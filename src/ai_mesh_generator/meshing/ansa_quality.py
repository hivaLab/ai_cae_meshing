from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ISSUE_WORDS = ("violation", "violations", "failed", "error", "errors", "unmeshed")


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


def summarize_ansa_quality_statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    report_files: list[str] = []
    issue_records: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    file_issue_count = 0

    for record in records:
        if record.get("status") == "skipped":
            continue
        normalized = normalize_write_statistics_status(record.get("write_statistics_status"))
        state = normalized["state"]
        status_counts[state] = status_counts.get(state, 0) + 1
        report_path = record.get("statistics_report_file")
        text_issues = 0
        if report_path:
            path = Path(str(report_path))
            report_files.append(str(path))
            if path.exists() and state != "completed_without_errors":
                text_issues = count_quality_issue_words(path.read_text(encoding="utf-8", errors="replace"))
                file_issue_count += text_issues
        issue_count = int(normalized["issue_count"]) + text_issues
        if issue_count:
            issue_records.append(
                {
                    "part_uid": record.get("part_uid", ""),
                    "status": state,
                    "statistics_report_file": report_path,
                    "issue_count": issue_count,
                }
            )

    return {
        "record_count": sum(1 for item in records if item.get("status") != "skipped"),
        "report_files": report_files,
        "status_counts": status_counts,
        "file_issue_word_count": file_issue_count,
        "issue_record_count": len(issue_records),
        "issue_records": issue_records,
        "passed": len(issue_records) == 0,
    }
