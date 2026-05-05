from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.training.quality import (
    AmgQualityTrainingError,
    QualityTrainingConfig,
    run_quality_training,
)

pytestmark = pytest.mark.model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_quality_training"

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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _graph_schema() -> dict:
    return {
        "schema_version": "AMG_BREP_GRAPH_SM_V1",
        "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
        "edge_types": EDGE_TYPES,
        "feature_candidate_columns": FEATURE_COLUMNS,
    }


def _manifest(sample_id: str, *, action: str = "KEEP_REFINED", edge_length: float = 2.0) -> dict:
    controls = {
        "edge_target_length_mm": edge_length,
        "circumferential_divisions": 12,
        "radial_growth_rate": 1.25,
    }
    if action == "KEEP_WITH_WASHER":
        controls.update({"washer_rings": 2, "washer_outer_radius_mm": 8.0})
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
            "h_min_mm": 1.0,
            "h_max_mm": 6.0,
            "growth_rate_max": 1.35,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [
            {
                "feature_id": "HOLE_UNKNOWN_0001",
                "type": "HOLE",
                "role": "UNKNOWN",
                "action": action,
                "geometry_signature": {"geometry_signature": f"HOLE:{sample_id}"},
                "controls": controls,
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


def _write_graph(sample_dir: Path) -> None:
    _write_json(sample_dir / "graph" / "graph_schema.json", _graph_schema())
    metadata = {"candidate_id": "DETECTED_HOLE_0001", "type": "HOLE", "role": "UNKNOWN", "geometry_signature": "HOLE"}
    arrays = {
        "node_type_ids": np.asarray([0], dtype=np.int64),
        "part_features": np.asarray([[0.0, 120.0, 80.0, 1.2, 9600.0, 6.0, 12.0]], dtype=np.float64),
        "face_features": np.zeros((1, 4), dtype=np.float64),
        "edge_features": np.zeros((1, 4), dtype=np.float64),
        "coedge_features": np.zeros((1, 4), dtype=np.float64),
        "vertex_features": np.zeros((1, 3), dtype=np.float64),
        "feature_candidate_features": np.asarray([[1, 0, 0.05, 0.05, 0.025, 0.05, 0.05, 0.5, 0.5, 0.0, 0.6, 0.6, 1.2, 0b00011]], dtype=np.float64),
        "feature_candidate_ids": np.asarray(["DETECTED_HOLE_0001"]),
        "feature_candidate_metadata_json": np.asarray([json.dumps(metadata, sort_keys=True)]),
        "coedge_next": np.zeros((0, 2), dtype=np.int64),
        "coedge_prev": np.zeros((0, 2), dtype=np.int64),
        "coedge_mate": np.zeros((0, 2), dtype=np.int64),
    }
    for edge_type in EDGE_TYPES:
        arrays[f"adj_{edge_type}"] = np.zeros((0, 2), dtype=np.int64)
    np.savez(sample_dir / "graph" / "brep_graph.npz", **arrays)


def _write_fixture(name: str, *, equal_scores: bool = False) -> tuple[Path, Path]:
    root = _fresh(RUNS / name)
    dataset = root / "dataset"
    quality = root / "quality_exploration"
    accepted = []
    records = []
    for index in range(1, 3):
        sample_id = f"sample_{index:06d}"
        sample = dataset / "samples" / sample_id
        _write_graph(sample)
        _write_json(sample / "labels" / "amg_manifest.json", _manifest(sample_id, action="KEEP_REFINED", edge_length=2.0))
        accepted.append({"sample_id": sample_id, "sample_dir": f"samples/{sample_id}"})
        perturb_manifest = quality / "samples" / sample_id / "perturb_001" / "labels" / "amg_manifest.json"
        _write_json(perturb_manifest, _manifest(sample_id, action="KEEP_WITH_WASHER", edge_length=3.5))
        baseline_score = float(index)
        perturb_score = baseline_score if equal_scores else baseline_score + 3.0
        records.extend(
            [
                {
                    "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
                    "sample_id": sample_id,
                    "evaluation_id": "baseline",
                    "status": "PASSED",
                    "manifest_path": (sample / "labels" / "amg_manifest.json").as_posix(),
                    "quality_score": baseline_score,
                    "accepted": True,
                },
                {
                    "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
                    "sample_id": sample_id,
                    "evaluation_id": "perturb_001",
                    "status": "FAILED",
                    "manifest_path": perturb_manifest.as_posix(),
                    "quality_score": perturb_score,
                    "accepted": False,
                },
            ]
        )
    _write_json(dataset / "dataset_index.json", {"schema": "CDF_DATASET_INDEX_SM_V1", "accepted_samples": accepted, "rejected_samples": []})
    (dataset / "splits").mkdir(parents=True, exist_ok=True)
    (dataset / "splits" / "train.txt").write_text("sample_000001\n", encoding="utf-8")
    (dataset / "splits" / "val.txt").write_text("sample_000002\n", encoding="utf-8")
    _write_json(
        quality / "quality_exploration_summary.json",
        {
            "schema": "CDF_QUALITY_EXPLORATION_SUMMARY_V1",
            "status": "SUCCESS",
            "dataset_root": dataset.as_posix(),
            "records": records,
            "quality_score_variance": 2.5,
        },
    )
    return dataset, quality


def test_quality_training_runs_pairwise_ranking_and_writes_checkpoint() -> None:
    dataset, quality = _write_fixture("train")
    output = RUNS / "train" / "training"

    result = run_quality_training(QualityTrainingConfig(dataset_root=dataset, quality_exploration_root=quality, output_dir=output, epochs=2, seed=708))

    assert Path(result.checkpoint_path).is_file()
    assert Path(result.metrics_path).is_file()
    assert result.metrics["example_count"] == 4
    assert result.metrics["train_pair_count"] == 1
    assert result.metrics["validation_pair_count"] == 1
    assert result.metrics["quality_score_variance"] > 0.0


def test_quality_training_rejects_empty_pairwise_signal() -> None:
    dataset, quality = _write_fixture("equal", equal_scores=True)

    with pytest.raises(AmgQualityTrainingError) as exc_info:
        run_quality_training(QualityTrainingConfig(dataset_root=dataset, quality_exploration_root=quality, output_dir=RUNS / "equal" / "training"))

    assert exc_info.value.code == "empty_pairwise_targets"


def test_quality_training_source_does_not_import_cdf_or_use_graph_targets() -> None:
    source = (ROOT / "ai_mesh_generator" / "amg" / "training" / "quality.py").read_text(encoding="utf-8")

    assert "import cad_dataset_factory" not in source
    assert "from cad_dataset_factory" not in source
    assert "reference_midsurface" not in source
    assert "target_action_id" not in source
    assert "target_edge_length_mm" not in source
