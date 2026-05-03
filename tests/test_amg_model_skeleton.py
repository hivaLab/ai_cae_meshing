from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.dataset import load_amg_dataset_sample
from ai_mesh_generator.amg.model import (
    ACTION_NAMES,
    AmgGraphModel,
    AmgModelError,
    AmgModelOutput,
    ModelDimensions,
    apply_action_mask,
    build_graph_batch,
    project_model_output,
)

pytestmark = pytest.mark.model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_model_skeleton"
FEATURE_COLUMNS = [
    "feature_type_id",
    "role_id",
    "size_1_over_Lref",
    "size_2_over_Lref",
    "radius_over_Lref",
    "width_over_Lref",
    "length_over_Lref",
    "center_x_over_Lref",
    "center_y_over_Lref",
    "center_z_over_Lref",
    "distance_to_outer_boundary_over_Lref",
    "distance_to_nearest_feature_over_Lref",
    "clearance_ratio",
    "expected_action_mask",
]
EDGE_TYPES = [
    "PART_HAS_FACE",
    "FACE_HAS_COEDGE",
    "COEDGE_HAS_EDGE",
    "EDGE_HAS_VERTEX",
    "COEDGE_NEXT",
    "COEDGE_PREV",
    "COEDGE_MATE",
    "FACE_ADJACENT_FACE",
    "FEATURE_CONTAINS_FACE",
    "FEATURE_CONTAINS_EDGE",
]


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _graph_schema() -> dict:
    return {
        "schema_version": "AMG_BREP_GRAPH_SM_V1",
        "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
        "edge_types": EDGE_TYPES,
        "feature_candidate_columns": FEATURE_COLUMNS,
    }


def _manifest() -> dict:
    return {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": "SMT_SAMPLE",
            "part_class": "SM_FLAT_PANEL",
            "idealization": "midsurface_shell",
            "thickness_mm": 1.2,
            "element_type": "quad_dominant_shell",
            "batch_session": "AMG_SHELL_CONST_THICKNESS_V1",
        },
        "global_mesh": {
            "h0_mm": 4.0,
            "h_min_mm": 1.2,
            "h_max_mm": 7.2,
            "growth_rate_max": 1.3,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def _write_sample() -> Path:
    sample_dir = RUNS / "samples" / "sample_000001"
    rows = np.asarray(
        [
            # UNKNOWN HOLE with a deliberately permissive raw mask; SUPPRESS must be removed.
            [1, 0, 0.05, 0.05, 0.025, 0.0, 0.0, 0.4, 0.4, 0.0, 0.5, 0.5, 1.0, 0b00111],
            # STRUCTURAL BEND with only bend-row action available.
            [4, 7, 0.5, 90.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.0, 0.6, 0.6, 1.0, 0b01000],
        ],
        dtype=np.float64,
    )
    adjacency = {f"adj_{edge_type}": np.empty((0, 2), dtype=np.int64) for edge_type in EDGE_TYPES}
    _write_json(sample_dir / "graph" / "graph_schema.json", _graph_schema())
    np.savez(
        sample_dir / "graph" / "brep_graph.npz",
        node_type_ids=np.asarray([0, 5, 5], dtype=np.int64),
        part_features=np.asarray([[0.0, 0.0, 0.0, 0.0, 100.0, 64.0, 1.2]], dtype=np.float64),
        face_features=np.empty((0, 11), dtype=np.float64),
        edge_features=np.empty((0, 10), dtype=np.float64),
        coedge_features=np.empty((0, 4), dtype=np.float64),
        vertex_features=np.empty((0, 3), dtype=np.float64),
        feature_candidate_features=rows,
        feature_candidate_ids=np.asarray(["FEATURE_0001", "FEATURE_0002"]),
        feature_candidate_metadata_json=np.asarray([json.dumps({"candidate_id": "FEATURE_0001"}), json.dumps({"candidate_id": "FEATURE_0002"})]),
        coedge_next=np.empty((0, 2), dtype=np.int64),
        coedge_prev=np.empty((0, 2), dtype=np.int64),
        coedge_mate=np.empty((0, 2), dtype=np.int64),
        **adjacency,
    )
    _write_json(sample_dir / "labels" / "amg_manifest.json", _manifest())
    (sample_dir / "cad").mkdir(parents=True, exist_ok=True)
    (sample_dir / "cad" / "reference_midsurface.step").write_text("debug only\n", encoding="utf-8")
    return sample_dir


def _model_output() -> tuple[AmgModelOutput, dict]:
    sample = load_amg_dataset_sample(_write_sample())
    batch = build_graph_batch(sample)
    model = AmgGraphModel(ModelDimensions(part_feature_dim=batch.part_features.shape[1], hidden_dim=16))
    return model(batch), _manifest()["global_mesh"]


def test_build_graph_batch_from_t601_sample_excludes_reference_midsurface() -> None:
    sample = load_amg_dataset_sample(_write_sample())

    batch = build_graph_batch(sample)

    assert batch.part_features.shape == (1, 7)
    assert batch.feature_candidate_features.shape == (2, len(FEATURE_COLUMNS))
    assert batch.feature_batch_indices.tolist() == [0, 0]
    assert "reference_midsurface" not in json.dumps(batch.model_input_paths)


def test_model_forward_returns_all_expected_heads() -> None:
    sample = load_amg_dataset_sample(_write_sample())
    batch = build_graph_batch(sample)
    model = AmgGraphModel(ModelDimensions(part_feature_dim=batch.part_features.shape[1], hidden_dim=16))

    output = model(batch)

    assert output.part_class_logits.shape == (1, 5)
    assert output.feature_type_logits.shape == (2, 5)
    assert output.feature_action_logits.shape == (2, len(ACTION_NAMES))
    assert output.log_h.shape == (2, 2)
    assert output.division_values.shape == (2, 3)
    assert output.quality_risk_logits.shape == (2, 1)


def test_action_mask_uses_expected_mask_and_blocks_unknown_suppress() -> None:
    sample = load_amg_dataset_sample(_write_sample())
    batch = build_graph_batch(sample)
    suppress_index = ACTION_NAMES.index("SUPPRESS")

    assert batch.action_mask[0, suppress_index].item() is False
    assert batch.action_mask[1].tolist() == [False, False, False, True, False]

    logits = torch.zeros_like(batch.action_mask, dtype=torch.float32)
    logits[:, suppress_index] = 100.0
    masked = apply_action_mask(logits, batch.action_mask)
    assert masked[0].argmax().item() != suppress_index


def test_projector_bounds_model_outputs() -> None:
    output, mesh_policy = _model_output()
    output = replace(
        output,
        log_h=torch.tensor([[math.log(0.01), math.log(100.0)], [math.log(2.0), math.log(8.0)]], dtype=torch.float32),
        division_values=torch.tensor([[-2.0, 1.2, 3.7], [0.0, 5.1, 9.8]], dtype=torch.float32),
        quality_risk_logits=torch.zeros((2, 1), dtype=torch.float32),
    )

    projected = project_model_output(output, mesh_policy)

    assert torch.all(projected.h_values_mm >= mesh_policy["h_min_mm"])
    assert torch.all(projected.h_values_mm <= mesh_policy["h_max_mm"])
    assert torch.all(projected.division_values >= 1.0)
    assert torch.allclose(projected.quality_risk, torch.full((2, 1), 0.5))


def test_malformed_candidate_feature_columns_raise_model_error() -> None:
    bad_arrays = {
        "part_features": np.zeros((1, 7), dtype=np.float64),
        "feature_candidate_features": np.zeros((1, len(FEATURE_COLUMNS) - 1), dtype=np.float64),
    }

    with pytest.raises(AmgModelError) as exc_info:
        build_graph_batch(bad_arrays)

    assert exc_info.value.code == "malformed_candidate_features"


def test_model_source_does_not_import_cdf_package() -> None:
    model_root = ROOT / "ai_mesh_generator" / "amg" / "model"
    source = "\n".join(path.read_text(encoding="utf-8") for path in model_root.glob("*.py"))

    assert "cad_dataset_factory" not in source
