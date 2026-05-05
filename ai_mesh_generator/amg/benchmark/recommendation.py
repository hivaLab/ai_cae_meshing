"""Benchmark real ANSA quality recommendations against baseline manifests."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MIN_ATTEMPTED = 6
MIN_IMPROVEMENT_RATE = 0.60
MIN_MEDIAN_DELTA = 0.01


class AmgRecommendationBenchmarkError(ValueError):
    """Raised when recommendation benchmark evidence is missing or malformed."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgRecommendationBenchmarkError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgRecommendationBenchmarkError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgRecommendationBenchmarkError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _summary_path(root: Path) -> Path:
    if root.is_file():
        return root
    path = root / "recommendation_summary.json"
    if not path.is_file():
        raise AmgRecommendationBenchmarkError("missing_recommendation_summary", "recommendation summary not found", root)
    return path


def _mesh_artifact_is_real(path_text: Any, root: Path) -> bool:
    if not isinstance(path_text, str) or not path_text:
        return False
    path = Path(path_text)
    if not path.is_absolute() and not path.exists():
        path = root / path
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    head = path.read_text(encoding="utf-8", errors="ignore")[:512].lower()
    return "mock" not in head and "placeholder" not in head


def _sample_report(path_text: Any, root: Path) -> dict[str, Any] | None:
    if not isinstance(path_text, str):
        return None
    path = Path(path_text)
    if not path.is_absolute() and not path.exists():
        path = root / path
    if not path.is_file():
        return None
    return _read_json(path, "sample_report_read_failed")


def build_recommendation_benchmark_report(
    *,
    recommendation: str | Path,
    baseline: str | Path | None = None,
    min_attempted: int = MIN_ATTEMPTED,
    min_improvement_rate: float = MIN_IMPROVEMENT_RATE,
    min_median_delta: float = MIN_MEDIAN_DELTA,
) -> dict[str, Any]:
    root = Path(recommendation)
    summary_path = _summary_path(root)
    summary = _read_json(summary_path, "recommendation_summary_read_failed")
    sample_results = summary.get("sample_results", [])
    if not isinstance(sample_results, list) or not all(isinstance(item, Mapping) for item in sample_results):
        raise AmgRecommendationBenchmarkError("malformed_recommendation_summary", "sample_results must be a list of objects", summary_path)
    deltas: list[float] = []
    failure_counts: Counter[str] = Counter()
    invalid_artifacts = 0
    valid_pair_count = 0
    improved_count = 0
    selected_non_baseline_count = 0
    for result in sample_results:
        report = _sample_report(result.get("report_path"), root)
        if report is None:
            failure_counts["missing_sample_report"] += 1
            continue
        if result.get("selected_evaluation_id") not in {None, "baseline"}:
            selected_non_baseline_count += 1
        baseline_run = report.get("baseline_run", {})
        recommended_run = report.get("recommended_run", {})
        if not isinstance(baseline_run, Mapping) or not isinstance(recommended_run, Mapping):
            failure_counts["missing_run_evidence"] += 1
            continue
        if not _mesh_artifact_is_real(baseline_run.get("mesh_path"), root) or not _mesh_artifact_is_real(recommended_run.get("mesh_path"), root):
            invalid_artifacts += 1
            failure_counts["missing_or_placeholder_mesh"] += 1
            continue
        baseline_score = result.get("baseline_score")
        recommended_score = result.get("recommended_score")
        delta = result.get("improvement_delta")
        if not isinstance(baseline_score, (int, float)) or not isinstance(recommended_score, (int, float)) or not isinstance(delta, (int, float)):
            failure_counts["missing_quality_scores"] += 1
            continue
        valid_pair_count += 1
        deltas.append(float(delta))
        if float(delta) > min_median_delta:
            improved_count += 1
    attempted_count = len(sample_results)
    improvement_rate = improved_count / valid_pair_count if valid_pair_count else 0.0
    median_delta = statistics.median(deltas) if deltas else None
    criteria = {
        "minimum_attempted": attempted_count >= min_attempted,
        "all_pairs_valid": valid_pair_count == attempted_count and attempted_count > 0,
        "no_invalid_artifacts": invalid_artifacts == 0,
        "non_baseline_selected": selected_non_baseline_count > 0,
        "improvement_rate_met": improvement_rate >= min_improvement_rate,
        "median_improvement_delta_met": median_delta is not None and median_delta > min_median_delta,
    }
    baseline_comparison = None
    if baseline is not None:
        baseline_root = Path(baseline)
        baseline_report = _read_json(baseline_root if baseline_root.is_file() else _summary_path(baseline_root), "baseline_benchmark_read_failed")
        baseline_rate = baseline_report.get("improvement_rate")
        baseline_median = baseline_report.get("median_improvement_delta")
        baseline_selected = baseline_report.get("selected_non_baseline_count")
        rate_delta = improvement_rate - float(baseline_rate) if isinstance(baseline_rate, (int, float)) else None
        median_delta_vs_baseline = float(median_delta) - float(baseline_median) if isinstance(median_delta, (int, float)) and isinstance(baseline_median, (int, float)) else None
        selected_delta = selected_non_baseline_count - int(baseline_selected) if isinstance(baseline_selected, int) else None
        criteria["baseline_improvement_rate_preserved"] = rate_delta is not None and rate_delta >= 0.0
        criteria["baseline_median_delta_preserved"] = median_delta_vs_baseline is not None and median_delta_vs_baseline >= 0.0
        baseline_comparison = {
            "baseline_path": baseline_root.as_posix(),
            "baseline_improvement_rate": baseline_rate,
            "baseline_median_improvement_delta": baseline_median,
            "baseline_selected_non_baseline_count": baseline_selected,
            "improvement_rate_delta": rate_delta,
            "median_improvement_delta_delta": median_delta_vs_baseline,
            "selected_non_baseline_count_delta": selected_delta,
        }
    return {
        "schema": "AMG_QUALITY_RECOMMENDATION_BENCHMARK_V1",
        "status": "SUCCESS" if all(criteria.values()) else "FAILED",
        "recommendation_root": root.as_posix(),
        "recommendation_summary_path": summary_path.as_posix(),
        "attempted_count": attempted_count,
        "valid_pair_count": valid_pair_count,
        "improved_count": improved_count,
        "improvement_rate": improvement_rate,
        "mean_improvement_delta": statistics.mean(deltas) if deltas else None,
        "median_improvement_delta": median_delta,
        "selected_non_baseline_count": selected_non_baseline_count,
        "failure_reason_counts": dict(sorted((Counter(summary.get("failure_reason_counts", {})) + failure_counts).items())),
        "invalid_artifact_count": invalid_artifacts,
        "success_criteria": criteria,
        "baseline_comparison": baseline_comparison,
    }


def write_recommendation_benchmark_report(path: str | Path, report: Mapping[str, Any]) -> None:
    _write_json(Path(path), report)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark real ANSA quality recommendations.")
    parser.add_argument("--recommendation", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--min-attempted", type=int, default=MIN_ATTEMPTED)
    parser.add_argument("--min-improvement-rate", type=float, default=MIN_IMPROVEMENT_RATE)
    parser.add_argument("--min-median-delta", type=float, default=MIN_MEDIAN_DELTA)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_recommendation_benchmark_report(
            recommendation=Path(args.recommendation),
            baseline=Path(args.baseline) if args.baseline else None,
            min_attempted=args.min_attempted,
            min_improvement_rate=args.min_improvement_rate,
            min_median_delta=args.min_median_delta,
        )
        write_recommendation_benchmark_report(args.out, report)
    except AmgRecommendationBenchmarkError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": report["status"], "out": Path(args.out).as_posix()}, indent=2, sort_keys=True))
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
