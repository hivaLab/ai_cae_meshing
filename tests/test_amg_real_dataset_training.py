from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.model import build_graph_batch
from ai_mesh_generator.amg.training.real import (
    AmgRealTrainingError,
    RealTrainingConfig,
    build_manifest_supervision_targets,
    main,
    run_real_dataset_training,
    validate_real_training_dataset,
)

pytestmark = pytest.mark.model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_real_dataset_training"

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


def _sample_manifest(sample_id: str, signature: str) -> dict:
    return {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": f"SMT_SM_FLAT_PANEL_T120_{sample_id}",
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


def _write_sample(dataset_root: Path, sample_id: str, *, invalid: str | None = None) -> None:
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
    }
    arrays = {
        "node_type_ids": np.asarray([0], dtype=np.int64),
        "part_features": np.asarray([[0.0, 120.0, 80.0, 1.2, 9600.0, 6.0, 12.0]], dtype=np.float64),
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
    _write_json(sample / "labels" / "amg_manifest.json", _sample_manifest(sample_id, signature))
    _write_json(
        sample / "reports" / "sample_acceptance.json",
        {
            "schema": "CDF_SAMPLE_ACCEPTANCE_SM_ANSA_V1",
            "sample_id": sample_id,
            "accepted": True,
            "accepted_by": {
                "geometry_validation": True,
                "feature_matching": True,
                "manifest_schema": True,
                "ansa_oracle": invalid != "not_accepted_by_ansa",
            },
            "rejection_reason": None,
        },
    )
    outputs = {"solver_deck": "meshes/ansa_oracle_mesh.bdf"}
    if invalid == "controlled_failure":
        outputs["controlled_failure_reason"] = "ansa_api_unavailable"
    _write_json(
        sample / "reports" / "ansa_execution_report.json",
        {
            "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
            "sample_id": sample_id,
            "accepted": invalid not in {"execution_failed"},
            "ansa_version": "mock-ansa" if invalid == "mock_ansa" else "ANSA_v25.1.0",
            "step_import_success": True,
            "geometry_cleanup_success": True,
            "midsurface_extraction_success": True,
            "feature_matching_success": True,
            "batch_mesh_success": True,
            "solver_export_success": True,
            "runtime_sec": 1.0,
            "outputs": outputs,
        },
    )
    _write_json(
        sample / "reports" / "ansa_quality_report.json",
        {
            "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
            "sample_id": sample_id,
            "accepted": invalid not in {"quality_failed", "hard_failed"},
            "mesh_stats": {"num_shell_elements": 10},
            "quality": {"num_hard_failed_elements": 1 if invalid == "hard_failed" else 0},
            "feature_checks": [],
        },
    )
    mesh_text = "placeholder mesh\n" if invalid == "placeholder_mesh" else "CEND\nBEGIN BULK\nENDDATA\n"
    mesh_path = sample / "meshes" / "ansa_oracle_mesh.bdf"
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    if invalid != "missing_mesh":
        mesh_path.write_text(mesh_text, encoding="utf-8")


def _write_dataset(name: str, *, invalid: str | None = None, sample_count: int = 2) -> Path:
    dataset_root = RUNS / name
    if dataset_root.exists():
        import shutil

        shutil.rmtree(dataset_root)
    accepted = []
    for index in range(1, sample_count + 1):
        sample_id = f"sample_{index:06d}"
        _write_sample(dataset_root, sample_id, invalid=invalid if index == 1 else None)
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
            "num_accepted": len(accepted),
            "num_rejected": 0,
            "accepted_samples": accepted,
            "rejected_samples": [],
        },
    )
    (dataset_root / "splits").mkdir(parents=True, exist_ok=True)
    (dataset_root / "splits" / "train.txt").write_text("".join(f"{item['sample_id']}\n" for item in accepted), encoding="utf-8")
    (dataset_root / "splits" / "val.txt").write_text("", encoding="utf-8")
    return dataset_root


def test_valid_real_dataset_passes_acceptance_gate() -> None:
    dataset_root = _write_dataset("valid_gate")

    samples = validate_real_training_dataset(dataset_root)

    assert [sample.sample_id for sample in samples] == ["sample_000001", "sample_000002"]


@pytest.mark.parametrize("invalid", ["missing_mesh", "placeholder_mesh", "mock_ansa", "controlled_failure", "hard_failed"])
def test_invalid_real_acceptance_evidence_raises(invalid: str) -> None:
    dataset_root = _write_dataset(f"invalid_{invalid}", invalid=invalid)

    with pytest.raises(AmgRealTrainingError) as exc_info:
        validate_real_training_dataset(dataset_root)

    assert exc_info.value.code == "dataset_not_real_accepted"


def test_manifest_supervision_targets_map_actions_and_numeric_controls() -> None:
    samples = validate_real_training_dataset(_write_dataset("targets"))
    batch = build_graph_batch(samples)

    targets = build_manifest_supervision_targets(samples, batch)

    assert targets.part_class_targets.tolist() == [0, 0]
    assert targets.feature_type_targets.tolist() == [0, 0]
    assert targets.feature_action_targets.tolist() == [0, 0]
    assert torch.allclose(torch.exp(targets.log_h_targets[:, 0]), torch.full((2,), 2.0))
    assert targets.log_h_mask[:, 0].tolist() == [True, True]
    assert targets.log_h_mask[:, 1].tolist() == [False, False]
    assert targets.division_targets[:, 0].tolist() == [12.0, 12.0]
    assert targets.matched_feature_count == 2
    assert targets.manifest_feature_count == 2


def test_empty_validation_split_uses_deterministic_split_and_writes_metrics() -> None:
    dataset_root = _write_dataset("train_run", sample_count=5)
    output_dir = RUNS / "real_training"

    result = run_real_dataset_training(RealTrainingConfig(dataset_root=dataset_root, output_dir=output_dir, epochs=2, batch_size=2, seed=1))

    assert Path(result.checkpoint_path).is_file()
    assert Path(result.metrics_path).is_file()
    assert result.metrics["split_source"] == "deterministic_80_20_split"
    assert result.metrics["sample_count"] == 5
    assert result.metrics["label_coverage_ratio"] == 1.0
    assert result.metrics["train_sample_count"] == 4
    assert result.metrics["validation_sample_count"] == 1


def test_cli_entrypoint_returns_success_and_failure_codes() -> None:
    valid_root = _write_dataset("cli_valid", sample_count=2)
    invalid_root = _write_dataset("cli_invalid", invalid="mock_ansa", sample_count=2)

    assert main(["--dataset", str(valid_root), "--out", str(RUNS / "cli_out"), "--epochs", "1", "--batch-size", "1"]) == 0
    assert main(["--dataset", str(invalid_root), "--out", str(RUNS / "cli_bad"), "--epochs", "1", "--batch-size", "1"]) == 1


def test_real_training_source_does_not_import_cdf_or_reference_midsurface() -> None:
    training_root = ROOT / "ai_mesh_generator" / "amg" / "training"
    source = "\n".join(path.read_text(encoding="utf-8") for path in training_root.glob("*.py"))

    assert "cad_dataset_factory" not in source
    assert "reference_midsurface" not in source
