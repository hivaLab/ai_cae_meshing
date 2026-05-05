"""Benchmark real ANSA quality recommendations."""

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
IMPROVEMENT_EPSILON = 0.01
SEVERE_REGRESSION_THRESHOLD = -1.0
MAX_SEVERE_REGRESSION_COUNT = 0


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


def _resolve_artifact_path(path_text: Any, root: Path) -> Path | None:
    if not isinstance(path_text, str) or not path_text:
        return None
    path = Path(path_text)
    if not path.is_absolute() and not path.exists():
        path = root / path
    return path


def _json_report_is_real(path_text: Any, root: Path, *, report_kind: str) -> tuple[bool, str | None]:
    path = _resolve_artifact_path(path_text, root)
    if path is None or not path.is_file():
        return False, f"missing_{report_kind}_report"
    report = _read_json(path, f"{report_kind}_report_read_failed")
    if report.get("accepted") is not True:
        return False, f"{report_kind}_report_not_accepted"
    encoded = json.dumps(report, sort_keys=True).lower()
    for marker in ("controlled_failure_reason", "mock-ansa", "unavailable", "placeholder"):
        if marker in encoded:
            return False, f"{report_kind}_report_{marker}"
    if report_kind == "quality":
        quality = report.get("quality", {})
        hard_failed = quality.get("num_hard_failed_elements") if isinstance(quality, Mapping) else None
        if hard_failed is None:
            hard_failed = report.get("num_hard_failed_elements")
        if hard_failed != 0:
            return False, "quality_report_hard_failed_elements"
    return True, None


def _run_evidence_is_real(run: Any, root: Path) -> tuple[bool, str | None]:
    if not isinstance(run, Mapping):
        return False, "missing_run_evidence"
    if run.get("status") != "VALID_EVIDENCE":
        return False, str(run.get("reason") or run.get("status") or "invalid_run_evidence")
    if not _mesh_artifact_is_real(run.get("mesh_path"), root):
        return False, "missing_or_placeholder_mesh"
    execution_ok, execution_reason = _json_report_is_real(run.get("execution_report_path"), root, report_kind="execution")
    if not execution_ok:
        return False, execution_reason
    quality_ok, quality_reason = _json_report_is_real(run.get("quality_report_path"), root, report_kind="quality")
    if not quality_ok:
        return False, quality_reason
    return True, None


def _sample_report(path_text: Any, root: Path) -> dict[str, Any] | None:
    if not isinstance(path_text, str):
        return None
    path = Path(path_text)
    if not path.is_absolute() and not path.exists():
        path = root / path
    if not path.is_file():
        return None
    return _read_json(path, "sample_report_read_failed")


def _quantile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    if q <= 0.0:
        return float(min(values))
    if q >= 1.0:
        return float(max(values))
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _csv_items(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = []
        for item in value:
            raw_items.extend(str(item).split(","))
    return tuple(item.strip() for item in raw_items if item.strip())


def _split_sample_ids(dataset_root: Path, split: str) -> list[str]:
    path = dataset_root / "splits" / f"{split}.txt"
    if not path.is_file():
        raise AmgRecommendationBenchmarkError("missing_dataset_split", f"dataset split not found: {split}", path)
    sample_ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not sample_ids:
        raise AmgRecommendationBenchmarkError("empty_dataset_split", f"dataset split is empty: {split}", path)
    return sample_ids


def _accepted_sample_dirs(dataset_root: Path) -> dict[str, Path]:
    index_path = dataset_root / "dataset_index.json"
    index = _read_json(index_path, "dataset_index_read_failed")
    if index.get("schema") != "CDF_DATASET_INDEX_SM_V1":
        raise AmgRecommendationBenchmarkError("dataset_index_schema_invalid", "dataset index schema must be CDF_DATASET_INDEX_SM_V1", index_path)
    accepted = index.get("accepted_samples", [])
    if not isinstance(accepted, list):
        raise AmgRecommendationBenchmarkError("dataset_index_schema_invalid", "accepted_samples must be a list", index_path)
    sample_dirs: dict[str, Path] = {}
    for item in accepted:
        if isinstance(item, str):
            sample_id = item
            sample_dir = dataset_root / "samples" / sample_id
        elif isinstance(item, Mapping):
            sample_id = item.get("sample_id")
            if not isinstance(sample_id, str):
                raise AmgRecommendationBenchmarkError("dataset_index_schema_invalid", "accepted sample record requires sample_id", index_path)
            sample_dir = Path(str(item.get("sample_dir", f"samples/{sample_id}")))
            if not sample_dir.is_absolute():
                sample_dir = dataset_root / sample_dir
        else:
            raise AmgRecommendationBenchmarkError("dataset_index_schema_invalid", "accepted sample records must be objects or strings", index_path)
        sample_dirs[sample_id] = sample_dir
    return sample_dirs


def _build_dataset_coverage_report(
    *,
    dataset: str | Path,
    split: str,
    recommendation_sample_ids: Sequence[str],
    required_part_classes: Sequence[str],
    required_feature_types: Sequence[str],
) -> tuple[dict[str, Any], dict[str, bool]]:
    dataset_root = Path(dataset)
    split_ids = _split_sample_ids(dataset_root, split)
    sample_dirs = _accepted_sample_dirs(dataset_root)
    recommendation_ids = list(recommendation_sample_ids)
    recommendation_set = set(recommendation_ids)
    split_set = set(split_ids)
    part_counts: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    missing_sample_ids: list[str] = []
    for sample_id in split_ids:
        sample_dir = sample_dirs.get(sample_id)
        if sample_dir is None:
            missing_sample_ids.append(sample_id)
            continue
        manifest = _read_json(sample_dir / "labels" / "amg_manifest.json", "manifest_read_failed")
        part = manifest.get("part", {})
        if isinstance(part, Mapping) and isinstance(part.get("part_class"), str):
            part_counts[str(part["part_class"])] += 1
        features = manifest.get("features", [])
        if isinstance(features, list):
            for feature in features:
                if isinstance(feature, Mapping) and isinstance(feature.get("type"), str):
                    feature_counts[str(feature["type"])] += 1
    required_parts = tuple(required_part_classes)
    required_features = tuple(required_feature_types)
    missing_parts = [part_class for part_class in required_parts if part_counts.get(part_class, 0) <= 0]
    missing_features = [feature_type for feature_type in required_features if feature_counts.get(feature_type, 0) <= 0]
    report = {
        "dataset_root": dataset_root.as_posix(),
        "split": split,
        "split_sample_count": len(split_ids),
        "recommendation_sample_count": len(recommendation_ids),
        "missing_sample_ids": missing_sample_ids,
        "missing_recommendation_sample_ids": sorted(split_set - recommendation_set),
        "extra_recommendation_sample_ids": sorted(recommendation_set - split_set),
        "part_class_counts": dict(sorted(part_counts.items())),
        "feature_type_counts": dict(sorted(feature_counts.items())),
        "required_part_classes": list(required_parts),
        "required_feature_types": list(required_features),
        "missing_part_classes": missing_parts,
        "missing_feature_types": missing_features,
    }
    criteria = {
        "recommendation_covers_split": recommendation_set == split_set,
        "dataset_samples_resolve": not missing_sample_ids,
        "required_part_classes_present": not missing_parts,
        "required_feature_types_present": not missing_features,
    }
    return report, criteria


def build_recommendation_benchmark_report(
    *,
    recommendation: str | Path,
    baseline: str | Path | None = None,
    ai_only: bool = False,
    dataset: str | Path | None = None,
    split: str = "test",
    required_part_classes: Sequence[str] = (),
    required_feature_types: Sequence[str] = (),
    min_attempted: int = MIN_ATTEMPTED,
    min_improvement_rate: float = MIN_IMPROVEMENT_RATE,
    min_median_delta: float = MIN_MEDIAN_DELTA,
    improvement_epsilon: float = IMPROVEMENT_EPSILON,
    severe_regression_threshold: float = SEVERE_REGRESSION_THRESHOLD,
    max_severe_regression_count: int = MAX_SEVERE_REGRESSION_COUNT,
) -> dict[str, Any]:
    root = Path(recommendation)
    summary_path = _summary_path(root)
    summary = _read_json(summary_path, "recommendation_summary_read_failed")
    sample_results = summary.get("sample_results", [])
    if not isinstance(sample_results, list) or not all(isinstance(item, Mapping) for item in sample_results):
        raise AmgRecommendationBenchmarkError("malformed_recommendation_summary", "sample_results must be a list of objects", summary_path)
    if ai_only and baseline is not None:
        raise AmgRecommendationBenchmarkError("ai_only_baseline_argument", "--ai-only cannot use --baseline comparison")

    deltas: list[float] = []
    failure_counts: Counter[str] = Counter()
    invalid_artifacts = 0
    valid_evidence_count = 0
    improved_count = 0
    selected_non_baseline_count = 0
    selected_baseline_count = 0
    risk_rejected_candidate_count = 0
    recommended_scores: list[float] = []
    selected_evaluation_ids: list[str] = []
    recommendation_sample_ids: list[str] = []
    for result in sample_results:
        sample_id = result.get("sample_id")
        if isinstance(sample_id, str):
            recommendation_sample_ids.append(sample_id)
        report = _sample_report(result.get("report_path"), root)
        if report is None:
            failure_counts["missing_sample_report"] += 1
            continue
        result_status = result.get("status")
        report_status = report.get("status")
        if result_status == "FAILED" or report_status == "FAILED":
            code = result.get("error_code") or report.get("error_code") or "sample_failed"
            failure_counts[str(code)] += 1
            continue
        if result.get("selected_evaluation_id") not in {None, "baseline"}:
            selected_non_baseline_count += 1
            selected_evaluation_ids.append(str(result.get("selected_evaluation_id")))
        elif result.get("selected_evaluation_id") == "baseline":
            selected_baseline_count += 1
        risk_rejected_candidate_count += int(result.get("risk_rejected_candidate_count", 0) or 0)
        baseline_run = report.get("baseline_run", {})
        recommended_run = report.get("recommended_run", {})
        if ai_only:
            if summary.get("compare_baseline") is not False:
                failure_counts["baseline_comparison_enabled"] += 1
                continue
            if result.get("selected_evaluation_id") in {None, "baseline"}:
                failure_counts["missing_non_baseline_recommendation"] += 1
                continue
            if baseline_run not in (None, {}):
                failure_counts["baseline_run_present"] += 1
                continue
            run_ok, run_reason = _run_evidence_is_real(recommended_run, root)
            if not run_ok:
                invalid_artifacts += 1
                failure_counts[str(run_reason)] += 1
                continue
            recommended_score = result.get("recommended_score")
            if not isinstance(recommended_score, (int, float)):
                failure_counts["missing_recommended_quality_score"] += 1
                continue
            recommended_scores.append(float(recommended_score))
            valid_evidence_count += 1
            continue
        if not isinstance(baseline_run, Mapping) or not isinstance(recommended_run, Mapping):
            failure_counts["missing_run_evidence"] += 1
            continue
        baseline_ok, baseline_reason = _run_evidence_is_real(baseline_run, root)
        recommended_ok, recommended_reason = _run_evidence_is_real(recommended_run, root)
        if not baseline_ok or not recommended_ok:
            invalid_artifacts += 1
            failure_counts[str(baseline_reason or recommended_reason)] += 1
            continue
        baseline_score = result.get("baseline_score")
        recommended_score = result.get("recommended_score")
        delta = result.get("improvement_delta")
        if not isinstance(baseline_score, (int, float)) or not isinstance(recommended_score, (int, float)) or not isinstance(delta, (int, float)):
            failure_counts["missing_quality_scores"] += 1
            continue
        valid_evidence_count += 1
        deltas.append(float(delta))
        if float(delta) > improvement_epsilon:
            improved_count += 1
    attempted_count = len(sample_results)
    improvement_rate = improved_count / valid_evidence_count if valid_evidence_count and not ai_only else 0.0
    median_delta = statistics.median(deltas) if deltas else None
    mean_delta = statistics.mean(deltas) if deltas else None
    worst_delta = min(deltas) if deltas else None
    lower_tail_p10 = _quantile(deltas, 0.10)
    lower_tail_p25 = _quantile(deltas, 0.25)
    severe_regression_count = sum(1 for delta in deltas if delta < severe_regression_threshold)
    if ai_only:
        criteria = {
            "minimum_attempted": attempted_count >= min_attempted,
            "all_ai_recommendations_valid": valid_evidence_count == attempted_count and attempted_count > 0,
            "no_invalid_artifacts": invalid_artifacts == 0,
            "all_selected_non_baseline": selected_non_baseline_count == attempted_count and selected_baseline_count == 0,
            "baseline_comparison_disabled": summary.get("compare_baseline") is False,
        }
    else:
        criteria = {
            "minimum_attempted": attempted_count >= min_attempted,
            "all_pairs_valid": valid_evidence_count == attempted_count and attempted_count > 0,
            "no_invalid_artifacts": invalid_artifacts == 0,
            "non_baseline_selected": selected_non_baseline_count > 0,
            "no_baseline_recommendations": selected_baseline_count == 0,
            "improvement_rate_met": improvement_rate >= min_improvement_rate,
            "median_improvement_delta_met": median_delta is not None and median_delta >= min_median_delta,
            "severe_regression_count_met": severe_regression_count <= max_severe_regression_count,
            "worst_improvement_delta_met": worst_delta is not None and worst_delta >= severe_regression_threshold,
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
    coverage_report = None
    if dataset is not None:
        coverage_report, coverage_criteria = _build_dataset_coverage_report(
            dataset=dataset,
            split=split,
            recommendation_sample_ids=recommendation_sample_ids,
            required_part_classes=tuple(required_part_classes),
            required_feature_types=tuple(required_feature_types),
        )
        criteria.update(coverage_criteria)
    return {
        "schema": "AMG_QUALITY_RECOMMENDATION_BENCHMARK_V1",
        "mode": "AI_ONLY" if ai_only else "BASELINE_COMPARISON",
        "status": "SUCCESS" if all(criteria.values()) else "FAILED",
        "recommendation_root": root.as_posix(),
        "recommendation_summary_path": summary_path.as_posix(),
        "attempted_count": attempted_count,
        "valid_pair_count": valid_evidence_count if not ai_only else 0,
        "valid_mesh_count": valid_evidence_count if ai_only else 0,
        "improved_count": improved_count,
        "improvement_rate": improvement_rate,
        "improvement_epsilon": improvement_epsilon,
        "mean_improvement_delta": mean_delta,
        "median_improvement_delta": median_delta,
        "worst_improvement_delta": worst_delta,
        "lower_tail_delta_p10": lower_tail_p10,
        "lower_tail_delta_p25": lower_tail_p25,
        "severe_regression_threshold": severe_regression_threshold,
        "severe_regression_count": severe_regression_count,
        "selected_non_baseline_count": selected_non_baseline_count,
        "selected_baseline_count": selected_baseline_count,
        "selected_evaluation_ids": selected_evaluation_ids,
        "recommended_quality_score_min": min(recommended_scores) if recommended_scores else None,
        "recommended_quality_score_median": statistics.median(recommended_scores) if recommended_scores else None,
        "recommended_quality_score_max": max(recommended_scores) if recommended_scores else None,
        "risk_rejected_candidate_count": risk_rejected_candidate_count,
        "failure_reason_counts": dict(sorted(failure_counts.items())),
        "invalid_artifact_count": invalid_artifacts,
        "success_criteria": criteria,
        "baseline_comparison": baseline_comparison,
        "coverage": coverage_report,
    }


def write_recommendation_benchmark_report(path: str | Path, report: Mapping[str, Any]) -> None:
    _write_json(Path(path), report)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark real ANSA quality recommendations.")
    parser.add_argument("--recommendation", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--ai-only", action="store_true")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--split", default="test")
    parser.add_argument("--required-part-classes", default="")
    parser.add_argument("--required-feature-types", default="")
    parser.add_argument("--min-attempted", type=int, default=MIN_ATTEMPTED)
    parser.add_argument("--min-improvement-rate", type=float, default=MIN_IMPROVEMENT_RATE)
    parser.add_argument("--min-median-delta", type=float, default=MIN_MEDIAN_DELTA)
    parser.add_argument("--improvement-epsilon", type=float, default=IMPROVEMENT_EPSILON)
    parser.add_argument("--severe-regression-threshold", type=float, default=SEVERE_REGRESSION_THRESHOLD)
    parser.add_argument("--max-severe-regression-count", type=int, default=MAX_SEVERE_REGRESSION_COUNT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_recommendation_benchmark_report(
            recommendation=Path(args.recommendation),
            baseline=Path(args.baseline) if args.baseline else None,
            ai_only=bool(args.ai_only),
            dataset=Path(args.dataset) if args.dataset else None,
            split=str(args.split),
            required_part_classes=_csv_items(args.required_part_classes),
            required_feature_types=_csv_items(args.required_feature_types),
            min_attempted=args.min_attempted,
            min_improvement_rate=args.min_improvement_rate,
            min_median_delta=args.min_median_delta,
            improvement_epsilon=args.improvement_epsilon,
            severe_regression_threshold=args.severe_regression_threshold,
            max_severe_regression_count=args.max_severe_regression_count,
        )
        write_recommendation_benchmark_report(args.out, report)
    except AmgRecommendationBenchmarkError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": report["status"], "out": Path(args.out).as_posix()}, indent=2, sort_keys=True))
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
