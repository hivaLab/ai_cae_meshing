from __future__ import annotations

from html.parser import HTMLParser
import re
from pathlib import Path
from typing import Any


ISSUE_WORDS = ("violation", "violations", "failed", "failure", "failures", "error", "errors", "fatal", "unmeshed")
DEFAULT_NUMERIC_THRESHOLDS = {
    "session_unmeshed_total_max": 0.0,
    "session_violating_total_max": 0.0,
    "side_length_min": 0.0,
    "solid_unmeshed_volume_count_max": 0.0,
    "solid_failed_region_count_max": 0.0,
    "solid_scaled_jacobian_min": 0.1,
    "solid_volume_min": 0.0,
    "solid_dihedral_max": 165.0,
}


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


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.tables: list[dict[str, Any]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._table_rows: list[list[str]] | None = None
        self._table_summary = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            attrs_dict = {key.lower(): value or "" for key, value in attrs}
            self._table_rows = []
            self._table_summary = attrs_dict.get("summary", "")
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self.rows.append(self._row)
                if self._table_rows is not None:
                    self._table_rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_rows is not None:
            self.tables.append({"summary": self._table_summary, "rows": self._table_rows})
            self._table_rows = None
            self._table_summary = ""


def parse_numeric_quality_metrics(text: str) -> dict[str, Any]:
    """Parse numeric metrics from ANSA Batch Mesh Manager HTML statistics."""

    parser = _TableParser()
    parser.feed(text)
    rows = parser.rows
    tables = parser.tables
    metrics: dict[str, Any] = {
        "table_row_count": len(rows),
        "session_part_records": [],
        "side_length": {},
    }

    session_records = _parse_session_part_records(tables, rows)

    if session_records:
        metrics["session_part_records"] = session_records
        metrics["session_part_record_count"] = len(session_records)
        metrics["session_unmeshed_total"] = _sum_records(session_records, "unmeshed")
        metrics["session_violating_total"] = _sum_records(session_records, "total")
        metrics["session_min_length_violation_total"] = _sum_records(session_records, "min_len")
        metrics["session_max_length_violation_total"] = _sum_records(session_records, "max_len")
        metrics["session_element_total"] = metrics["session_violating_total"]
        metrics["session_average_length_mean"] = _mean_records(session_records, "aver_length_shells")
    else:
        metrics["session_part_record_count"] = 0

    overall_shell_total = _parse_overall_shell_element_total(tables, rows)
    if overall_shell_total is not None:
        metrics["overall_shell_element_total"] = overall_shell_total

    side_length = _parse_side_length_table(rows)
    if side_length:
        metrics["side_length"] = side_length
        if "min" in side_length:
            metrics["side_length_min"] = side_length["min"]
        if "average" in side_length:
            metrics["side_length_average"] = side_length["average"]
        if "max" in side_length:
            metrics["side_length_max"] = side_length["max"]

    solid_quality = _parse_solid_quality_metrics(text)
    if solid_quality:
        metrics["solid_quality"] = solid_quality
        metrics.update(solid_quality)

    return metrics


def quality_threshold_violations(
    numeric_metrics: dict[str, Any], thresholds: dict[str, float] | None = None
) -> list[dict[str, Any]]:
    thresholds = {**DEFAULT_NUMERIC_THRESHOLDS, **(thresholds or {})}
    violations: list[dict[str, Any]] = []
    if int(numeric_metrics.get("session_part_record_count", 0)) > 0:
        unmeshed = float(numeric_metrics.get("session_unmeshed_total", 0.0))
        violating_total = float(numeric_metrics.get("session_violating_total", numeric_metrics.get("session_element_total", 0.0)))
        if unmeshed > float(thresholds["session_unmeshed_total_max"]):
            violations.append(
                {
                    "metric": "session_unmeshed_total",
                    "value": unmeshed,
                    "threshold": float(thresholds["session_unmeshed_total_max"]),
                    "rule": "<=",
                }
            )
        if violating_total > float(thresholds["session_violating_total_max"]):
            violations.append(
                {
                    "metric": "session_violating_total",
                    "value": violating_total,
                    "threshold": float(thresholds["session_violating_total_max"]),
                    "rule": "<=",
                }
            )
    if "side_length_min" in numeric_metrics:
        side_min = float(numeric_metrics["side_length_min"])
        if side_min <= float(thresholds["side_length_min"]):
            violations.append(
                {
                    "metric": "side_length_min",
                    "value": side_min,
                    "threshold": float(thresholds["side_length_min"]),
                    "rule": ">",
                }
            )
    if "solid_unmeshed_volume_count" in numeric_metrics:
        unmeshed_volume = float(numeric_metrics["solid_unmeshed_volume_count"])
        if unmeshed_volume > float(thresholds["solid_unmeshed_volume_count_max"]):
            violations.append(
                {
                    "metric": "solid_unmeshed_volume_count",
                    "value": unmeshed_volume,
                    "threshold": float(thresholds["solid_unmeshed_volume_count_max"]),
                    "rule": "<=",
                }
            )
    if "solid_failed_region_count" in numeric_metrics:
        failed_regions = float(numeric_metrics["solid_failed_region_count"])
        if failed_regions > float(thresholds["solid_failed_region_count_max"]):
            violations.append(
                {
                    "metric": "solid_failed_region_count",
                    "value": failed_regions,
                    "threshold": float(thresholds["solid_failed_region_count_max"]),
                    "rule": "<=",
                }
            )
    if "solid_scaled_jacobian_min" in numeric_metrics:
        scaled_jacobian = float(numeric_metrics["solid_scaled_jacobian_min"])
        if scaled_jacobian < float(thresholds["solid_scaled_jacobian_min"]):
            violations.append(
                {
                    "metric": "solid_scaled_jacobian_min",
                    "value": scaled_jacobian,
                    "threshold": float(thresholds["solid_scaled_jacobian_min"]),
                    "rule": ">=",
                }
            )
    if "solid_volume_min" in numeric_metrics:
        volume_min = float(numeric_metrics["solid_volume_min"])
        if volume_min <= float(thresholds["solid_volume_min"]):
            violations.append(
                {
                    "metric": "solid_volume_min",
                    "value": volume_min,
                    "threshold": float(thresholds["solid_volume_min"]),
                    "rule": ">",
                }
            )
    if "solid_dihedral_max" in numeric_metrics:
        dihedral_max = float(numeric_metrics["solid_dihedral_max"])
        if dihedral_max > float(thresholds["solid_dihedral_max"]):
            violations.append(
                {
                    "metric": "solid_dihedral_max",
                    "value": dihedral_max,
                    "threshold": float(thresholds["solid_dihedral_max"]),
                    "rule": "<=",
                }
            )
    return violations


def parse_quality_report(path: Path | str, scan_issue_terms: bool = True) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        return {
            "path": str(report_path),
            "exists": False,
            "parsed": False,
            "issue_terms": {},
            "numeric_metrics": {},
            "threshold_violations": [{"metric": "report_file", "value": "missing", "rule": "exists"}],
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
            "numeric_metrics": {},
            "threshold_violations": [{"metric": "report_file", "value": "unreadable", "rule": "parse"}],
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
    numeric_metrics = parse_numeric_quality_metrics(text)
    threshold_violations = quality_threshold_violations(numeric_metrics)
    issue_count = (count_quality_issue_words(text) if scan_issue_terms else 0) + len(threshold_violations)
    return {
        "path": str(report_path),
        "exists": True,
        "parsed": True,
        "issue_terms": terms,
        "numeric_metrics": numeric_metrics,
        "threshold_violations": threshold_violations,
        "issue_count": issue_count,
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
                    "numeric_metrics": report_parse.get("numeric_metrics", {}) if report_parse else {},
                    "threshold_violations": report_parse.get("threshold_violations", []) if report_parse else [],
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


def _normalize_header(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9%]+", "_", value.strip().lower()).strip("_")
    lookup = {
        "aver_length_shells": "aver_length_shells",
        "aver_len_shells": "aver_length_shells",
        "average_length_shells": "aver_length_shells",
        "unmeshed": "unmeshed",
        "triangles": "triangles_percent",
        "triangles_%": "triangles_percent",
        "triangles_percent": "triangles_percent",
        "total": "total",
        "min_len": "min_len",
        "min_length": "min_len",
        "max_len": "max_len",
        "max_length": "max_len",
        "min": "min",
        "average": "average",
        "max": "max",
    }
    return lookup.get(normalized, normalized)


def _parse_session_part_records(
    tables: list[dict[str, Any]], rows: list[list[str]]
) -> list[dict[str, float | str]]:
    candidate_tables = []
    for table in tables:
        table_rows = table.get("rows", [])
        summary = str(table.get("summary", "")).lower()
        flattened = " ".join(" ".join(row) for row in table_rows).lower()
        if "session-parts" in summary or ("unmeshed" in flattened and "violating shell elements" in flattened):
            candidate_tables.append(table_rows)
    if not candidate_tables:
        candidate_tables = [rows]

    records: list[dict[str, float | str]] = []
    for table_rows in candidate_tables:
        header: list[str] | None = None
        for row in table_rows:
            lowered = [_normalize_header(cell) for cell in row]
            if "unmeshed" in lowered and "total" in lowered:
                header = lowered
                continue
            if header is None or len(row) < 2:
                continue
            normalized_row = _align_session_total_row(header, row)
            record = _row_to_record(header, normalized_row)
            if record and any(key in record for key in ("unmeshed", "total", "min_len", "max_len")):
                records.append(record)
    return records


def _align_session_total_row(header: list[str], row: list[str]) -> list[str]:
    if not row or row[0].strip().upper() != "TOTAL" or "aver_length_shells" not in header:
        return row
    expected = len(header)
    if len(row) >= expected:
        return row
    average_index = header.index("aver_length_shells")
    aligned = [""] * expected
    aligned[0] = row[0]
    for offset, value in enumerate(row[1:]):
        index = average_index + offset
        if index < expected:
            aligned[index] = value
    return aligned


def _row_to_record(header: list[str], row: list[str]) -> dict[str, float | str]:
    record: dict[str, float | str] = {}
    for index, key in enumerate(header[: len(row)]):
        value = row[index]
        number = _number(value)
        if index == 0 and number is None:
            record["label"] = value
        elif number is not None:
            record[key] = number
    return record


def _parse_overall_shell_element_total(tables: list[dict[str, Any]], rows: list[list[str]]) -> float | None:
    candidate_tables = [table.get("rows", []) for table in tables]
    if not candidate_tables:
        candidate_tables = [rows]
    for table_rows in candidate_tables:
        flattened = " ".join(" ".join(row) for row in table_rows).lower()
        if "overall numbers of shell" not in flattened:
            continue
        header: list[str] | None = None
        for row in table_rows:
            lowered = [_normalize_header(cell) for cell in row]
            if "type" in lowered and "total" in lowered:
                header = lowered
                continue
            if header and row and row[0].strip().lower() == "number":
                total_index = header.index("total")
                if total_index < len(row):
                    return _number(row[total_index])
    return None


def _parse_side_length_table(rows: list[list[str]]) -> dict[str, float]:
    for index, row in enumerate(rows):
        if "side length" not in " ".join(row).lower():
            continue
        vertical = _parse_vertical_side_length_rows(rows[index + 1 : index + 8])
        if vertical:
            return vertical
        for follow in rows[index + 1 : index + 4]:
            header = [_normalize_header(cell) for cell in follow]
            if {"min", "average", "max"} <= set(header):
                value_row = next((candidate for candidate in rows[index + 2 : index + 6] if candidate != follow), [])
                record = _row_to_record(header, value_row)
                return {key: float(record[key]) for key in ("min", "average", "max") if key in record}
    return {}


def _parse_solid_quality_metrics(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    normalized = re.sub(r"\s+", " ", text.replace("&nbsp;", " ")).lower()
    lookups = {
        "solid_unmeshed_volume_count": [
            r"unmeshed\s+volumes?\D{0,40}({number})",
            r"unmeshed\s+macros?\D{0,40}({number})",
        ],
        "solid_failed_region_count": [
            r"failed\s+regions?\D{0,40}({number})",
            r"failed\s+volumes?\D{0,40}({number})",
        ],
        "solid_scaled_jacobian_min": [
            r"min(?:imum)?\s+scaled\s+jacobian\D{0,40}({number})",
            r"scaled\s+jacobian\D{0,40}min(?:imum)?\D{0,40}({number})",
        ],
        "solid_volume_min": [
            r"min(?:imum)?\s+(?:tetra\s+)?volume\D{0,40}({number})",
            r"(?:tetra\s+)?volume\D{0,40}min(?:imum)?\D{0,40}({number})",
        ],
        "solid_dihedral_max": [
            r"max(?:imum)?\s+dihedral\D{0,40}({number})",
            r"dihedral\D{0,40}max(?:imum)?\D{0,40}({number})",
        ],
    }
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[ee][-+]?\d+)?"
    for key, patterns in lookups.items():
        for pattern in patterns:
            match = re.search(pattern.replace("{number}", number), normalized)
            if match:
                metrics[key] = float(match.group(1))
                break
    return metrics


def _parse_vertical_side_length_rows(rows: list[list[str]]) -> dict[str, float]:
    result: dict[str, float] = {}
    lookup = {"min": "min", "average": "average", "max": "max"}
    for row in rows:
        if not row:
            continue
        key = lookup.get(_normalize_header(row[0]))
        if not key:
            continue
        values = [_number(cell) for cell in row[1:]]
        number = next((value for value in values if value is not None), None)
        if number is not None:
            result[key] = float(number)
    return result if {"min", "average", "max"} <= set(result) else {}


def _number(value: str) -> float | None:
    cleaned = value.strip().replace(",", "")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _sum_records(records: list[dict[str, float | str]], key: str) -> float:
    return float(sum(float(record[key]) for record in records if key in record))


def _min_records(records: list[dict[str, float | str]], key: str) -> float | None:
    values = [float(record[key]) for record in records if key in record]
    return min(values) if values else None


def _max_records(records: list[dict[str, float | str]], key: str) -> float | None:
    values = [float(record[key]) for record in records if key in record]
    return max(values) if values else None


def _mean_records(records: list[dict[str, float | str]], key: str) -> float | None:
    values = [float(record[key]) for record in records if key in record]
    return sum(values) / len(values) if values else None
