from __future__ import annotations

import json
import shutil
from pathlib import Path

from ai_mesh_generator.amg.benchmark.real_pipeline import build_real_pipeline_benchmark_report, main, write_real_pipeline_benchmark_report

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_amg_real_pipeline_benchmark"


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(sample_id: str, part_class: str, features: list[dict]) -> dict:
    return {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "part": {
            "part_name": f"SMT_{sample_id}",
            "part_class": part_class,
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
        "features": features,
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def _feature(feature_id: str, feature_type: str, role: str, action: str) -> dict:
    controls_by_action = {
        "KEEP_REFINED": {"edge_target_length_mm": 2.0},
        "KEEP_WITH_BEND_ROWS": {"bend_target_length_mm": 2.0, "bend_rows": 2},
        "KEEP_WITH_FLANGE_SIZE": {"flange_target_length_mm": 3.0, "min_elements_across_width": 2},
    }
    return {
        "feature_id": feature_id,
        "type": feature_type,
        "role": role,
        "action": action,
        "geometry_signature": {"geometry_signature": feature_id},
        "controls": controls_by_action[action],
    }


def _family_manifest(sample_id: str, case_index: int) -> dict:
    case = case_index % 8
    if case == 0:
        return _manifest(sample_id, "SM_FLAT_PANEL", [_feature("HOLE_UNKNOWN_0001", "HOLE", "UNKNOWN", "KEEP_REFINED")])
    if case == 1:
        return _manifest(sample_id, "SM_FLAT_PANEL", [_feature("SLOT_UNKNOWN_0001", "SLOT", "UNKNOWN", "KEEP_REFINED")])
    if case == 2:
        return _manifest(sample_id, "SM_FLAT_PANEL", [_feature("CUTOUT_PASSAGE_0001", "CUTOUT", "PASSAGE", "KEEP_REFINED")])
    if case == 3:
        return _manifest(
            sample_id,
            "SM_FLAT_PANEL",
            [
                _feature("HOLE_UNKNOWN_0001", "HOLE", "UNKNOWN", "KEEP_REFINED"),
                _feature("SLOT_UNKNOWN_0001", "SLOT", "UNKNOWN", "KEEP_REFINED"),
                _feature("CUTOUT_PASSAGE_0001", "CUTOUT", "PASSAGE", "KEEP_REFINED"),
            ],
        )
    part_classes = {
        4: "SM_SINGLE_FLANGE",
        5: "SM_L_BRACKET",
        6: "SM_U_CHANNEL",
        7: "SM_HAT_CHANNEL",
    }
    return _manifest(
        sample_id,
        part_classes[case],
        [
            _feature("BEND_STRUCTURAL_0001", "BEND", "STRUCTURAL", "KEEP_WITH_BEND_ROWS"),
            _feature("FLANGE_STRUCTURAL_0001", "FLANGE", "STRUCTURAL", "KEEP_WITH_FLANGE_SIZE"),
        ],
    )


def _write_dataset(root: Path, sample_count: int = 150, *, family: bool = False) -> Path:
    dataset = _fresh(root / "dataset")
    accepted = []
    for index in range(1, sample_count + 1):
        sample_id = f"sample_{index:06d}"
        sample_dir = dataset / "samples" / sample_id
        if family:
            manifest = _family_manifest(sample_id, index - 1)
        elif index <= 30:
            manifest = _manifest(sample_id, "SM_FLAT_PANEL", [_feature("HOLE_UNKNOWN_0001", "HOLE", "UNKNOWN", "KEEP_REFINED")])
        elif index <= 60:
            manifest = _manifest(sample_id, "SM_FLAT_PANEL", [_feature("SLOT_UNKNOWN_0001", "SLOT", "UNKNOWN", "KEEP_REFINED")])
        elif index <= 90:
            manifest = _manifest(sample_id, "SM_FLAT_PANEL", [_feature("CUTOUT_PASSAGE_0001", "CUTOUT", "PASSAGE", "KEEP_REFINED")])
        elif index <= 120:
            manifest = _manifest(
                sample_id,
                "SM_FLAT_PANEL",
                [
                    _feature("HOLE_UNKNOWN_0001", "HOLE", "UNKNOWN", "KEEP_REFINED"),
                    _feature("SLOT_UNKNOWN_0001", "SLOT", "UNKNOWN", "KEEP_REFINED"),
                    _feature("CUTOUT_PASSAGE_0001", "CUTOUT", "PASSAGE", "KEEP_REFINED"),
                ],
            )
        else:
            manifest = _manifest(
                sample_id,
                "SM_L_BRACKET",
                [
                    _feature("BEND_STRUCTURAL_0001", "BEND", "STRUCTURAL", "KEEP_WITH_BEND_ROWS"),
                    _feature("FLANGE_STRUCTURAL_0001", "FLANGE", "STRUCTURAL", "KEEP_WITH_FLANGE_SIZE"),
                ],
            )
        _write_json(sample_dir / "labels" / "amg_manifest.json", manifest)
        accepted.append({"sample_id": sample_id, "sample_dir": f"samples/{sample_id}"})
    _write_json(
        dataset / "dataset_index.json",
        {"schema": "CDF_DATASET_INDEX_SM_V1", "accepted_samples": accepted, "rejected_samples": []},
    )
    (dataset / "splits").mkdir(parents=True, exist_ok=True)
    train_count = int(0.70 * sample_count)
    val_count = int(0.15 * sample_count)
    (dataset / "splits" / "train.txt").write_text("".join(f"sample_{index:06d}\n" for index in range(1, train_count + 1)), encoding="utf-8")
    (dataset / "splits" / "val.txt").write_text("".join(f"sample_{index:06d}\n" for index in range(train_count + 1, train_count + val_count + 1)), encoding="utf-8")
    (dataset / "splits" / "test.txt").write_text("".join(f"sample_{index:06d}\n" for index in range(train_count + val_count + 1, sample_count + 1)), encoding="utf-8")
    return dataset


def _write_training(root: Path, *, sample_count: int = 150) -> Path:
    training = root / "training"
    _write_json(
        training / "metrics.json",
        {
            "status": "SUCCESS",
            "sample_count": sample_count,
            "candidate_count": 210,
            "manifest_feature_count": 210,
            "matched_target_count": 210,
            "label_coverage_ratio": 1.0,
            "train_loss_total": 0.1,
            "val_loss_total": 0.2,
            "checkpoint_path": (training / "checkpoint.pt").as_posix(),
        },
    )
    return training


def _write_inference(root: Path, *, placeholder: bool = False, sample_ids: list[str] | None = None, failed_sample_ids: set[str] | None = None) -> Path:
    inference = root / "inference"
    sample_results = []
    selected_ids = sample_ids or [f"sample_{index:06d}" for index in range(128, 151)]
    failed = failed_sample_ids or set()
    for offset, sample_id in enumerate(selected_ids):
        sample_dir = inference / "samples" / sample_id
        if sample_id in failed:
            sample_results.append(
                {
                    "sample_id": sample_id,
                    "status": "MODEL_REJECTED",
                    "attempts": 0,
                    "sample_output_dir": sample_dir.as_posix(),
                    "error_code": "family_rate_test_failure",
                    "message": "forced family failure",
                }
            )
            continue
        _write_json(
            sample_dir / "reports" / "ansa_execution_report.json",
            {
                "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
                "sample_id": sample_id,
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
            },
        )
        _write_json(
            sample_dir / "reports" / "ansa_quality_report.json",
            {
                "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
                "sample_id": sample_id,
                "accepted": True,
                "mesh_stats": {"num_shell_elements": 10},
                "quality": {"num_hard_failed_elements": 0},
                "feature_checks": [],
            },
        )
        mesh = sample_dir / "meshes" / "ansa_oracle_mesh.bdf"
        mesh.parent.mkdir(parents=True, exist_ok=True)
        mesh.write_text("placeholder mesh\n" if placeholder and offset == 0 else "CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
        sample_results.append(
            {
                "sample_id": sample_id,
                "status": "VALID_MESH",
                "attempts": 1,
                "sample_output_dir": sample_dir.as_posix(),
                "execution_report_path": (sample_dir / "reports" / "ansa_execution_report.json").as_posix(),
                "quality_report_path": (sample_dir / "reports" / "ansa_quality_report.json").as_posix(),
                "solver_deck_path": mesh.as_posix(),
                "inference_report_path": (sample_dir / "reports" / "amg_inference_report.json").as_posix(),
            }
        )
    _write_json(
        inference / "inference_summary.json",
        {
            "schema": "AMG_REAL_INFERENCE_SUMMARY_V1",
            "status": "SUCCESS",
            "attempted_count": len(sample_results),
            "success_count": len(sample_results),
            "failed_count": 0,
            "retry_count": 0,
            "failure_reason_counts": {},
            "sample_results": sample_results,
        },
    )
    return inference


def test_benchmark_report_aggregates_coverage_and_real_mesh_success() -> None:
    root = _fresh(RUNS / "success")
    dataset = _write_dataset(root)
    training = _write_training(root)
    inference = _write_inference(root)

    report = build_real_pipeline_benchmark_report(dataset=dataset, training=training, inference=inference)

    assert report["status"] == "SUCCESS"
    assert report["coverage"]["split_counts"] == {"train": 105, "val": 22, "test": 23}
    assert set(report["coverage"]["feature_type_histogram"]) == {"BEND", "CUTOUT", "FLANGE", "HOLE", "SLOT"}
    assert report["inference"]["attempted_count"] == 23
    assert report["inference"]["after_retry_valid_mesh_rate"] == 1.0


def test_family_expansion_profile_reports_per_family_success_rates() -> None:
    root = _fresh(RUNS / "family_success")
    dataset = _write_dataset(root, sample_count=240, family=True)
    training = _write_training(root, sample_count=240)
    test_ids = [f"sample_{index:06d}" for index in range(205, 241)]
    inference = _write_inference(root, sample_ids=test_ids)

    report = build_real_pipeline_benchmark_report(
        dataset=dataset,
        training=training,
        inference=inference,
        profile="sm_family_expansion_v1",
    )

    assert report["status"] == "SUCCESS"
    assert report["coverage"]["split_counts"] == {"train": 168, "val": 36, "test": 36}
    assert set(report["coverage"]["part_class_histogram"]) == {
        "SM_FLAT_PANEL",
        "SM_SINGLE_FLANGE",
        "SM_L_BRACKET",
        "SM_U_CHANNEL",
        "SM_HAT_CHANNEL",
    }
    assert set(report["inference"]["per_part_class"]) == {
        "SM_FLAT_PANEL",
        "SM_SINGLE_FLANGE",
        "SM_L_BRACKET",
        "SM_U_CHANNEL",
        "SM_HAT_CHANNEL",
    }
    assert report["success_criteria"]["per_required_family_valid_mesh_rate_at_least_0_80"] is True


def test_family_expansion_profile_fails_when_required_family_rate_is_low() -> None:
    root = _fresh(RUNS / "family_low_rate")
    dataset = _write_dataset(root, sample_count=240, family=True)
    training = _write_training(root, sample_count=240)
    test_ids = [f"sample_{index:06d}" for index in range(205, 241)]
    hat_failures = {sample_id for sample_id in test_ids if (int(sample_id.rsplit("_", 1)[1]) - 1) % 8 == 7}
    inference = _write_inference(root, sample_ids=test_ids, failed_sample_ids=hat_failures)

    report = build_real_pipeline_benchmark_report(
        dataset=dataset,
        training=training,
        inference=inference,
        profile="sm_family_expansion_v1",
    )

    assert report["status"] == "FAILED"
    assert report["inference"]["per_part_class"]["SM_HAT_CHANNEL"]["after_retry_valid_mesh_rate"] == 0.0
    assert report["success_criteria"]["per_required_family_valid_mesh_rate_at_least_0_80"] is False


def test_benchmark_report_does_not_count_placeholder_mesh_as_success() -> None:
    root = _fresh(RUNS / "placeholder")
    dataset = _write_dataset(root)
    training = _write_training(root)
    inference = _write_inference(root, placeholder=True)

    report = build_real_pipeline_benchmark_report(dataset=dataset, training=training, inference=inference)

    assert report["status"] == "SUCCESS"
    assert report["inference"]["valid_mesh_count"] == 22
    assert report["inference"]["failure_reason_counts"] == {"missing_or_placeholder_mesh": 1}


def test_benchmark_cli_writes_report() -> None:
    root = _fresh(RUNS / "cli")
    dataset = _write_dataset(root)
    training = _write_training(root)
    inference = _write_inference(root)
    out = root / "benchmark_report.json"

    assert main(["--dataset", str(dataset), "--training", str(training), "--inference", str(inference), "--out", str(out)]) == 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["status"] == "SUCCESS"


def test_benchmark_report_writer_and_source_boundaries() -> None:
    out = _fresh(RUNS / "writer") / "benchmark_report.json"
    write_real_pipeline_benchmark_report(out, {"schema": "AMG_REAL_PIPELINE_BENCHMARK_REPORT_V1", "status": "FAILED"})
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "FAILED"

    source = (ROOT / "ai_mesh_generator" / "amg" / "benchmark" / "real_pipeline.py").read_text(encoding="utf-8")
    assert "import cad_dataset_factory" not in source
    assert "from cad_dataset_factory" not in source
    assert "reference_midsurface" not in source
    assert "target_action_id" not in source
    assert "target_edge_length_mm" not in source
