"""Aggregate real AMG pipeline evidence from file-contract artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class AmgBenchmarkReportError(ValueError):
    """Raised when benchmark evidence is missing or cannot be trusted."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgBenchmarkReportError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgBenchmarkReportError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgBenchmarkReportError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _sample_records(dataset_root: Path) -> list[dict[str, Any]]:
    index = _read_json(dataset_root / "dataset_index.json", "dataset_index_read_failed")
    if index.get("schema") != "CDF_DATASET_INDEX_SM_V1":
        raise AmgBenchmarkReportError("dataset_index_schema_invalid", "dataset index schema must be CDF_DATASET_INDEX_SM_V1", dataset_root)
    records = index.get("accepted_samples", [])
    if not isinstance(records, list) or not all(isinstance(item, Mapping) for item in records):
        raise AmgBenchmarkReportError("dataset_index_schema_invalid", "accepted_samples must be a list of objects", dataset_root)
    return [dict(item) for item in records]


def _sample_dir(dataset_root: Path, record: Mapping[str, Any]) -> Path:
    sample_id = record.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id:
        raise AmgBenchmarkReportError("dataset_index_schema_invalid", "accepted sample records require sample_id", dataset_root)
    sample_dir = record.get("sample_dir", f"samples/{sample_id}")
    if not isinstance(sample_dir, str) or not sample_dir:
        raise AmgBenchmarkReportError("dataset_index_schema_invalid", "accepted sample records require sample_dir", dataset_root)
    path = Path(sample_dir)
    return path if path.is_absolute() else dataset_root / path


def _split_count(dataset_root: Path, split: str) -> int:
    path = dataset_root / "splits" / f"{split}.txt"
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))


def _dataset_coverage(dataset_root: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    part_classes: Counter[str] = Counter()
    feature_types: Counter[str] = Counter()
    feature_roles: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    features_per_sample: Counter[str] = Counter()
    manifest_paths: list[str] = []
    for record in records:
        sample_dir = _sample_dir(dataset_root, record)
        manifest_path = sample_dir / "labels" / "amg_manifest.json"
        manifest = _read_json(manifest_path, "manifest_read_failed")
        if manifest.get("schema_version") != "AMG_MANIFEST_SM_V1" or manifest.get("status") != "VALID":
            raise AmgBenchmarkReportError("manifest_not_valid", "benchmark accepted samples require VALID AMG manifests", manifest_path)
        part = manifest.get("part", {})
        if not isinstance(part, Mapping):
            raise AmgBenchmarkReportError("manifest_not_valid", "manifest part must be an object", manifest_path)
        part_classes[str(part.get("part_class", "UNKNOWN"))] += 1
        features = manifest.get("features", [])
        if not isinstance(features, list):
            raise AmgBenchmarkReportError("manifest_not_valid", "manifest features must be a list", manifest_path)
        features_per_sample[str(len(features))] += 1
        for feature in features:
            if not isinstance(feature, Mapping):
                raise AmgBenchmarkReportError("manifest_not_valid", "manifest feature records must be objects", manifest_path)
            feature_types[str(feature.get("type", "UNKNOWN"))] += 1
            feature_roles[str(feature.get("role", "UNKNOWN"))] += 1
            actions[str(feature.get("action", "UNKNOWN"))] += 1
        manifest_paths.append(manifest_path.as_posix())
    return {
        "accepted_sample_count": len(records),
        "part_class_histogram": dict(sorted(part_classes.items())),
        "feature_type_histogram": dict(sorted(feature_types.items())),
        "feature_role_histogram": dict(sorted(feature_roles.items())),
        "action_histogram": dict(sorted(actions.items())),
        "features_per_sample_histogram": dict(sorted(features_per_sample.items())),
        "split_counts": {
            "train": _split_count(dataset_root, "train"),
            "val": _split_count(dataset_root, "val"),
            "test": _split_count(dataset_root, "test"),
        },
        "manifest_paths": manifest_paths,
    }


def _resolve_artifact(path_value: Any, *, root: Path | None = None) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise AmgBenchmarkReportError("missing_artifact_path", "artifact path must be a non-empty string")
    path = Path(path_value)
    if path.is_absolute() or path.exists():
        return path
    if root is not None and (root / path).exists():
        return root / path
    return path


def _mesh_is_real(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    head = path.read_text(encoding="utf-8", errors="ignore")[:512].lower()
    return "mock" not in head and "placeholder" not in head


def _validate_valid_mesh_result(result: Mapping[str, Any], inference_root: Path) -> tuple[int, str | None]:
    execution_path = _resolve_artifact(result.get("execution_report_path"), root=inference_root)
    quality_path = _resolve_artifact(result.get("quality_report_path"), root=inference_root)
    mesh_path = _resolve_artifact(result.get("solver_deck_path"), root=inference_root)
    execution = _read_json(execution_path, "execution_report_read_failed")
    quality = _read_json(quality_path, "quality_report_read_failed")
    outputs = execution.get("outputs", {})
    if isinstance(outputs, Mapping) and "controlled_failure_reason" in outputs:
        return 0, "controlled_failure_report"
    if execution.get("ansa_version") in {"unavailable", "mock-ansa"}:
        return 0, "non_real_ansa_report"
    hard_failed = int(quality.get("quality", {}).get("num_hard_failed_elements", 1))
    if execution.get("accepted") is not True:
        return hard_failed, "execution_not_accepted"
    if quality.get("accepted") is not True:
        return hard_failed, "quality_not_accepted"
    if hard_failed != 0:
        return hard_failed, "hard_failed_elements"
    if not _mesh_is_real(mesh_path):
        return hard_failed, "missing_or_placeholder_mesh"
    return hard_failed, None


def _inference_evidence(inference_root: Path) -> dict[str, Any]:
    summary_path = inference_root / "inference_summary.json"
    summary = _read_json(summary_path, "inference_summary_read_failed")
    sample_results = summary.get("sample_results", [])
    if not isinstance(sample_results, list):
        raise AmgBenchmarkReportError("inference_summary_invalid", "sample_results must be a list", summary_path)
    attempted = len(sample_results)
    success = 0
    first_pass_success = 0
    retry_success = 0
    hard_failed_counts: list[int] = []
    failure_counts: Counter[str] = Counter()
    valid_mesh_paths: list[str] = []
    for result in sample_results:
        if not isinstance(result, Mapping):
            raise AmgBenchmarkReportError("inference_summary_invalid", "sample result entries must be objects", summary_path)
        status = str(result.get("status"))
        attempts = int(result.get("attempts", 0))
        if status == "VALID_MESH":
            hard_failed, failure = _validate_valid_mesh_result(result, inference_root)
            hard_failed_counts.append(hard_failed)
            if failure is not None:
                failure_counts[failure] += 1
                continue
            success += 1
            if attempts <= 1:
                first_pass_success += 1
            else:
                retry_success += 1
            valid_mesh_paths.append(str(result.get("solver_deck_path")))
        else:
            failure_counts[str(result.get("error_code") or status)] += 1
    return {
        "summary_path": summary_path.as_posix(),
        "attempted_count": attempted,
        "valid_mesh_count": success,
        "failed_count": attempted - success,
        "first_pass_valid_mesh_count": first_pass_success,
        "retry_valid_mesh_count": retry_success,
        "after_retry_valid_mesh_rate": float(success / attempted) if attempted else 0.0,
        "first_pass_valid_mesh_rate": float(first_pass_success / attempted) if attempted else 0.0,
        "failure_reason_counts": dict(sorted(failure_counts.items())),
        "hard_failed_element_counts": hard_failed_counts,
        "valid_mesh_paths": valid_mesh_paths,
    }


def build_real_pipeline_benchmark_report(
    *,
    dataset: str | Path,
    training: str | Path,
    inference: str | Path,
) -> dict[str, Any]:
    dataset_root = Path(dataset)
    training_root = Path(training)
    inference_root = Path(inference)
    records = _sample_records(dataset_root)
    coverage = _dataset_coverage(dataset_root, records)
    training_metrics_path = training_root / "metrics.json"
    training_metrics = _read_json(training_metrics_path, "training_metrics_read_failed")
    if training_metrics.get("status") != "SUCCESS":
        raise AmgBenchmarkReportError("training_not_successful", "training metrics must have status SUCCESS", training_metrics_path)
    inference_evidence = _inference_evidence(inference_root)
    label_coverage = float(training_metrics.get("label_coverage_ratio", 0.0))
    attempted = int(inference_evidence["attempted_count"])
    valid_rate = float(inference_evidence["after_retry_valid_mesh_rate"])
    required_part_classes = {"SM_FLAT_PANEL", "SM_L_BRACKET"}
    required_feature_types = {"HOLE", "SLOT", "CUTOUT", "BEND", "FLANGE"}
    part_coverage_ok = required_part_classes.issubset(set(coverage["part_class_histogram"]))
    feature_coverage_ok = required_feature_types.issubset(set(coverage["feature_type_histogram"]))
    success_criteria = {
        "dataset_validation_required": True,
        "accepted_sample_count_at_least_150": int(coverage["accepted_sample_count"]) >= 150,
        "required_part_coverage": part_coverage_ok,
        "required_feature_coverage": feature_coverage_ok,
        "training_status_success": True,
        "label_coverage_ratio_at_least_0_98": label_coverage >= 0.98,
        "inference_attempted_at_least_20": attempted >= 20,
        "after_retry_valid_mesh_rate_at_least_0_80": valid_rate >= 0.80,
    }
    overall_status = "SUCCESS" if all(success_criteria.values()) else "FAILED"
    return {
        "schema": "AMG_REAL_PIPELINE_BENCHMARK_REPORT_V1",
        "status": overall_status,
        "dataset_root": dataset_root.as_posix(),
        "training_root": training_root.as_posix(),
        "inference_root": inference_root.as_posix(),
        "coverage": coverage,
        "training": {
            "metrics_path": training_metrics_path.as_posix(),
            "sample_count": training_metrics.get("sample_count"),
            "candidate_count": training_metrics.get("candidate_count"),
            "manifest_feature_count": training_metrics.get("manifest_feature_count"),
            "matched_target_count": training_metrics.get("matched_target_count"),
            "label_coverage_ratio": label_coverage,
            "train_loss_total": training_metrics.get("train_loss_total"),
            "val_loss_total": training_metrics.get("val_loss_total"),
            "checkpoint_path": training_metrics.get("checkpoint_path"),
        },
        "inference": inference_evidence,
        "success_criteria": success_criteria,
    }


def write_real_pipeline_benchmark_report(path: str | Path, report: Mapping[str, Any]) -> None:
    _write_json(Path(path), report)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate real AMG pipeline benchmark evidence.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--training", required=True)
    parser.add_argument("--inference", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_real_pipeline_benchmark_report(
            dataset=Path(args.dataset),
            training=Path(args.training),
            inference=Path(args.inference),
        )
        write_real_pipeline_benchmark_report(args.out, report)
    except AmgBenchmarkReportError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": report["status"], "out": Path(args.out).as_posix()}, indent=2, sort_keys=True))
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
