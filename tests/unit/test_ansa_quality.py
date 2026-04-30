from __future__ import annotations

from ai_mesh_generator.meshing.ansa_quality import (
    count_quality_issue_words,
    normalize_write_statistics_status,
    parse_numeric_quality_metrics,
    parse_quality_report,
    quality_threshold_violations,
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


def test_quality_report_parser_extracts_numeric_ansa_statistics(tmp_path):
    report = tmp_path / "statistics.html"
    report.write_text(
        """
        <html><body>
        <table summary="Session-Parts Report Table">
        <tr><td colspan="4">PARTS</td><td colspan="3">STATISTICS</td><td colspan="3">VIOLATING SHELL ELEMENTS</td></tr>
        <tr><td>Part</td><td>Aver.Length Shells</td><td>Unmeshed</td><td>Triangles %</td><td>Total</td><td>Min.Len.</td><td>Max.Len.</td></tr>
        <tr><td>TOTAL</td><td>12.5</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
        </table>
        <table summary="Statistics Report Table">
        <tr><td colspan="3">OVERALL NUMBERS of SHELL ELEMENTs / PERCENTAGE (%)</td></tr>
        <tr><td>TYPE</td><td>Quad</td><td>TOTAL</td></tr>
        <tr><td>NUMBER</td><td>126 (100.00 %)</td><td>126</td></tr>
        </table>
        <table>
        <tr><td>ELEMENT's SIDE LENGTH</td></tr>
        <tr><td>MIN</td><td>1.2</td><td>-</td></tr>
        <tr><td>AVERAGE</td><td>12.5</td><td>12.5</td></tr>
        <tr><td>MAX</td><td>18.0</td><td>-</td></tr>
        </table>
        </body></html>
        """,
        encoding="utf-8",
    )

    parsed = parse_quality_report(report, scan_issue_terms=False)

    assert parsed["numeric_metrics"]["session_part_record_count"] == 1
    assert parsed["numeric_metrics"]["session_unmeshed_total"] == 0.0
    assert parsed["numeric_metrics"]["session_violating_total"] == 0.0
    assert parsed["numeric_metrics"]["overall_shell_element_total"] == 126.0
    assert parsed["numeric_metrics"]["side_length_min"] == 1.2
    assert parsed["threshold_violations"] == []


def test_quality_thresholds_reject_unmeshed_numeric_statistics():
    metrics = parse_numeric_quality_metrics(
        """
        <table>
        <tr><td>Part</td><td>Unmeshed</td><td>Total</td></tr>
        <tr><td>TOTAL</td><td>2</td><td>126</td></tr>
        </table>
        """
    )

    violations = quality_threshold_violations(metrics)

    assert violations
    assert violations[0]["metric"] == "session_unmeshed_total"


def test_quality_thresholds_reject_violating_shell_total():
    metrics = parse_numeric_quality_metrics(
        """
        <table summary="Session-Parts Report Table">
        <tr><td>Part</td><td>Unmeshed</td><td>Total</td></tr>
        <tr><td>TOTAL</td><td>0</td><td>2</td></tr>
        </table>
        """
    )

    violations = quality_threshold_violations(metrics)

    assert violations
    assert violations[0]["metric"] == "session_violating_total"
