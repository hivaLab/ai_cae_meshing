from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.inference.real_mesh import (
    AmgRealInferenceError,
    RealInferenceConfig,
    build_predicted_amg_manifest,
    load_trained_checkpoint,
    main,
    run_real_mesh_inference,
    select_inference_samples,
)
from ai_mesh_generator.amg.model import AmgGraphModel, ModelDimensions

pytestmark = pytest.mark.model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_real_mesh_inference"

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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(sample_id: str, signature: str) -> dict:
    return {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": f"SMT_{sample_id}",
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
            "growth_rate_max": 1.35,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [
            {
                "feature_id": "HOLE_UNKNOWN_0001",
                "type": "HOLE",
                "role": "UNKNOWN",
                "action": "KEEP_REFINED",
                "geometry_signature": {"geometry_signature": signature},
                "controls": {
                    "edge_target_length_mm": 2.0,
                    "circumferential_divisions": 12,
                    "radial_growth_rate": 1.25,
                },
            }
        ],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def _write_sample(dataset_root: Path, sample_id: str) -> None:
    sample = dataset_root / "samples" / sample_id
    signature = f"HOLE:{sample_id}:8.000:8.000"
    _write_json(
        sample / "graph" / "graph_schema.json",
        {
            "schema_version": "AMG_BREP_GRAPH_SM_V1",
            "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
            "edge_types": EDGE_TYPES,
            "feature_candidate_columns": FEATURE_COLUMNS,
        },
    )
    metadata = {
        "candidate_id": "DETECTED_HOLE_0001",
        "type": "HOLE",
        "role": "UNKNOWN",
        "geometry_signature": signature,
        "size_1_mm": 8.0,
        "size_2_mm": 8.0,
        "radius_mm": 4.0,
    }
    arrays = {
        "node_type_ids": np.asarray([0], dtype=np.int64),
        "part_features": np.asarray([[0.0, 120.0, 80.0, 1.2, 120.0, 80.0, 1.2]], dtype=np.float64),
        "face_features": np.zeros((1, 4), dtype=np.float64),
        "edge_features": np.zeros((1, 4), dtype=np.float64),
        "coedge_features": np.zeros((1, 4), dtype=np.float64),
        "vertex_features": np.zeros((1, 3), dtype=np.float64),
        "feature_candidate_features": np.asarray([[1, 0, 0.05, 0.05, 0.025, 0.05, 0.05, 0.5, 0.5, 0.0, 0.6, 0.6, 1.2, 0b00111]], dtype=np.float64),
        "feature_candidate_ids": np.asarray(["DETECTED_HOLE_0001"]),
        "feature_candidate_metadata_json": np.asarray([json.dumps(metadata, sort_keys=True)]),
        "coedge_next": np.zeros((0, 2), dtype=np.int64),
        "coedge_prev": np.zeros((0, 2), dtype=np.int64),
        "coedge_mate": np.zeros((0, 2), dtype=np.int64),
    }
    for edge_type in EDGE_TYPES:
        arrays[f"adj_{edge_type}"] = np.zeros((0, 2), dtype=np.int64)
    (sample / "graph").mkdir(parents=True, exist_ok=True)
    np.savez(sample / "graph" / "brep_graph.npz", **arrays)
    _write_json(sample / "labels" / "amg_manifest.json", _manifest(sample_id, signature))
    cad_path = sample / "cad" / "input.step"
    cad_path.parent.mkdir(parents=True, exist_ok=True)
    cad_path.write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")


def _write_dataset(name: str, sample_count: int = 25) -> Path:
    dataset_root = RUNS / name
    if dataset_root.exists():
        import shutil

        shutil.rmtree(dataset_root)
    accepted = []
    for index in range(1, sample_count + 1):
        sample_id = f"sample_{index:06d}"
        _write_sample(dataset_root, sample_id)
        accepted.append(
            {
                "sample_id": sample_id,
                "sample_dir": f"samples/{sample_id}",
                "manifest": f"samples/{sample_id}/labels/amg_manifest.json",
                "acceptance_report": f"samples/{sample_id}/reports/sample_acceptance.json",
            }
        )
    _write_json(
        dataset_root / "dataset_index.json",
        {
            "schema": "CDF_DATASET_INDEX_SM_V1",
            "accepted_samples": accepted,
            "rejected_samples": [],
        },
    )
    (dataset_root / "splits").mkdir(parents=True, exist_ok=True)
    (dataset_root / "splits" / "train.txt").write_text("".join(f"{item['sample_id']}\n" for item in accepted), encoding="utf-8")
    (dataset_root / "splits" / "val.txt").write_text("", encoding="utf-8")
    return dataset_root


def _zero_model(part_feature_dim: int, hidden_dim: int = 8) -> AmgGraphModel:
    model = AmgGraphModel(ModelDimensions(part_feature_dim=part_feature_dim, hidden_dim=hidden_dim))
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    return model


def _write_checkpoint(dataset_root: Path, output_dir: Path, *, type_bias: int | None = None) -> tuple[Path, Path]:
    sample = select_inference_samples(dataset_root, limit=1)[0]
    model = _zero_model(sample.graph.arrays["part_features"].shape[1])
    if type_bias is not None:
        with torch.no_grad():
            model.feature_type_head.bias[type_bias] = 50.0
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "checkpoint.pt"
    training_config = output_dir / "training_config.json"
    torch.save({"model_state": model.state_dict()}, checkpoint)
    _write_json(training_config, {"hidden_dim": 8})
    return checkpoint, training_config


def _decode_payload(command: list[str]) -> dict:
    encoded = next(item.split(":", 1)[1] for item in command if item.startswith("-process_string:"))
    padded = encoded + "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def _fake_completed(command: list[str], accepted: bool = True, retry_case: str | None = None) -> subprocess.CompletedProcess:
    payload = _decode_payload(command)
    sample_dir = Path(payload["sample_dir"])
    sample_id = sample_dir.name
    _write_json(
        Path(payload["execution_report"]),
        {
            "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
            "sample_id": sample_id,
            "accepted": accepted,
            "ansa_version": "ANSA_v25.1.0",
            "step_import_success": True,
            "geometry_cleanup_success": True,
            "midsurface_extraction_success": True,
            "feature_matching_success": True,
            "batch_mesh_success": True,
            "solver_export_success": True,
            "runtime_sec": 1.0,
            "outputs": {"solver_deck": "meshes/ansa_oracle_mesh.bdf"},
        },
    )
    quality_payload = {"num_hard_failed_elements": 0 if accepted else 1}
    if retry_case is not None:
        quality_payload["retry_case"] = retry_case
    _write_json(
        Path(payload["quality_report"]),
        {
            "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
            "sample_id": sample_id,
            "accepted": accepted,
            "mesh_stats": {"num_shell_elements": 10},
            "quality": quality_payload,
            "feature_checks": [],
        },
    )
    mesh = sample_dir / "meshes" / "ansa_oracle_mesh.bdf"
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    return subprocess.CompletedProcess(command, 0 if accepted else 2, "ok", "")


def test_checkpoint_load_and_deterministic_held_out_selection() -> None:
    dataset = _write_dataset("selector", sample_count=25)
    checkpoint, training_config = _write_checkpoint(dataset, RUNS / "selector_ckpt")

    samples = select_inference_samples(dataset, limit=20)
    model = load_trained_checkpoint(checkpoint, training_config, samples[0])

    assert samples[0].sample_id == "sample_000006"
    assert samples[-1].sample_id == "sample_000025"
    assert isinstance(model, AmgGraphModel)


def test_split_selection_uses_requested_split_without_default_limit() -> None:
    dataset = _write_dataset("split_selector", sample_count=25)
    (dataset / "splits" / "test.txt").write_text(
        "".join(f"sample_{index:06d}\n" for index in range(3, 8)),
        encoding="utf-8",
    )

    samples = select_inference_samples(dataset, split="test", limit=None)

    assert [sample.sample_id for sample in samples] == [f"sample_{index:06d}" for index in range(3, 8)]


def test_predicted_manifest_validates_and_bounds_controls() -> None:
    dataset = _write_dataset("manifest", sample_count=1)
    sample = select_inference_samples(dataset, limit=1)[0]
    model = _zero_model(sample.graph.arrays["part_features"].shape[1])

    result = build_predicted_amg_manifest(sample, model)

    assert result.status == "PREDICTED"
    assert result.manifest is not None
    feature = result.manifest["features"][0]
    assert feature["action"] == "KEEP_REFINED"
    assert feature["controls"]["edge_target_length_mm"] == pytest.approx(1.2)
    assert feature["controls"]["circumferential_divisions"] == 1
    assert feature["action"] != "SUPPRESS"


def test_type_mismatch_rejects_before_ansa(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _write_dataset("type_mismatch", sample_count=1)
    checkpoint, training_config = _write_checkpoint(dataset, RUNS / "type_mismatch_ckpt", type_bias=1)
    executable = RUNS / "fake_ansa.bat"
    executable.write_text("@echo off\n", encoding="utf-8")

    def fail_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("ANSA subprocess must not be called for rejected model output")

    monkeypatch.setattr("ai_mesh_generator.amg.inference.real_mesh.subprocess.run", fail_run)
    result = run_real_mesh_inference(
        RealInferenceConfig(
            dataset_root=dataset,
            checkpoint_path=checkpoint,
            training_config_path=training_config,
            output_dir=RUNS / "type_mismatch_out",
            ansa_executable=executable,
            limit=1,
        )
    )

    assert result.status == "PARTIAL_FAILED"
    assert result.sample_results[0].status == "MODEL_REJECTED"
    assert result.sample_results[0].error_code == "feature_type_mismatch"


def test_real_inference_builds_ansa_command_and_accepts_real_shaped_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _write_dataset("success", sample_count=2)
    checkpoint, training_config = _write_checkpoint(dataset, RUNS / "success_ckpt")
    executable = RUNS / "ansa64.bat"
    executable.write_text("@echo off\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        commands.append(list(command))
        assert kwargs["timeout"] == 180
        return _fake_completed(list(command), accepted=True)

    monkeypatch.setattr("ai_mesh_generator.amg.inference.real_mesh.subprocess.run", fake_run)
    result = run_real_mesh_inference(
        RealInferenceConfig(
            dataset_root=dataset,
            checkpoint_path=checkpoint,
            training_config_path=training_config,
            output_dir=RUNS / "success_out",
            ansa_executable=executable,
            limit=1,
        )
    )

    assert result.status == "SUCCESS"
    assert result.success_count == 1
    payload = _decode_payload(commands[0])
    assert payload["sample_dir"].endswith("sample_000002")
    assert payload["manifest"].endswith("labels/amg_manifest.json")
    assert payload["execution_report"].endswith("reports/ansa_execution_report.json")
    assert payload["quality_report"].endswith("reports/ansa_quality_report.json")
    assert Path(result.sample_results[0].solver_deck_path).is_file()


@pytest.mark.parametrize(
    ("name", "execution_patch", "quality_patch", "mesh_text", "expected"),
    [
        ("controlled", {"accepted": False, "ansa_version": "unavailable", "outputs": {"controlled_failure_reason": "ansa_api_unavailable"}}, {"accepted": False}, "CEND\n", "controlled_failure_report"),
        ("hard_failed", {"accepted": False}, {"accepted": False, "quality": {"num_hard_failed_elements": 1}}, "CEND\n", "quality_not_satisfied_after_retry"),
        ("placeholder", {"accepted": True}, {"accepted": True, "quality": {"num_hard_failed_elements": 0}}, "placeholder mesh\n", "quality_not_satisfied_after_retry"),
    ],
)
def test_bad_ansa_outputs_are_not_success(monkeypatch: pytest.MonkeyPatch, name: str, execution_patch: dict, quality_patch: dict, mesh_text: str, expected: str) -> None:
    dataset = _write_dataset(f"bad_{name}", sample_count=1)
    checkpoint, training_config = _write_checkpoint(dataset, RUNS / f"bad_{name}_ckpt")
    executable = RUNS / f"bad_{name}_ansa.bat"
    executable.write_text("@echo off\n", encoding="utf-8")

    def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        payload = _decode_payload(list(command))
        sample_dir = Path(payload["sample_dir"])
        execution = {
            "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
            "sample_id": sample_dir.name,
            "accepted": True,
            "ansa_version": "ANSA_v25.1.0",
            "step_import_success": True,
            "geometry_cleanup_success": True,
            "midsurface_extraction_success": True,
            "feature_matching_success": True,
            "batch_mesh_success": True,
            "solver_export_success": True,
            "runtime_sec": 1.0,
            "outputs": {"solver_deck": "meshes/ansa_oracle_mesh.bdf"},
        }
        execution.update(execution_patch)
        quality = {
            "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
            "sample_id": sample_dir.name,
            "accepted": True,
            "mesh_stats": {"num_shell_elements": 10},
            "quality": {"num_hard_failed_elements": 0, "retry_case": "global_growth_fail"},
            "feature_checks": [],
        }
        quality.update(quality_patch)
        _write_json(Path(payload["execution_report"]), execution)
        _write_json(Path(payload["quality_report"]), quality)
        mesh = sample_dir / "meshes" / "ansa_oracle_mesh.bdf"
        mesh.parent.mkdir(parents=True, exist_ok=True)
        mesh.write_text(mesh_text, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0 if execution["accepted"] else 2, "ok", "")

    monkeypatch.setattr("ai_mesh_generator.amg.inference.real_mesh.subprocess.run", fake_run)
    result = run_real_mesh_inference(
        RealInferenceConfig(
            dataset_root=dataset,
            checkpoint_path=checkpoint,
            training_config_path=training_config,
            output_dir=RUNS / f"bad_{name}_out",
            ansa_executable=executable,
            limit=1,
            max_retries=1,
        )
    )

    assert result.status == "PARTIAL_FAILED"
    assert result.sample_results[0].error_code == expected


def test_cli_entrypoint_success_and_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _write_dataset("cli", sample_count=1)
    checkpoint, training_config = _write_checkpoint(dataset, RUNS / "cli_ckpt")
    executable = RUNS / "cli_ansa.bat"
    executable.write_text("@echo off\n", encoding="utf-8")

    monkeypatch.setattr("ai_mesh_generator.amg.inference.real_mesh.subprocess.run", lambda command, **kwargs: _fake_completed(list(command), accepted=True))

    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--checkpoint",
                str(checkpoint),
                "--training-config",
                str(training_config),
                "--out",
                str(RUNS / "cli_out"),
                "--ansa-executable",
                str(executable),
                "--limit",
                "1",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--checkpoint",
                str(checkpoint),
                "--training-config",
                str(training_config),
                "--out",
                str(RUNS / "cli_blocked"),
                "--ansa-executable",
                str(RUNS / "missing_ansa.bat"),
                "--limit",
                "1",
            ]
        )
        == 2
    )


def test_inference_source_does_not_import_cdf_or_reference_midsurface() -> None:
    source = (ROOT / "ai_mesh_generator" / "amg" / "inference" / "real_mesh.py").read_text(encoding="utf-8")

    assert "import cad_dataset_factory" not in source
    assert "from cad_dataset_factory" not in source
    assert "reference_midsurface" not in source
    assert "target_action_id" not in source
    assert "target_edge_length_mm" not in source
