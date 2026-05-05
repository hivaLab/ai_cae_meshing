from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from cad_dataset_factory.cdf.oracle.ansa_scripts.cdf_ansa_api_layer import _parse_statistics_report
from cad_dataset_factory.cdf.pipeline.e2e_dataset import generate_dataset, validate_dataset
from cad_dataset_factory.cdf.quality import CdfQualityExplorationError, compute_quality_score, perturb_manifest, run_quality_exploration

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_quality_exploration"


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(*, relief: bool = False) -> dict:
    feature = {
        "feature_id": "HOLE_RELIEF_0001" if relief else "HOLE_BOLT_0001",
        "type": "HOLE",
        "role": "RELIEF" if relief else "BOLT",
        "action": "KEEP_REFINED" if relief else "KEEP_WITH_WASHER",
        "geometry_signature": {"geometry_signature": "HOLE:fixture"},
        "controls": {
            "edge_target_length_mm": 2.0,
            "circumferential_divisions": 12,
            "radial_growth_rate": 1.25,
        },
    }
    if not relief:
        feature["controls"].update({"washer_rings": 2, "washer_outer_radius_mm": 8.0})
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
            "h_min_mm": 1.0,
            "h_max_mm": 6.0,
            "growth_rate_max": 1.35,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [feature],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }


def _quality_report(
    *,
    hard_failed: int = 0,
    spread: float = 0.5,
    violating: int | None = None,
    unmeshed: int = 0,
) -> dict:
    return {
        "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
        "sample_id": "sample_000001",
        "accepted": hard_failed == 0,
        "mesh_stats": {"num_shell_elements": 20},
        "quality": {
            "num_hard_failed_elements": hard_failed,
            "num_shell_elements": 20,
            "violating_shell_elements_total": hard_failed if violating is None else violating,
            "unmeshed_shell_count": unmeshed,
            "side_length_spread_ratio": spread,
            "aspect_ratio_proxy_max": 1.5 + spread,
            "triangles_percent": 4.0,
        },
        "feature_checks": [{"feature_id": "HOLE_BOLT_0001", "type": "HOLE", "boundary_size_error": 0.1}],
    }


def _execution_report() -> dict:
    return {
        "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
        "sample_id": "sample_000001",
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


def _write_dataset(root: Path) -> Path:
    dataset = _fresh(root / "dataset")
    sample = dataset / "samples" / "sample_000001"
    _write_json(sample / "labels" / "amg_manifest.json", _manifest())
    _write_json(sample / "reports" / "ansa_execution_report.json", _execution_report())
    _write_json(sample / "reports" / "ansa_quality_report.json", _quality_report(spread=0.4))
    (sample / "cad").mkdir(parents=True, exist_ok=True)
    (sample / "cad" / "input.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    mesh = sample / "meshes" / "ansa_oracle_mesh.bdf"
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    _write_json(
        dataset / "dataset_index.json",
        {
            "schema": "CDF_DATASET_INDEX_SM_V1",
            "accepted_samples": [{"sample_id": "sample_000001", "sample_dir": "samples/sample_000001"}],
            "rejected_samples": [],
        },
    )
    return dataset


def test_quality_score_requires_continuous_metrics() -> None:
    good = compute_quality_score(_quality_report(spread=0.25), _execution_report())
    bad = compute_quality_score(_quality_report(hard_failed=2, spread=2.0), _execution_report())

    assert bad > good
    with pytest.raises(CdfQualityExplorationError) as exc_info:
        compute_quality_score({"schema": "CDF_ANSA_QUALITY_REPORT_SM_V1", "quality": {"num_hard_failed_elements": 0}})
    assert exc_info.value.code == "quality_metric_unavailable"
    hard_fail_without_continuous = compute_quality_score(
        {"schema": "CDF_ANSA_QUALITY_REPORT_SM_V1", "quality": {"num_hard_failed_elements": 1}},
        _execution_report(),
    )
    assert hard_fail_without_continuous >= 1000.0


def test_perturb_manifest_produces_schema_valid_control_variants() -> None:
    baseline = _manifest(relief=True)

    scaled = perturb_manifest(baseline, {"kind": "edge_length_scale", "scale": 10.0})
    suppressed = perturb_manifest(baseline, {"kind": "suppress_small"})

    assert scaled["features"][0]["controls"]["edge_target_length_mm"] == 6.0
    assert suppressed["features"][0]["action"] == "SUPPRESS"
    assert baseline["features"][0]["action"] == "KEEP_REFINED"


def test_statistics_report_parser_extracts_continuous_quality_metrics() -> None:
    stats = RUNS / "statistics.html"
    stats.parent.mkdir(parents=True, exist_ok=True)
    stats.write_text(
        """
        <table>
          <tr><td>TOTAL</td><td>2.5</td><td>0</td><td>12.5%</td><td>3</td></tr>
          <tr><td>MIN</td><td>x</td><td>x</td><td>1.0</td></tr>
          <tr><td>AVERAGE</td><td>x</td><td>x</td><td>2.0</td></tr>
          <tr><td>MAX</td><td>x</td><td>x</td><td>4.0</td></tr>
        </table>
        """,
        encoding="utf-8",
    )

    metrics = _parse_statistics_report(stats)

    assert metrics["average_shell_length_mm"] == 2.5
    assert metrics["violating_shell_elements_total"] == 3
    assert metrics["side_length_spread_ratio"] == 1.5
    assert metrics["aspect_ratio_proxy_max"] == 4.0


def test_statistics_report_parser_ignores_overall_number_total_header() -> None:
    stats = RUNS / "statistics_with_multiple_totals.html"
    stats.parent.mkdir(parents=True, exist_ok=True)
    stats.write_text(
        """
        <table summary="Session-Parts Report Table">
          <tr><td>Name</td><td>Property ID</td><td>Session</td><td>Aver.Length Shells</td><td>Unmeshed</td><td>Triangles %</td><td>Total</td></tr>
          <tr><td>part</td><td>1</td><td>session</td><td>1.31</td><td>0</td><td>0.02</td><td>0</td></tr>
          <tr><td colspan="3"><b>TOTAL</b></td><td>1.31</td><td>0</td><td>0.02</td><td>0</td></tr>
        </table>
        <table summary="Statistics Report Table">
          <tr><td>TYPE</td><td>Tria</td><td>Quad</td><td>TOTAL</td></tr>
          <tr><td>NUMBER</td><td>0</td><td>9064</td><td>9064</td></tr>
        </table>
        """,
        encoding="utf-8",
    )

    metrics = _parse_statistics_report(stats)

    assert metrics["triangles_percent"] == 0.02
    assert metrics["violating_shell_elements_total"] == 0


def test_run_quality_exploration_records_real_failed_cases_without_hiding(monkeypatch) -> None:
    dataset = _write_dataset(_fresh(RUNS / "explore"))
    output = RUNS / "explore" / "quality"

    def fake_run_ansa_oracle(request, execute=True):
        _write_json(request.execution_report_path, _execution_report())
        _write_json(request.quality_report_path, _quality_report(hard_failed=1, spread=1.8))
        mesh = request.sample_dir / "meshes" / "ansa_oracle_mesh.bdf"
        mesh.parent.mkdir(parents=True, exist_ok=True)
        mesh.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
        return SimpleNamespace(status="COMPLETED", error_code=None)

    monkeypatch.setattr("cad_dataset_factory.cdf.quality.exploration.run_ansa_oracle", fake_run_ansa_oracle)

    result = run_quality_exploration(
        dataset_root=dataset,
        output_dir=output,
        ansa_executable=RUNS / "ansa64.bat",
        perturbations_per_sample=1,
    )

    summary = json.loads(Path(result.summary_path).read_text(encoding="utf-8"))
    assert result.status == "SUCCESS"
    assert result.baseline_count == 1
    assert result.evaluated_count == 1
    assert result.failed_count == 1
    assert result.quality_score_variance > 0.0
    assert {record["evaluation_id"] for record in summary["records"]} == {"baseline", "perturb_001"}


def test_run_quality_exploration_preserves_near_fail_quality_evidence(monkeypatch) -> None:
    dataset = _write_dataset(_fresh(RUNS / "near_fail"))
    output = RUNS / "near_fail" / "quality"

    def fake_run_ansa_oracle(request, execute=True):
        _write_json(request.execution_report_path, _execution_report())
        _write_json(request.quality_report_path, _quality_report(hard_failed=0, spread=1.4, violating=3, unmeshed=1))
        mesh = request.sample_dir / "meshes" / "ansa_oracle_mesh.bdf"
        mesh.parent.mkdir(parents=True, exist_ok=True)
        mesh.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
        return SimpleNamespace(status="COMPLETED", error_code=None)

    monkeypatch.setattr("cad_dataset_factory.cdf.quality.exploration.run_ansa_oracle", fake_run_ansa_oracle)

    result = run_quality_exploration(
        dataset_root=dataset,
        output_dir=output,
        ansa_executable=RUNS / "ansa64.bat",
        perturbations_per_sample=1,
    )

    summary = json.loads(Path(result.summary_path).read_text(encoding="utf-8"))
    perturb = next(record for record in summary["records"] if record["evaluation_id"] == "perturb_001")
    assert result.status == "SUCCESS"
    assert result.near_fail_count == 1
    assert summary["near_fail_count"] == 1
    assert perturb["status"] == "NEAR_FAIL"
    assert perturb["accepted"] is True
    assert perturb["quality_metrics_available"] is True


@pytest.mark.requires_ansa
def test_real_ansa_control_perturbations_change_same_geometry_quality() -> None:
    ansa_executable = os.environ.get("ANSA_EXECUTABLE")
    if not ansa_executable:
        pytest.skip("ANSA_EXECUTABLE is not configured")
    dataset = _fresh(RUNS / "real_control_response" / "dataset")
    quality = RUNS / "real_control_response" / "quality"

    generated = generate_dataset(
        config_path=ROOT / "configs" / "cdf_sm_ansa_v1.default.json",
        out_dir=dataset,
        count=1,
        seed=1708,
        require_ansa=True,
        env={**os.environ, "ANSA_EXECUTABLE": ansa_executable},
        profile="sm_quality_exploration_v1",
    )
    assert generated.status == "SUCCESS"
    assert validate_dataset(dataset_root=dataset, require_ansa=True).exit_code == 0

    result = run_quality_exploration(
        dataset_root=dataset,
        output_dir=quality,
        ansa_executable=ansa_executable,
        perturbations_per_sample=3,
    )

    summary = json.loads(Path(result.summary_path).read_text(encoding="utf-8"))
    scores = [float(record["quality_score"]) for record in summary["records"] if isinstance(record.get("quality_score"), (int, float))]
    assert len(scores) >= 2
    assert max(scores) - min(scores) >= 0.01
    control_reports = [
        json.loads(Path(record["execution_report_path"]).read_text(encoding="utf-8"))["outputs"]["controls_applied"][0]
        for record in summary["records"]
        if record.get("evaluation_id") != "baseline"
    ]
    assert any(report.get("bound_to_real_ansa_api") is True for report in control_reports)
