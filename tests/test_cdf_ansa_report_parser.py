from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dataset_factory.cdf.oracle import (
    AnsaReportParseError,
    parse_ansa_execution_report,
    parse_ansa_quality_report,
    summarize_ansa_reports,
)
from cad_dataset_factory.cdf.oracle.ansa_scripts import cdf_ansa_oracle

ROOT = Path(__file__).resolve().parents[1]


def _execution_report(sample_id: str = "sample_000403", *, accepted: bool = True) -> dict:
    return {
        "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
        "sample_id": sample_id,
        "accepted": accepted,
        "ansa_version": "mock-ansa",
        "step_import_success": accepted,
        "geometry_cleanup_success": accepted,
        "midsurface_extraction_success": accepted,
        "feature_matching_success": accepted,
        "batch_mesh_success": accepted,
        "solver_export_success": accepted,
        "runtime_sec": 12.5,
        "outputs": {
            "solver_deck": "meshes/ansa_oracle_mesh.bdf",
        },
    }


def _quality_report(
    sample_id: str = "sample_000403",
    *,
    accepted: bool = True,
    hard_failed: int = 0,
    boundary_error: float = 0.038,
) -> dict:
    return {
        "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
        "sample_id": sample_id,
        "accepted": accepted,
        "mesh_stats": {
            "num_nodes": 821,
            "num_shell_elements": 764,
            "quad_ratio": 0.92,
            "tria_ratio": 0.08,
        },
        "quality": {
            "num_hard_failed_elements": hard_failed,
            "min_angle_deg": 24.6,
            "max_angle_deg": 151.0,
            "max_aspect_ratio": 4.8,
            "max_warpage_deg": 8.4,
            "max_skewness": 0.63,
            "min_jacobian": 0.78,
        },
        "feature_checks": [
            {
                "feature_id": "HOLE_BOLT_0001",
                "type": "HOLE",
                "target_divisions": 24,
                "measured_divisions": 24,
                "target_edge_length_mm": 1.047,
                "measured_boundary_length_mm": 1.09,
                "boundary_size_error": boundary_error,
            },
            {
                "feature_id": "BEND_STRUCTURAL_0001",
                "type": "BEND",
                "bend_row_error": 0,
            },
        ],
    }


def test_schema_valid_execution_report_parses() -> None:
    parsed = parse_ansa_execution_report(_execution_report())

    assert parsed.sample_id == "sample_000403"
    assert parsed.accepted is True
    assert parsed.step_import_success is True
    assert parsed.runtime_sec == 12.5
    assert parsed.outputs["solver_deck"] == "meshes/ansa_oracle_mesh.bdf"


def test_schema_valid_quality_report_parses_boundary_errors() -> None:
    parsed = parse_ansa_quality_report(_quality_report(hard_failed=2, boundary_error=-0.125))

    assert parsed.sample_id == "sample_000403"
    assert parsed.num_hard_failed_elements == 2
    assert len(parsed.feature_boundary_errors) == 1
    assert parsed.feature_boundary_errors[0].feature_id == "HOLE_BOLT_0001"
    assert parsed.feature_boundary_errors[0].boundary_size_error == -0.125
    assert parsed.max_boundary_size_error == 0.125


def test_parser_accepts_report_file_paths() -> None:
    root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_report_parser"
    root.mkdir(parents=True, exist_ok=True)
    execution_path = root / "ansa_execution_report.json"
    quality_path = root / "ansa_quality_report.json"
    execution_path.write_text(json.dumps(_execution_report()) + "\n", encoding="utf-8")
    quality_path.write_text(json.dumps(_quality_report()) + "\n", encoding="utf-8")

    execution = parse_ansa_execution_report(execution_path)
    quality = parse_ansa_quality_report(quality_path)
    summary = summarize_ansa_reports(execution, quality)

    assert summary.accepted is True
    assert summary.failed_phases == []


def test_summary_preserves_report_failures_without_threshold_recalculation() -> None:
    execution = parse_ansa_execution_report(_execution_report(accepted=False))
    quality = parse_ansa_quality_report(_quality_report(accepted=False, hard_failed=7))

    summary = summarize_ansa_reports(execution, quality)

    assert summary.accepted is False
    assert summary.execution_accepted is False
    assert summary.quality_accepted is False
    assert summary.num_hard_failed_elements == 7
    assert "step_import" in summary.failed_phases
    assert "quality_report" in summary.failed_phases


def test_summary_rejects_sample_id_mismatch() -> None:
    execution = parse_ansa_execution_report(_execution_report("sample_a"))
    quality = parse_ansa_quality_report(_quality_report("sample_b"))

    with pytest.raises(AnsaReportParseError) as exc_info:
        summarize_ansa_reports(execution, quality)
    assert exc_info.value.code == "sample_id_mismatch"


def test_schema_invalid_report_raises_structured_error() -> None:
    report = _execution_report()
    report["schema"] = "WRONG_SCHEMA"

    with pytest.raises(AnsaReportParseError) as exc_info:
        parse_ansa_execution_report(report)
    assert exc_info.value.code == "schema_validation_failed"


def test_quality_report_requires_hard_fail_metric() -> None:
    report = _quality_report()
    del report["quality"]["num_hard_failed_elements"]

    with pytest.raises(AnsaReportParseError) as exc_info:
        parse_ansa_quality_report(report)
    assert exc_info.value.code == "missing_quality_metric"


def test_controlled_failure_execution_report_from_t402_parses() -> None:
    sample_dir = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_report_parser" / "samples" / "sample_000402"
    (sample_dir / "labels").mkdir(parents=True, exist_ok=True)
    (sample_dir / "labels" / "amg_manifest.json").write_text(
        '{"schema_version":"AMG_MANIFEST_SM_V1","status":"VALID"}\n',
        encoding="utf-8",
    )
    argv = [
        "--sample-dir",
        sample_dir.as_posix(),
        "--manifest",
        (sample_dir / "labels" / "amg_manifest.json").as_posix(),
        "--execution-report",
        (sample_dir / "reports" / "ansa_execution_report.json").as_posix(),
        "--quality-report",
        (sample_dir / "reports" / "ansa_quality_report.json").as_posix(),
        "--batch-mesh-session",
        "AMG_SHELL_CONST_THICKNESS_V1",
        "--quality-profile",
        "AMG_QA_SHELL_V1",
        "--solver-deck",
        "NASTRAN",
        "--save-ansa-database",
        "true",
    ]

    cdf_ansa_oracle.main(argv)
    parsed = parse_ansa_execution_report(sample_dir / "reports" / "ansa_execution_report.json")

    assert parsed.sample_id == "sample_000402"
    assert parsed.accepted is False
    assert parsed.outputs["controlled_failure_reason"] == "ansa_api_unavailable"
