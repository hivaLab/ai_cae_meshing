from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from cad_dataset_factory.cdf.cli import main as cdf_main
from cad_dataset_factory.cdf.dataset import build_sample_acceptance, write_dataset_index
from cad_dataset_factory.cdf.pipeline import generate_dataset, validate_dataset

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_e2e_dataset_cli"
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


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest() -> dict:
    return {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": "SMT_SM_FLAT_PANEL_T120_P000001",
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
        "features": [],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def _graph_schema() -> dict:
    return {
        "schema_version": "AMG_BREP_GRAPH_SM_V1",
        "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
        "edge_types": EDGE_TYPES,
        "feature_candidate_columns": FEATURE_COLUMNS,
    }


def _write_graph(sample_dir: Path) -> None:
    _write_json(sample_dir / "graph" / "graph_schema.json", _graph_schema())
    adjacency = {f"adj_{edge_type}": np.empty((0, 2), dtype=np.int64) for edge_type in EDGE_TYPES}
    np.savez(
        sample_dir / "graph" / "brep_graph.npz",
        node_type_ids=np.asarray([0], dtype=np.int64),
        part_features=np.asarray([[0.0, 0.0, 0.0, 0.0, 100.0, 64.0, 1.2]], dtype=np.float64),
        face_features=np.empty((0, 11), dtype=np.float64),
        edge_features=np.empty((0, 10), dtype=np.float64),
        coedge_features=np.empty((0, 4), dtype=np.float64),
        vertex_features=np.empty((0, 3), dtype=np.float64),
        feature_candidate_features=np.empty((0, len(FEATURE_COLUMNS)), dtype=np.float64),
        coedge_next=np.empty((0, 2), dtype=np.int64),
        coedge_prev=np.empty((0, 2), dtype=np.int64),
        coedge_mate=np.empty((0, 2), dtype=np.int64),
        **adjacency,
    )


def _execution_report(*, accepted: bool = True, controlled: bool = False) -> dict:
    return {
        "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
        "sample_id": "sample_000001",
        "accepted": accepted,
        "ansa_version": "unavailable" if controlled else "ANSA_REAL_TEST",
        "step_import_success": accepted,
        "geometry_cleanup_success": accepted,
        "midsurface_extraction_success": accepted,
        "feature_matching_success": accepted,
        "batch_mesh_success": accepted,
        "solver_export_success": accepted,
        "runtime_sec": 1.0,
        "outputs": {"controlled_failure_reason": "ansa_api_unavailable"} if controlled else {},
    }


def _quality_report(*, accepted: bool = True, hard_failed: int = 0) -> dict:
    return {
        "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
        "sample_id": "sample_000001",
        "accepted": accepted,
        "mesh_stats": {"num_elements": 10},
        "quality": {"num_hard_failed_elements": hard_failed},
        "feature_checks": [],
    }


def _write_accepted_sample(dataset_root: Path, *, controlled: bool = False, omit_quality: bool = False, mesh_text: str = "real mesh\n") -> Path:
    sample_id = "sample_000001"
    sample_dir = dataset_root / "samples" / sample_id
    (sample_dir / "cad").mkdir(parents=True, exist_ok=True)
    (sample_dir / "labels").mkdir(parents=True, exist_ok=True)
    (sample_dir / "reports").mkdir(parents=True, exist_ok=True)
    (sample_dir / "meshes").mkdir(parents=True, exist_ok=True)
    (sample_dir / "cad" / "input.step").write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
    _write_graph(sample_dir)
    _write_json(sample_dir / "labels" / "amg_manifest.json", _manifest())
    _write_json(sample_dir / "reports" / "ansa_execution_report.json", _execution_report(accepted=not controlled, controlled=controlled))
    if not omit_quality:
        _write_json(sample_dir / "reports" / "ansa_quality_report.json", _quality_report())
    (sample_dir / "meshes" / "ansa_oracle_mesh.bdf").write_text(mesh_text, encoding="utf-8")
    _write_json(
        sample_dir / "reports" / "sample_acceptance.json",
        build_sample_acceptance(
            sample_id,
            {
                "geometry_validation": True,
                "feature_matching": True,
                "manifest_schema": True,
                "ansa_oracle": True,
            },
        ),
    )
    write_dataset_index(dataset_root, [{"sample_id": sample_id}], [], {"schema": "CDF_CONFIG_SM_ANSA_V1"})
    return sample_dir


def test_generate_require_ansa_missing_executable_blocks_without_accepted_samples(monkeypatch) -> None:
    monkeypatch.delenv("ANSA_EXECUTABLE", raising=False)
    dataset_root = _fresh(RUNS / "missing_ansa")

    result = generate_dataset(
        config_path=ROOT / "configs" / "cdf_sm_ansa_v1.default.json",
        out_dir=dataset_root,
        count=3,
        seed=1,
        require_ansa=True,
        env={},
    )

    index = json.loads((dataset_root / "dataset_index.json").read_text(encoding="utf-8"))
    stats = json.loads((dataset_root / "dataset_stats.json").read_text(encoding="utf-8"))
    assert result.exit_code == 2
    assert result.status == "BLOCKED"
    assert index["num_accepted"] == 0
    assert index["accepted_samples"] == []
    assert stats["status"] == "BLOCKED"
    assert stats["reason"] == "missing_ansa_executable"
    assert not any((dataset_root / "samples").iterdir())
    assert (dataset_root / "splits" / "train.txt").read_text(encoding="utf-8") == ""


def test_cli_generate_returns_blocked_exit_code_for_missing_ansa(monkeypatch) -> None:
    monkeypatch.delenv("ANSA_EXECUTABLE", raising=False)
    dataset_root = _fresh(RUNS / "cli_missing_ansa")

    code = cdf_main(
        [
            "generate",
            "--config",
            str(ROOT / "configs" / "cdf_sm_ansa_v1.default.json"),
            "--out",
            str(dataset_root),
            "--count",
            "3",
            "--seed",
            "1",
            "--require-ansa",
        ]
    )

    assert code == 2
    assert json.loads((dataset_root / "dataset_index.json").read_text(encoding="utf-8"))["num_accepted"] == 0


def test_validate_rejects_accepted_sample_missing_quality_report() -> None:
    dataset_root = _fresh(RUNS / "missing_quality")
    _write_accepted_sample(dataset_root, omit_quality=True)

    result = validate_dataset(dataset_root=dataset_root, require_ansa=True)

    assert result.exit_code == 3
    assert result.status == "VALIDATION_FAILED"
    assert result.errors[0]["code"] == "missing_required_sample_file"
    assert "reports/ansa_quality_report.json" in result.errors[0]["message"]


def test_validate_rejects_controlled_failure_ansa_report() -> None:
    dataset_root = _fresh(RUNS / "controlled_failure")
    _write_accepted_sample(dataset_root, controlled=True)

    result = validate_dataset(dataset_root=dataset_root, require_ansa=True)

    assert result.exit_code == 3
    assert result.status == "VALIDATION_FAILED"
    assert result.errors[0]["code"] == "unreal_ansa_execution_report"


def test_validate_rejects_placeholder_oracle_mesh() -> None:
    dataset_root = _fresh(RUNS / "placeholder_mesh")
    _write_accepted_sample(dataset_root, mesh_text="placeholder mesh\n")

    result = validate_dataset(dataset_root=dataset_root, require_ansa=True)

    assert result.exit_code == 3
    assert result.errors[0]["code"] == "missing_or_placeholder_oracle_mesh"


def test_cli_validate_returns_validation_failed_exit_code() -> None:
    dataset_root = _fresh(RUNS / "cli_validate")
    _write_accepted_sample(dataset_root, omit_quality=True)

    code = cdf_main(["validate", "--dataset", str(dataset_root), "--require-ansa"])

    assert code == 3


@pytest.mark.requires_ansa
def test_real_ansa_gate_never_accepts_without_real_oracle_outputs() -> None:
    if not os.environ.get("ANSA_EXECUTABLE"):
        pytest.skip("ANSA_EXECUTABLE is not configured")
    dataset_root = _fresh(RUNS / "real_ansa_gate")

    result = generate_dataset(
        config_path=ROOT / "configs" / "cdf_sm_ansa_v1.default.json",
        out_dir=dataset_root,
        count=1,
        seed=1,
        require_ansa=True,
    )

    if result.status == "SUCCESS":
        assert result.accepted_count == 1
        assert validate_dataset(dataset_root=dataset_root, require_ansa=True).exit_code == 0
    else:
        assert result.accepted_count == 0
