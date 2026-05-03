from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.model import AmgGraphModel, ModelDimensions, build_graph_batch
from ai_mesh_generator.amg.training import (
    AmgTrainingSmokeError,
    build_smoke_targets,
    compute_smoke_loss,
    load_smoke_checkpoint,
    run_training_smoke,
    save_smoke_checkpoint,
)

pytestmark = pytest.mark.model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_training_smoke"


def _arrays(*, rows: np.ndarray | None = None) -> dict[str, np.ndarray]:
    if rows is None:
        rows = np.asarray(
            [
                # UNKNOWN HOLE: raw SUPPRESS bit is present, but model batching must remove it.
                [1, 0, 0.05, 0.05, 0.025, 0.0, 0.0, 0.4, 0.4, 0.0, 0.5, 0.5, 1.2, 0b00111],
                # STRUCTURAL BEND: bend-row action only.
                [4, 7, 0.5, 90.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.0, 0.6, 0.6, 1.0, 0b01000],
            ],
            dtype=np.float64,
        )
    return {
        "part_features": np.asarray([[0.0, 0.0, 0.0, 0.0, 100.0, 64.0, 1.2]], dtype=np.float64),
        "feature_candidate_features": rows,
    }


def _model_and_batch() -> tuple[AmgGraphModel, object]:
    batch = build_graph_batch(_arrays())
    model = AmgGraphModel(ModelDimensions(part_feature_dim=batch.part_features.shape[1], hidden_dim=16))
    return model, batch


def test_build_smoke_targets_from_graph_rows_and_masks() -> None:
    batch = build_graph_batch(_arrays())

    targets = build_smoke_targets(batch)

    assert targets.part_class_targets.tolist() == [0]
    assert targets.feature_type_targets.tolist() == [0, 3]
    assert targets.feature_action_targets.tolist() == [0, 3]
    assert targets.log_h_targets.shape == (2, 2)
    assert targets.division_targets.shape == (2, 3)
    assert targets.quality_risk_targets.shape == (2, 1)


def test_compute_smoke_loss_returns_finite_scalar_and_head_losses() -> None:
    model, batch = _model_and_batch()
    targets = build_smoke_targets(batch)

    breakdown = compute_smoke_loss(model(batch), targets)

    assert torch.isfinite(breakdown.total)
    for value in breakdown.as_metrics().values():
        assert math.isfinite(value)


def test_masked_feature_action_loss_respects_action_mask() -> None:
    model, batch = _model_and_batch()
    targets = build_smoke_targets(batch)
    output = model(batch)
    suppress_index = 2

    output.feature_action_logits.data[:, suppress_index] = 1.0e6
    breakdown = compute_smoke_loss(output, targets)

    assert torch.isfinite(breakdown.feature_action)
    assert targets.feature_action_targets.tolist() == [0, 3]


def test_run_training_smoke_reports_metrics_and_checkpoint() -> None:
    result = run_training_smoke(_arrays(), RUNS / "run", steps=2, seed=1234)

    assert result.steps == 2
    assert len(result.loss_history) == 2
    assert math.isfinite(result.initial_loss)
    assert math.isfinite(result.final_loss)
    assert result.metrics["parameter_delta_norm"] > 0.0
    assert Path(result.checkpoint_path).is_file()


def test_optimizer_step_changes_trainable_parameter() -> None:
    model, batch = _model_and_batch()
    targets = build_smoke_targets(batch)
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    before = [parameter.detach().clone() for parameter in model.parameters() if parameter.requires_grad]

    optimizer.zero_grad(set_to_none=True)
    compute_smoke_loss(model(batch), targets).total.backward()
    optimizer.step()

    assert any(not torch.allclose(old, new) for old, new in zip(before, (p for p in model.parameters() if p.requires_grad)))


def test_checkpoint_save_load_restores_state_and_metrics() -> None:
    model, batch = _model_and_batch()
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    output = model(batch)
    targets = build_smoke_targets(batch)
    compute_smoke_loss(output, targets).total.backward()
    optimizer.step()
    expected_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
    checkpoint_path = RUNS / "checkpoint" / "smoke.pt"
    metrics = {"loss_total": 1.25}

    save_smoke_checkpoint(checkpoint_path, model, optimizer, 1, metrics)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.add_(10.0)
    checkpoint = load_smoke_checkpoint(checkpoint_path, model, optimizer)

    for key, value in expected_state.items():
        assert torch.allclose(model.state_dict()[key], value)
    assert checkpoint["step"] == 1
    assert checkpoint["metrics"] == metrics


def test_empty_candidate_batch_raises_training_error() -> None:
    rows = np.empty((0, 14), dtype=np.float64)
    batch = build_graph_batch(_arrays(rows=rows))

    with pytest.raises(AmgTrainingSmokeError) as exc_info:
        build_smoke_targets(batch)

    assert exc_info.value.code == "empty_candidate_batch"


def test_all_masked_action_row_raises_training_error() -> None:
    rows = np.asarray([[1, 7, 0.05, 0.05, 0.025, 0.0, 0.0, 0.4, 0.4, 0.0, 0.5, 0.5, 1.0, 0]], dtype=np.float64)
    batch = build_graph_batch(_arrays(rows=rows))

    with pytest.raises(AmgTrainingSmokeError) as exc_info:
        build_smoke_targets(batch)

    assert exc_info.value.code == "empty_action_mask"


def test_training_source_does_not_import_cdf_package() -> None:
    training_root = ROOT / "ai_mesh_generator" / "amg" / "training"
    source = "\n".join(path.read_text(encoding="utf-8") for path in training_root.glob("*.py"))

    assert "cad_dataset_factory" not in source
    assert "reference_midsurface" not in json.dumps(build_graph_batch(_arrays()).model_input_paths)
