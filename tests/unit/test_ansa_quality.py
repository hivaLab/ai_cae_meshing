from __future__ import annotations

from ai_mesh_generator.meshing.ansa_quality import (
    count_quality_issue_words,
    normalize_write_statistics_status,
    parse_quality_report,
    summarize_ansa_quality_statistics,
)


def test_normalize_write_statistics_status_uses_ansa_contract():
    assert normalize_write_statistics_status(2)["state"] == "completed_without_errors"
    assert normalize_write_statistics_status(1)["state"] == "completed_with_quality_issues"
    assert normalize_write_statistics_status(0)["state"] == "statistics_unavailable"
    assert normalize_write_statistics_status(None)["state"] == "not_available"


def test_quality_statistics_summary_flags_reported_issues(tmp_path):
    good = tmp_path / "good.html"
    bad = tmp_path / "bad.html"
    good.write_text("Completed with 0 errors and 0 violations", encoding="utf-8")
    bad.write_text("Quality violation: unmeshed macro remains", encoding="utf-8")

    summary = summarize_ansa_quality_statistics(
        [
            {"part_uid": "part_a", "status": "ran", "write_statistics_status": 2, "statistics_report_file": str(good)},
            {"part_uid": "part_b", "status": "ran", "write_statistics_status": 1, "statistics_report_file": str(bad)},
        ]
    )

    assert summary["passed"] is False
    assert summary["issue_record_count"] == 1
    assert summary["status_counts"]["completed_without_errors"] == 1
    assert summary["status_counts"]["completed_with_quality_issues"] == 1
    assert count_quality_issue_words(good.read_text(encoding="utf-8")) == 0


def test_quality_statistics_trusts_ansa_success_status_over_static_report_words(tmp_path):
    report = tmp_path / "statistics.html"
    report.write_text("Template section: errors and violations columns", encoding="utf-8")

    summary = summarize_ansa_quality_statistics(
        [{"part_uid": "part_a", "status": "ran", "write_statistics_status": 2, "statistics_report_file": str(report)}]
    )

    assert summary["passed"] is True
    assert summary["file_issue_word_count"] == 0


def test_quality_statistics_missing_report_is_explicit_failure(tmp_path):
    missing = tmp_path / "missing_statistics.html"

    summary = summarize_ansa_quality_statistics(
        [{"part_uid": "part_a", "status": "ran", "write_statistics_status": 2, "statistics_report_file": str(missing)}]
    )

    assert summary["passed"] is False
    assert summary["issue_record_count"] == 1
    assert summary["issue_records"][0]["report_error"] == "quality statistics report file is missing"


def test_quality_report_parser_extracts_issue_terms_for_failed_status(tmp_path):
    report = tmp_path / "bad_statistics.html"
    report.write_text("Fatal error: unmeshed macro and quality violation remain", encoding="utf-8")

    parsed = parse_quality_report(report, scan_issue_terms=True)

    assert parsed["exists"] is True
    assert parsed["parsed"] is True
    assert parsed["issue_count"] > 0
    assert parsed["issue_terms"]["fatal"] == 1
