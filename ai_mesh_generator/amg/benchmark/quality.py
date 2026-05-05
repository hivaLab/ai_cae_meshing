"""Aggregate quality-exploration evidence for AMG control learning."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class AmgQualityBenchmarkError(ValueError):
    """Raised when quality-learning benchmark evidence is missing or malformed."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgQualityBenchmarkError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgQualityBenchmarkError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgQualityBenchmarkError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _quality_summary_path(root: Path) -> Path:
    if root.is_file():
        return root
    path = root / "quality_exploration_summary.json"
    if not path.is_file():
        raise AmgQualityBenchmarkError("missing_quality_exploration_summary", "quality exploration summary not found", root)
    return path


def _training_metrics_path(root: Path) -> Path:
    if root.is_file():
        return root
    for filename in ("quality_training_metrics.json", "metrics.json"):
        path = root / filename
        if path.is_file():
            return path
    raise AmgQualityBenchmarkError("missing_quality_training_metrics", "quality training metrics not found", root)


def _resolve_path(path_value: Any, *, roots: Sequence[Path]) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise AmgQualityBenchmarkError("missing_artifact_path", "artifact path must be a non-empty string")
    path = Path(path_value)
    if path.is_absolute() or path.exists():
        return path
    for root in roots:
        candidate = root / path
        if candidate.exists():
            return candidate
    return path


def _entropy(counts: Mapping[str, int | float]) -> float:
    total = float(sum(float(value) for value in counts.values()))
    if total <= 0:
        return 0.0
    entropy = 0.0
    for value in counts.values():
        probability = float(value) / total
        if probability > 0:
            entropy -= probability * math.log2(probability)
    return entropy


def _manifest_controls(manifest: Mapping[str, Any]) -> tuple[Counter[str], Counter[str], list[float]]:
    action_counts: Counter[str] = Counter()
    feature_type_counts: Counter[str] = Counter()
    control_values: list[float] = []
    features = manifest.get("features", [])
    if not isinstance(features, list):
        raise AmgQualityBenchmarkError("manifest_not_valid", "manifest features must be a list")
    for feature in features:
        if not isinstance(feature, Mapping):
            raise AmgQualityBenchmarkError("manifest_not_valid", "manifest features must be objects")
        action_counts[str(feature.get("action", "UNKNOWN"))] += 1
        feature_type_counts[str(feature.get("type", "UNKNOWN"))] += 1
        controls = feature.get("controls", {})
        if isinstance(controls, Mapping):
            for key in (
                "edge_target_length_mm",
                "bend_target_length_mm",
                "flange_target_length_mm",
                "growth_rate",
                "radial_growth_rate",
                "perimeter_growth_rate",
                "washer_rings",
                "bend_rows",
                "circumferential_divisions",
                "end_arc_divisions",
                "straight_edge_divisions",
                "min_elements_across_width",
            ):
                value = controls.get(key)
                if isinstance(value, (int, float)):
                    control_values.append(float(value))
    return action_counts, feature_type_counts, control_values


def _record_coverage(records: Sequence[Mapping[str, Any]], roots: Sequence[Path]) -> dict[str, Any]:
    action_counts: Counter[str] = Counter()
    feature_type_counts: Counter[str] = Counter()
    control_values: list[float] = []
    for record in records:
        manifest_path = _resolve_path(record.get("manifest_path"), roots=roots)
        manifest = _read_json(manifest_path, "manifest_read_failed")
        actions, feature_types, values = _manifest_controls(manifest)
        action_counts.update(actions)
        feature_type_counts.update(feature_types)
        control_values.extend(values)
    return {
        "action_histogram": dict(sorted(action_counts.items())),
        "feature_type_histogram": dict(sorted(feature_type_counts.items())),
        "action_entropy_bits": _entropy(action_counts),
        "feature_type_entropy_bits": _entropy(feature_type_counts),
        "control_value_count": len(control_values),
        "control_value_variance": statistics.pvariance(control_values) if len(control_values) >= 2 else 0.0,
    }


def _quality_evidence(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status", "UNKNOWN")) for record in records)
    scores = [float(record["quality_score"]) for record in records if isinstance(record.get("quality_score"), (int, float))]
    pass_count = sum(1 for record in records if record.get("status") == "PASSED")
    fail_count = sum(1 for record in records if record.get("status") == "FAILED")
    blocked_count = sum(1 for record in records if record.get("status") == "BLOCKED")
    accepted_count = sum(1 for record in records if record.get("accepted") is True)
    near_fail_count = sum(
        1
        for record in records
        if record.get("status") == "FAILED" and isinstance(record.get("quality_score"), (int, float))
    )
    by_sample: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        sample_id = record.get("sample_id")
        if isinstance(sample_id, str):
            by_sample[sample_id].append(record)
    improvements: list[float] = []
    positive_improvement_count = 0
    for sample_records in by_sample.values():
        baseline_scores = [
            float(record["quality_score"])
            for record in sample_records
            if record.get("evaluation_id") == "baseline" and isinstance(record.get("quality_score"), (int, float))
        ]
        scored = [float(record["quality_score"]) for record in sample_records if isinstance(record.get("quality_score"), (int, float))]
        if baseline_scores and scored:
            improvement = baseline_scores[0] - min(scored)
            improvements.append(improvement)
            if improvement > 0:
                positive_improvement_count += 1
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "record_count": len(records),
        "scored_record_count": len(scores),
        "accepted_record_count": accepted_count,
        "passed_count": pass_count,
        "failed_count": fail_count,
        "blocked_count": blocked_count,
        "near_fail_count": near_fail_count,
        "quality_score_variance": statistics.pvariance(scores) if len(scores) >= 2 else 0.0,
        "quality_score_min": min(scores) if scores else None,
        "quality_score_max": max(scores) if scores else None,
        "baseline_best_improvement_mean": statistics.mean(improvements) if improvements else 0.0,
        "baseline_best_positive_improvement_count": positive_improvement_count,
    }


def build_quality_benchmark_report(
    *,
    dataset: str | Path,
    quality_exploration: str | Path,
    training: str | Path,
) -> dict[str, Any]:
    dataset_root = Path(dataset)
    quality_root = Path(quality_exploration)
    training_root = Path(training)
    summary_path = _quality_summary_path(quality_root)
    summary = _read_json(summary_path, "quality_summary_read_failed")
    records = summary.get("records", [])
    if not isinstance(records, list) or not all(isinstance(item, Mapping) for item in records):
        raise AmgQualityBenchmarkError("malformed_quality_summary", "records must be a list of objects", summary_path)
    if not records:
        raise AmgQualityBenchmarkError("empty_quality_records", "quality benchmark requires exploration records", summary_path)
    metrics_path = _training_metrics_path(training_root)
    training_metrics = _read_json(metrics_path, "quality_training_metrics_read_failed")
    if training_metrics.get("status") != "SUCCESS":
        raise AmgQualityBenchmarkError("quality_training_not_successful", "quality training metrics must have status SUCCESS", metrics_path)

    roots = (Path.cwd(), quality_root, dataset_root)
    coverage = _record_coverage(records, roots)
    evidence = _quality_evidence(records)
    validation_accuracy = float(training_metrics.get("validation_pairwise_accuracy", 0.0) or 0.0)
    criteria = {
        "no_blocked_quality_records": int(evidence["blocked_count"]) == 0,
        "quality_score_variance_nonzero": float(evidence["quality_score_variance"]) > 0.0,
        "action_entropy_nonzero": float(coverage["action_entropy_bits"]) > 0.0,
        "control_value_variance_nonzero": float(coverage["control_value_variance"]) > 0.0,
        "has_pass_and_fail_or_near_fail_examples": int(evidence["passed_count"]) > 0 and (int(evidence["failed_count"]) > 0 or int(evidence["near_fail_count"]) > 0),
        "held_out_pairwise_accuracy_above_random": validation_accuracy > 0.50,
    }
    status = "SUCCESS" if all(criteria.values()) else "FAILED"
    return {
        "schema": "AMG_QUALITY_BENCHMARK_REPORT_V1",
        "status": status,
        "dataset_root": dataset_root.as_posix(),
        "quality_exploration_root": quality_root.as_posix(),
        "training_root": training_root.as_posix(),
        "quality_summary_path": summary_path.as_posix(),
        "training_metrics_path": metrics_path.as_posix(),
        "coverage": coverage,
        "quality_evidence": evidence,
        "training": {
            "example_count": training_metrics.get("example_count"),
            "train_pair_count": training_metrics.get("train_pair_count"),
            "validation_pair_count": training_metrics.get("validation_pair_count"),
            "train_pairwise_accuracy": training_metrics.get("train_pairwise_accuracy"),
            "validation_pairwise_accuracy": training_metrics.get("validation_pairwise_accuracy"),
            "quality_score_variance": training_metrics.get("quality_score_variance"),
            "checkpoint_path": training_metrics.get("checkpoint_path"),
        },
        "success_criteria": criteria,
    }


def write_quality_benchmark_report(path: str | Path, report: Mapping[str, Any]) -> None:
    _write_json(Path(path), report)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate AMG quality-learning benchmark evidence.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--quality-exploration", required=True)
    parser.add_argument("--training", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_quality_benchmark_report(
            dataset=Path(args.dataset),
            quality_exploration=Path(args.quality_exploration),
            training=Path(args.training),
        )
        write_quality_benchmark_report(args.out, report)
    except AmgQualityBenchmarkError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": report["status"], "out": Path(args.out).as_posix()}, indent=2, sort_keys=True))
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
