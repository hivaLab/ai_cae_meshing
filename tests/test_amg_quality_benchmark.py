from __future__ import annotations

import json
import shutil
from pathlib import Path

from ai_mesh_generator.amg.benchmark.quality import build_quality_benchmark_report, main, write_quality_benchmark_report

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_quality_benchmark"


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(sample_id: str, *, action: str, length: float) -> dict:
    controls = {"edge_target_length_mm": length, "circumferential_divisions": 12, "radial_growth_rate": 1.25}
    if action == "KEEP_WITH_WASHER":
        controls.update({"washer_rings": 2, "washer_outer_radius_mm": 8.0})
    if action == "SUPPRESS":
        controls = {"suppression_rule": "quality_exploration_action_swap"}
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
                "feature_id": "HOLE_0001",
                "type": "HOLE",
                "role": "BOLT" if action == "KEEP_WITH_WASHER" else "RELIEF",
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


def _write_fixture(name: str, *, blocked: bool = False) -> tuple[Path, Path, Path]:
    root = _fresh(RUNS / name)
    dataset = root / "dataset"
    quality = root / "quality_exploration"
    training = root / "training"
    records = []
    for index, (action, score, status) in enumerate(
        [
            ("KEEP_REFINED", 10.0, "PASSED"),
            ("KEEP_WITH_WASHER", 6.0, "PASSED"),
            ("SUPPRESS", 40.0, "FAILED"),
        ],
        start=1,
    ):
        manifest_path = quality / "manifests" / f"candidate_{index}.json"
        _write_json(manifest_path, _manifest("sample_000001", action=action, length=1.5 + index))
        records.append(
            {
                "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
                "sample_id": "sample_000001",
                "evaluation_id": "baseline" if index == 1 else f"perturb_{index:03d}",
                "status": "BLOCKED" if blocked and index == 2 else status,
                "manifest_path": manifest_path.as_posix(),
                "quality_score": None if blocked and index == 2 else score,
                "accepted": status == "PASSED",
            }
        )
    _write_json(dataset / "dataset_index.json", {"schema": "CDF_DATASET_INDEX_SM_V1", "accepted_samples": [], "rejected_samples": []})
    _write_json(
        quality / "quality_exploration_summary.json",
        {
            "schema": "CDF_QUALITY_EXPLORATION_SUMMARY_V1",
            "status": "BLOCKED" if blocked else "SUCCESS",
            "dataset_root": dataset.as_posix(),
            "records": records,
            "quality_score_variance": 1.0,
        },
    )
    _write_json(
        training / "quality_training_metrics.json",
        {
            "schema": "AMG_QUALITY_TRAINING_METRICS_V1",
            "status": "SUCCESS",
            "example_count": 3,
            "train_pair_count": 2,
            "validation_pair_count": 1,
            "train_pairwise_accuracy": 1.0,
            "validation_pairwise_accuracy": 1.0,
            "quality_score_variance": 100.0,
            "checkpoint_path": (training / "quality_ranker_checkpoint.pt").as_posix(),
        },
    )
    return dataset, quality, training


def test_quality_benchmark_requires_information_not_sample_count() -> None:
    dataset, quality, training = _write_fixture("success")

    report = build_quality_benchmark_report(dataset=dataset, quality_exploration=quality, training=training)

    assert report["status"] == "SUCCESS"
    assert report["coverage"]["action_entropy_bits"] > 0.0
    assert report["coverage"]["control_value_variance"] > 0.0
    assert report["quality_evidence"]["quality_score_variance"] > 0.0
    assert report["quality_evidence"]["same_geometry_quality_delta_mean"] > 0.01
    assert report["success_criteria"]["same_geometry_quality_delta_meaningful"] is True
    assert report["success_criteria"]["held_out_pairwise_accuracy_above_random"] is True


def test_quality_benchmark_fails_when_metrics_are_blocked() -> None:
    dataset, quality, training = _write_fixture("blocked", blocked=True)

    report = build_quality_benchmark_report(dataset=dataset, quality_exploration=quality, training=training)

    assert report["status"] == "FAILED"
    assert report["quality_evidence"]["blocked_count"] == 1
    assert report["success_criteria"]["no_blocked_quality_records"] is False


def test_quality_benchmark_rejects_geometry_only_variance() -> None:
    dataset, quality, training = _write_fixture("geometry_only")
    summary_path = quality / "quality_exploration_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for record in summary["records"]:
        if record["evaluation_id"] != "baseline":
            record["quality_score"] = 10.000001
        else:
            record["quality_score"] = 10.0
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = build_quality_benchmark_report(dataset=dataset, quality_exploration=quality, training=training)

    assert report["status"] == "FAILED"
    assert report["quality_evidence"]["same_geometry_quality_delta_mean"] < 0.01
    assert report["success_criteria"]["same_geometry_quality_delta_meaningful"] is False


def test_quality_benchmark_cli_writer_and_source_boundaries() -> None:
    dataset, quality, training = _write_fixture("cli")
    out = RUNS / "cli" / "quality_benchmark.json"

    assert main(["--dataset", str(dataset), "--quality-exploration", str(quality), "--training", str(training), "--out", str(out)]) == 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["status"] == "SUCCESS"

    writer_out = RUNS / "writer" / "quality_benchmark.json"
    write_quality_benchmark_report(writer_out, {"schema": "AMG_QUALITY_BENCHMARK_REPORT_V1", "status": "FAILED"})
    assert json.loads(writer_out.read_text(encoding="utf-8"))["status"] == "FAILED"

    source = (ROOT / "ai_mesh_generator" / "amg" / "benchmark" / "quality.py").read_text(encoding="utf-8")
    assert "import cad_dataset_factory" not in source
    assert "from cad_dataset_factory" not in source
    assert "reference_midsurface" not in source
    assert "target_action_id" not in source
    assert "target_edge_length_mm" not in source
