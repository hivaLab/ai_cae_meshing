from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_mesh_generator.amg.benchmark.recommendation import build_recommendation_benchmark_report, write_recommendation_benchmark_report
from ai_mesh_generator.amg.dataset import load_amg_dataset_sample
from ai_mesh_generator.amg.quality_features import build_quality_feature_vector
from ai_mesh_generator.amg.recommendation.quality import (
    AmgQualityRecommendationError,
    QualityRecommendationConfig,
    load_candidate_manifests,
    load_quality_ranker,
    run_quality_recommendation,
    score_candidate_manifests,
    select_recommendation_samples,
)
from ai_mesh_generator.amg.training.quality import QualityControlRanker

pytestmark = pytest.mark.model

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_quality_recommendation"

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


def _manifest(sample_id: str, *, edge_length: float) -> dict:
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
                "action": "KEEP_REFINED",
                "geometry_signature": {"geometry_signature": f"HOLE:{sample_id}"},
                "controls": {
                    "edge_target_length_mm": edge_length,
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


def _write_graph(sample_dir: Path) -> None:
    _write_json(
        sample_dir / "graph" / "graph_schema.json",
        {
            "schema_version": "AMG_BREP_GRAPH_SM_V1",
            "node_types": ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"],
            "edge_types": EDGE_TYPES,
            "feature_candidate_columns": FEATURE_COLUMNS,
        },
    )
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
    sample_dir.joinpath("graph").mkdir(parents=True, exist_ok=True)
    np.savez(sample_dir / "graph" / "brep_graph.npz", **arrays)


def _write_fixture(name: str, *, sample_count: int = 1, empty_test_split: bool = False) -> tuple[Path, Path, Path]:
    root = _fresh(RUNS / name)
    dataset = root / "dataset"
    quality = root / "quality_exploration"
    training = root / "training"
    accepted = []
    records = []
    for index in range(1, sample_count + 1):
        sample_id = f"sample_{index:06d}"
        sample = dataset / "samples" / sample_id
        _write_graph(sample)
        _write_json(sample / "labels" / "amg_manifest.json", _manifest(sample_id, edge_length=2.0))
        (sample / "cad").mkdir(parents=True, exist_ok=True)
        (sample / "cad" / "input.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        accepted.append({"sample_id": sample_id, "sample_dir": f"samples/{sample_id}"})
        perturb_path = quality / "samples" / sample_id / "perturb_001" / "labels" / "amg_manifest.json"
        _write_json(perturb_path, _manifest(sample_id, edge_length=5.0))
        records.extend(
            [
                {
                    "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
                    "sample_id": sample_id,
                    "evaluation_id": "baseline",
                    "status": "FAILED",
                    "manifest_path": (sample / "labels" / "amg_manifest.json").as_posix(),
                    "quality_score": -999999.0,
                    "accepted": False,
                },
                {
                    "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
                    "sample_id": sample_id,
                    "evaluation_id": "perturb_001",
                    "status": "PASSED",
                    "manifest_path": perturb_path.as_posix(),
                    "quality_score": 999999.0,
                    "accepted": True,
                },
            ]
        )
    _write_json(dataset / "dataset_index.json", {"schema": "CDF_DATASET_INDEX_SM_V1", "accepted_samples": accepted, "rejected_samples": []})
    (dataset / "splits").mkdir(parents=True, exist_ok=True)
    split_ids = "" if empty_test_split else "".join(f"sample_{index:06d}\n" for index in range(1, sample_count + 1))
    (dataset / "splits" / "test.txt").write_text(split_ids, encoding="utf-8")
    _write_json(quality / "quality_exploration_summary.json", {"schema": "CDF_QUALITY_EXPLORATION_SUMMARY_V1", "status": "SUCCESS", "records": records})
    sample = load_amg_dataset_sample(dataset / "samples" / "sample_000001")
    base_vector = build_quality_feature_vector(sample, _manifest("sample_000001", edge_length=2.0))
    perturb_vector = build_quality_feature_vector(sample, _manifest("sample_000001", edge_length=5.0))
    target_index = int(np.argmax(np.abs(perturb_vector - base_vector)))
    model = QualityControlRanker(input_dim=int(base_vector.shape[0]), hidden_dim=4)
    for parameter in model.parameters():
        parameter.data.zero_()
    model.network[0].weight.data[0, target_index] = 1.0
    model.network[2].weight.data[0, 0] = 1.0
    model.network[4].weight.data[0, 0] = -1.0
    training.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state": model.state_dict(), "input_dim": int(base_vector.shape[0]), "hidden_dim": 4}, training / "quality_ranker_checkpoint.pt")
    return dataset, quality, training


def _payload(command: list[str]) -> dict:
    token = next(item for item in command if item.startswith("-process_string:"))
    encoded = token.split(":", 1)[1]
    encoded += "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))


def _fake_subprocess_run(command, capture_output=True, text=True, timeout=None, check=False):
    payload = _payload(command)
    manifest = json.loads(Path(payload["manifest"]).read_text(encoding="utf-8"))
    edge_length = float(manifest["features"][0]["controls"]["edge_target_length_mm"])
    spread = 0.8 if edge_length < 3.0 else 0.1
    execution_path = Path(payload["execution_report"])
    quality_path = Path(payload["quality_report"])
    mesh_path = Path(payload["sample_dir"]) / "meshes" / "ansa_oracle_mesh.bdf"
    _write_json(
        execution_path,
        {
            "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
            "sample_id": Path(payload["sample_dir"]).name,
            "accepted": True,
            "ansa_version": "ANSA_v25.1.0",
            "runtime_sec": 1.0,
            "outputs": {"solver_deck": "meshes/ansa_oracle_mesh.bdf"},
        },
    )
    _write_json(
        quality_path,
        {
            "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
            "sample_id": Path(payload["sample_dir"]).name,
            "accepted": True,
            "mesh_stats": {"num_shell_elements": 20},
            "quality": {
                "num_hard_failed_elements": 0,
                "num_shell_elements": 20,
                "side_length_spread_ratio": spread,
                "aspect_ratio_proxy_max": 1.0 + spread,
                "triangles_percent": 0.0,
                "violating_shell_elements_total": 0,
            },
            "feature_checks": [],
        },
    )
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    mesh_path.write_text("CEND\nBEGIN BULK\nGRID,1\nENDDATA\n", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_quality_ranker_scores_candidates_without_label_leakage() -> None:
    dataset, quality, training = _write_fixture("score")
    sample = load_amg_dataset_sample(dataset / "samples" / "sample_000001")
    ranker = load_quality_ranker(training)
    candidates = load_candidate_manifests(quality_exploration_root=quality, sample_id=sample.sample_id)

    scored = score_candidate_manifests(sample, candidates, ranker)

    assert scored[0].evaluation_id == "perturb_001"
    assert scored[0].predicted_score < scored[1].predicted_score
    assert "quality_score" not in scored[0].__dict__
    assert "status" not in scored[0].__dict__


def test_run_quality_recommendation_writes_separate_real_evidence(monkeypatch) -> None:
    dataset, quality, training = _write_fixture("run")
    out = RUNS / "run" / "recommendation"
    ansa = RUNS / "run" / "ansa64.bat"
    ansa.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr("ai_mesh_generator.amg.recommendation.quality.subprocess.run", _fake_subprocess_run)

    result = run_quality_recommendation(
        QualityRecommendationConfig(
            dataset_root=dataset,
            quality_exploration_root=quality,
            training_root=training,
            output_dir=out,
            ansa_executable=ansa,
        )
    )

    assert result.status == "SUCCESS"
    assert result.valid_pair_count == 1
    assert result.improved_count == 1
    report = json.loads(Path(result.sample_results[0].report_path).read_text(encoding="utf-8"))
    assert report["selected_evaluation_id"] == "perturb_001"
    assert report["improvement_delta"] > 0.01
    assert (out / "samples" / "sample_000001" / "baseline" / "meshes" / "ansa_oracle_mesh.bdf").is_file()
    assert (out / "samples" / "sample_000001" / "recommended" / "meshes" / "ansa_oracle_mesh.bdf").is_file()


def test_recommendation_benchmark_accepts_real_improvement_and_rejects_placeholder(monkeypatch) -> None:
    dataset, quality, training = _write_fixture("benchmark", sample_count=6)
    out = RUNS / "benchmark" / "recommendation"
    ansa = RUNS / "benchmark" / "ansa64.bat"
    ansa.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr("ai_mesh_generator.amg.recommendation.quality.subprocess.run", _fake_subprocess_run)
    result = run_quality_recommendation(
        QualityRecommendationConfig(
            dataset_root=dataset,
            quality_exploration_root=quality,
            training_root=training,
            output_dir=out,
            ansa_executable=ansa,
        )
    )

    report = build_recommendation_benchmark_report(recommendation=out)
    baseline_path = RUNS / "benchmark" / "baseline_benchmark.json"
    write_recommendation_benchmark_report(baseline_path, report)
    compared = build_recommendation_benchmark_report(recommendation=out, baseline=baseline_path)

    assert result.valid_pair_count == 6
    assert report["status"] == "SUCCESS"
    assert report["improvement_rate"] == 1.0
    assert compared["status"] == "SUCCESS"
    assert compared["baseline_comparison"]["improvement_rate_delta"] == 0.0
    assert compared["median_improvement_delta"] == report["median_improvement_delta"]
    first_mesh = out / "samples" / "sample_000001" / "recommended" / "meshes" / "ansa_oracle_mesh.bdf"
    first_mesh.write_text("placeholder mesh\n", encoding="utf-8")
    rejected = build_recommendation_benchmark_report(recommendation=out)
    assert rejected["status"] == "FAILED"
    assert rejected["success_criteria"]["no_invalid_artifacts"] is False


def test_recommendation_rejects_empty_test_split_and_source_boundaries() -> None:
    dataset, _quality, _training = _write_fixture("empty", empty_test_split=True)

    with pytest.raises(AmgQualityRecommendationError) as exc_info:
        select_recommendation_samples(dataset)

    assert exc_info.value.code == "empty_recommendation_selection"
    for relative in (
        "ai_mesh_generator/amg/recommendation/quality.py",
        "ai_mesh_generator/amg/benchmark/recommendation.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "import cad_dataset_factory" not in source
        assert "from cad_dataset_factory" not in source
        assert "reference_midsurface" not in source
        assert "target_action_id" not in source
        assert "target_edge_length_mm" not in source
