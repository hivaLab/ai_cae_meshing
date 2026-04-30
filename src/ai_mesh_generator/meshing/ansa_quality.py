from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ISSUE_WORDS = ("violation", "violations", "failed", "failure", "failures", "error", "errors", "fatal", "unmeshed")


def normalize_write_statistics_status(value: Any) -> dict[str, Any]:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return {"code": None, "state": "not_available", "issue_count": 0}
    if code == 2:
        return {"code": code, "state": "completed_without_errors", "issue_count": 0}
    if code == 1:
        return {"code": code, "state": "completed_with_quality_issues", "issue_count": 1}
    if code == 0:
        return {"code": code, "state": "statistics_unavailable", "issue_count": 1}
    return {"code": code, "state": "unknown_status", "issue_count": 1}


def count_quality_issue_words(text: str) -> int:
    lowered = text.lower()
    total = 0
    for word in ISSUE_WORDS:
        for match in re.finditer(rf"\b{re.escape(word)}\b", lowered):
            start = max(0, match.start() - 8)
            prefix = lowered[start : match.start()]
            if re.search(r"\b0\s*$", prefix):
                continue
            total += 1
    return total


def parse_quality_report(path: Path | str, scan_issue_terms: bool = True) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        return {
            "path": str(report_path),
            "exists": False,
            "parsed": False,
            "issue_terms": {},
            "issue_count": 1,
            "error": "quality statistics report file is missing",
        }
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "path": str(report_path),
            "exists": True,
            "parsed": False,
            "issue_terms": {},
            "issue_count": 1,
            "error": str(exc),
        }
    terms = {}
    if scan_issue_terms:
        lowered = text.lower()
        for word in ISSUE_WORDS:
            count = len(re.findall(rf"\b{re.escape(word)}\b", lowered))
            if count:
                terms[word] = count
    return {
        "path": str(report_path),
        "exists": True,
        "parsed": True,
        "issue_terms": terms,
        "issue_count": count_quality_issue_words(text) if scan_issue_terms else 0,
        "error": "",
    }


def summarize_ansa_quality_statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    report_files: list[str] = []
    issue_records: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    parsed_reports: list[dict[str, Any]] = []
    file_issue_count = 0

    for record in records:
        if record.get("status") == "skipped":
            continue
        normalized = normalize_write_statistics_status(record.get("write_statistics_status"))
        state = normalized["state"]
        status_counts[state] = status_counts.get(state, 0) + 1
        report_path = record.get("statistics_report_file")
        text_issues = 0
        report_parse = None
        if report_path:
            path = Path(str(report_path))
            report_files.append(str(path))
            report_parse = parse_quality_report(path, scan_issue_terms=state != "completed_without_errors")
            parsed_reports.append(report_parse)
            text_issues = int(report_parse["issue_count"])
            file_issue_count += text_issues
        else:
            report_parse = {
                "path": "",
                "exists": False,
                "parsed": False,
                "issue_terms": {},
                "issue_count": 1,
                "error": "quality statistics report file path is missing",
            }
            parsed_reports.append(report_parse)
            text_issues = 1
            file_issue_count += 1
        issue_count = int(normalized["issue_count"]) + text_issues
        if issue_count:
            issue_records.append(
                {
                    "part_uid": record.get("part_uid", ""),
                    "status": state,
                    "statistics_report_file": report_path,
                    "issue_count": issue_count,
                    "report_error": report_parse.get("error", "") if report_parse else "",
                    "issue_terms": report_parse.get("issue_terms", {}) if report_parse else {},
                }
            )

    return {
        "record_count": sum(1 for item in records if item.get("status") != "skipped"),
        "report_files": report_files,
        "status_counts": status_counts,
        "parsed_reports": parsed_reports,
        "file_issue_word_count": file_issue_count,
        "issue_record_count": len(issue_records),
        "issue_records": issue_records,
        "passed": len(issue_records) == 0,
    }
