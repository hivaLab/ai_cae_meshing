"""Diagnose AMG quality-candidate evidence without hiding failed AI proposals."""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AmgQualityCandidateDiagnosticError(ValueError):
    """Raised when quality-candidate diagnostics cannot be built."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class QualityCandidateDiagnosticConfig:
    dataset_root: Path
    quality_exploration_root: Path
    sample_ids: tuple[str, ...] = ()
    split: str | None = None
    limit: int | None = None
    improvement_epsilon: float = 0.01


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgQualityCandidateDiagnosticError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgQualityCandidateDiagnosticError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgQualityCandidateDiagnosticError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _summary_path(root: Path) -> Path:
    if root.is_file():
        return root
    path = root / "quality_exploration_summary.json"
    if not path.is_file():
        raise AmgQualityCandidateDiagnosticError("missing_quality_exploration_summary", "quality exploration summary not found", root)
    return path


def _split_ids(dataset_root: Path, split: str | None) -> list[str]:
    if not split:
        return []
    path = dataset_root / "splits" / f"{split}.txt"
    if not path.is_file():
        raise AmgQualityCandidateDiagnosticError("missing_split_file", f"split file not found: {split}", path)
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _resolve_path(path_text: Any, roots: Sequence[Path]) -> Path | None:
    if not isinstance(path_text, str) or not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute() or path.exists():
        return path
    for root in roots:
        candidate = root / path
        if candidate.exists():
            return candidate
    return path


def _control_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    features = manifest.get("features", [])
    if not isinstance(features, list):
        return rows
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        controls = feature.get("controls", {})
        rows.append(
            {
                "feature_id": feature.get("feature_id"),
                "type": feature.get("type"),
                "role": feature.get("role"),
                "action": feature.get("action"),
                "controls": dict(controls) if isinstance(controls, Mapping) else {},
            }
        )
    return rows


def _score_breakdown_from_reports(quality_report: Mapping[str, Any], execution_report: Mapping[str, Any]) -> dict[str, Any]:
    quality = quality_report.get("quality", {})
    if not isinstance(quality, Mapping):
        return {"available": False, "reason": "malformed_quality_report"}
    hard_failed = int(quality.get("num_hard_failed_elements", 1) or 0)
    feature_checks = quality_report.get("feature_checks", [])
    boundary_error = 0.0
    if isinstance(feature_checks, list):
        for check in feature_checks:
            if isinstance(check, Mapping) and isinstance(check.get("boundary_size_error"), (int, float)):
                boundary_error = max(boundary_error, abs(float(check["boundary_size_error"])))
    components = {
        "hard_failed_penalty": 1000.0 * hard_failed,
        "violating_shell_penalty": 100.0 * float(quality.get("violating_shell_elements_total", 0.0) or 0.0),
        "side_length_spread_penalty": 25.0 * float(quality.get("side_length_spread_ratio", 0.0) or 0.0),
        "aspect_proxy_penalty": 10.0 * max(0.0, float(quality.get("aspect_ratio_proxy_max", 1.0) or 1.0) - 1.0),
        "boundary_error_penalty": 10.0 * boundary_error,
        "triangles_penalty": 0.05 * float(quality.get("triangles_percent", 0.0) or 0.0),
        "shell_count_penalty": 0.001
        * float(quality.get("num_shell_elements", quality_report.get("mesh_stats", {}).get("num_shell_elements", 0.0)) or 0.0),
        "runtime_penalty": 0.001 * float(execution_report.get("runtime_sec", 0.0) or 0.0),
    }
    total = sum(float(value) for value in components.values())
    return {
        "available": True,
        "quality_score": total,
        "components": components,
        "hard_failed_elements": hard_failed,
        "boundary_size_error_max": boundary_error,
    }


def _record_diagnostic(record: Mapping[str, Any], roots: Sequence[Path]) -> dict[str, Any]:
    manifest_path = _resolve_path(record.get("manifest_path"), roots)
    execution_path = _resolve_path(record.get("execution_report_path"), roots)
    quality_path = _resolve_path(record.get("quality_report_path"), roots)
    manifest = _read_json(manifest_path, "manifest_read_failed") if manifest_path is not None and manifest_path.is_file() else {}
    execution = _read_json(execution_path, "execution_report_read_failed") if execution_path is not None and execution_path.is_file() else {}
    quality = _read_json(quality_path, "quality_report_read_failed") if quality_path is not None and quality_path.is_file() else {}
    if execution and quality:
        score = _score_breakdown_from_reports(quality, execution)
        quality_score = score.get("quality_score")
        score_source = "reports"
    else:
        quality_score = record.get("quality_score")
        score = {"available": False, "reason": "reports_missing", "record_quality_score": quality_score}
        score_source = "record"
    return {
        "sample_id": record.get("sample_id"),
        "evaluation_id": record.get("evaluation_id", record.get("candidate_id")),
        "status": record.get("status"),
        "is_baseline": bool(record.get("is_baseline") or record.get("evaluation_id") == "baseline"),
        "is_fresh_candidate": bool(record.get("is_fresh_candidate")),
        "predicted_score": record.get("predicted_score"),
        "quality_score": quality_score,
        "quality_score_source": score_source,
        "score_breakdown": score,
        "manifest_path": manifest_path.as_posix() if manifest_path is not None else None,
        "execution_report_path": execution_path.as_posix() if execution_path is not None else None,
        "quality_report_path": quality_path.as_posix() if quality_path is not None else None,
        "controls": _control_rows(manifest),
    }


def _sample_diagnostic(sample_id: str, records: Sequence[Mapping[str, Any]], roots: Sequence[Path], improvement_epsilon: float) -> dict[str, Any]:
    diagnostics = [_record_diagnostic(record, roots) for record in records]
    baseline_scores = [
        float(item["quality_score"])
        for item in diagnostics
        if item["is_baseline"] and isinstance(item.get("quality_score"), (int, float))
    ]
    candidate_scores = [
        float(item["quality_score"])
        for item in diagnostics
        if not item["is_baseline"] and isinstance(item.get("quality_score"), (int, float))
    ]
    baseline_score = baseline_scores[0] if baseline_scores else None
    best_candidate_score = min(candidate_scores) if candidate_scores else None
    improvement_delta = None
    has_better_candidate = False
    if baseline_score is not None and best_candidate_score is not None:
        improvement_delta = baseline_score - best_candidate_score
        has_better_candidate = improvement_delta > improvement_epsilon
    status = "HAS_BETTER_AI_CANDIDATE" if has_better_candidate else "NEEDS_AI_CANDIDATE_IMPROVEMENT"
    if baseline_score is None or best_candidate_score is None:
        status = "INSUFFICIENT_EVIDENCE"
    return {
        "sample_id": sample_id,
        "status": status,
        "baseline_quality_score": baseline_score,
        "best_non_baseline_quality_score": best_candidate_score,
        "best_non_baseline_improvement_delta": improvement_delta,
        "candidate_count": len([item for item in diagnostics if not item["is_baseline"]]),
        "scored_candidate_count": len(candidate_scores),
        "quality_score_variance": statistics.pvariance(candidate_scores) if len(candidate_scores) >= 2 else 0.0,
        "records": sorted(
            diagnostics,
            key=lambda item: (
                float("inf") if not isinstance(item.get("quality_score"), (int, float)) else float(item["quality_score"]),
                str(item.get("evaluation_id")),
            ),
        ),
    }


def build_quality_candidate_diagnostics(config: QualityCandidateDiagnosticConfig) -> dict[str, Any]:
    """Build a diagnostic report comparing baseline/reference evidence to AI candidates."""

    summary_path = _summary_path(config.quality_exploration_root)
    summary = _read_json(summary_path, "quality_summary_read_failed")
    records = summary.get("records", [])
    if not isinstance(records, list) or not all(isinstance(item, Mapping) for item in records):
        raise AmgQualityCandidateDiagnosticError("malformed_quality_summary", "records must be a list of objects", summary_path)
    requested_ids = list(config.sample_ids) or _split_ids(config.dataset_root, config.split)
    if not requested_ids:
        requested_ids = sorted({str(record.get("sample_id")) for record in records if isinstance(record.get("sample_id"), str)})
    if config.limit is not None:
        if config.limit <= 0:
            raise AmgQualityCandidateDiagnosticError("invalid_limit", "limit must be positive")
        requested_ids = requested_ids[: config.limit]
    if not requested_ids:
        raise AmgQualityCandidateDiagnosticError("empty_diagnostic_selection", "no samples selected for diagnostics", summary_path)
    roots = (Path.cwd(), config.quality_exploration_root, config.dataset_root)
    by_sample = {
        sample_id: [record for record in records if record.get("sample_id") == sample_id]
        for sample_id in requested_ids
    }
    sample_reports = [
        _sample_diagnostic(sample_id, sample_records, roots, config.improvement_epsilon)
        for sample_id, sample_records in by_sample.items()
        if sample_records
    ]
    if not sample_reports:
        raise AmgQualityCandidateDiagnosticError("missing_sample_records", "selected samples have no quality records", summary_path)
    status_counts: dict[str, int] = {}
    for sample in sample_reports:
        status = str(sample["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema": "AMG_QUALITY_CANDIDATE_DIAGNOSTIC_V1",
        "status": "NEEDS_IMPROVEMENT" if status_counts.get("NEEDS_AI_CANDIDATE_IMPROVEMENT", 0) else "OK",
        "dataset_root": config.dataset_root.as_posix(),
        "quality_exploration_root": config.quality_exploration_root.as_posix(),
        "quality_summary_path": summary_path.as_posix(),
        "sample_count": len(sample_reports),
        "status_counts": dict(sorted(status_counts.items())),
        "samples": sample_reports,
    }


def write_quality_candidate_diagnostics(path: str | Path, report: Mapping[str, Any]) -> None:
    _write_json(Path(path), report)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose AMG quality candidate evidence.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--quality-exploration", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--split")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--improvement-epsilon", type=float, default=0.01)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_quality_candidate_diagnostics(
            QualityCandidateDiagnosticConfig(
                dataset_root=Path(args.dataset),
                quality_exploration_root=Path(args.quality_exploration),
                sample_ids=tuple(args.sample_id or ()),
                split=args.split,
                limit=args.limit,
                improvement_epsilon=args.improvement_epsilon,
            )
        )
        write_quality_candidate_diagnostics(args.out, report)
    except AmgQualityCandidateDiagnosticError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
