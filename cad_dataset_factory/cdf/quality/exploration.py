"""Real-ANSA quality exploration for accepted CDF samples."""

from __future__ import annotations

import copy
import json
import math
import shutil
import statistics
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.oracle import AnsaRunRequest, AnsaRunnerConfig, run_ansa_oracle

CONTINUOUS_QUALITY_KEYS = (
    "average_shell_length_mm",
    "min_shell_side_length_mm",
    "average_shell_side_length_mm",
    "max_shell_side_length_mm",
    "side_length_spread_ratio",
    "aspect_ratio_proxy_max",
    "triangles_percent",
)
QUALITY_SCORE_NEAR_FAIL_THRESHOLD = 5.0


class CdfQualityExplorationError(ValueError):
    """Raised when quality exploration cannot proceed safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class QualityExplorationResult:
    status: str
    output_dir: str
    summary_path: str
    baseline_count: int
    evaluated_count: int
    passed_count: int
    near_fail_count: int
    failed_count: int
    blocked_count: int
    quality_score_variance: float


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CdfQualityExplorationError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise CdfQualityExplorationError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise CdfQualityExplorationError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _manifest_validator() -> Draft202012Validator:
    schema = _read_json(_repo_root() / "contracts" / "AMG_MANIFEST_SM_V1.schema.json", "schema_read_failed")
    return Draft202012Validator(schema)


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(manifest), allow_nan=False))
    errors = sorted(_manifest_validator().iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise CdfQualityExplorationError("manifest_schema_invalid", f"{location}: {first.message}")
    return normalized


def _accepted_sample_dirs(dataset_root: Path) -> list[Path]:
    index = _read_json(dataset_root / "dataset_index.json", "dataset_index_read_failed")
    records = index.get("accepted_samples")
    if not isinstance(records, list):
        raise CdfQualityExplorationError("malformed_dataset_index", "accepted_samples must be a list", dataset_root)
    sample_dirs: list[Path] = []
    for record in records:
        if isinstance(record, str):
            sample_dirs.append(dataset_root / "samples" / record)
        elif isinstance(record, Mapping):
            sample_dir = record.get("sample_dir")
            sample_id = record.get("sample_id")
            if not isinstance(sample_id, str):
                raise CdfQualityExplorationError("malformed_dataset_index", "accepted records require sample_id", dataset_root)
            relative = sample_dir if isinstance(sample_dir, str) else f"samples/{sample_id}"
            sample_dirs.append(dataset_root / relative)
        else:
            raise CdfQualityExplorationError("malformed_dataset_index", "accepted records must be strings or objects", dataset_root)
    return sample_dirs


def _has_continuous_quality(quality: Mapping[str, Any]) -> bool:
    return any(isinstance(quality.get(key), (int, float)) for key in CONTINUOUS_QUALITY_KEYS)


def compute_quality_score(quality_report: Mapping[str, Any], execution_report: Mapping[str, Any] | None = None) -> float:
    """Return lower-is-better scalar score from real ANSA quality evidence."""

    quality = quality_report.get("quality", {})
    feature_checks = quality_report.get("feature_checks", [])
    if not isinstance(quality, Mapping):
        raise CdfQualityExplorationError("malformed_quality_report", "quality must be an object")
    hard_failed = int(quality.get("num_hard_failed_elements", 1))
    boundary_error = 0.0
    if isinstance(feature_checks, list):
        for check in feature_checks:
            if isinstance(check, Mapping) and isinstance(check.get("boundary_size_error"), (int, float)):
                boundary_error = max(boundary_error, abs(float(check["boundary_size_error"])))
    if not _has_continuous_quality(quality):
        if hard_failed > 0:
            return 1000.0 * hard_failed + 10.0 * boundary_error
        raise CdfQualityExplorationError("quality_metric_unavailable", "continuous quality metrics are required")
    violating = float(quality.get("violating_shell_elements_total", 0.0) or 0.0)
    spread = float(quality.get("side_length_spread_ratio", 0.0) or 0.0)
    aspect_proxy = max(1.0, float(quality.get("aspect_ratio_proxy_max", 1.0) or 1.0))
    triangles_percent = float(quality.get("triangles_percent", 0.0) or 0.0)
    shell_elements = float(quality.get("num_shell_elements", quality_report.get("mesh_stats", {}).get("num_shell_elements", 0.0)) or 0.0)
    runtime = 0.0
    if isinstance(execution_report, Mapping) and isinstance(execution_report.get("runtime_sec"), (int, float)):
        runtime = float(execution_report["runtime_sec"])
    return (
        1000.0 * hard_failed
        + 100.0 * violating
        + 25.0 * spread
        + 10.0 * max(0.0, aspect_proxy - 1.0)
        + 10.0 * boundary_error
        + 0.05 * triangles_percent
        + 0.001 * shell_elements
        + 0.001 * runtime
    )


def _is_near_fail_quality(quality_report: Mapping[str, Any]) -> bool:
    quality = quality_report.get("quality", {})
    if not isinstance(quality, Mapping):
        return False
    hard_failed = int(quality.get("num_hard_failed_elements", 0) or 0)
    if hard_failed > 0:
        return False
    explicit_margins = (
        "violating_shell_elements_total",
        "unmeshed_shell_count",
    )
    return any(float(quality.get(key, 0.0) or 0.0) > 0.0 for key in explicit_margins)


def _is_near_fail_score(quality_score: float | None) -> bool:
    return quality_score is not None and quality_score >= QUALITY_SCORE_NEAR_FAIL_THRESHOLD


def _clamp_mesh_size(value: float, global_mesh: Mapping[str, Any]) -> float:
    h_min = float(global_mesh.get("h_min_mm", 0.1))
    h_max = float(global_mesh.get("h_max_mm", max(h_min, value)))
    return max(h_min, min(h_max, value))


def perturb_manifest(manifest: Mapping[str, Any], perturbation: Mapping[str, Any]) -> dict[str, Any]:
    """Build a schema-valid candidate manifest without mutating the baseline."""

    mutated = copy.deepcopy(dict(manifest))
    global_mesh = mutated.get("global_mesh", {})
    if not isinstance(global_mesh, Mapping):
        raise CdfQualityExplorationError("malformed_manifest", "global_mesh must be an object")
    kind = str(perturbation.get("kind", "baseline"))
    for feature in mutated.get("features", []):
        if not isinstance(feature, dict):
            continue
        controls = feature.get("controls")
        if not isinstance(controls, dict):
            continue
        if kind == "edge_length_scale":
            scale = float(perturbation["scale"])
            for key in ("edge_target_length_mm", "bend_target_length_mm", "flange_target_length_mm"):
                if isinstance(controls.get(key), (int, float)):
                    controls[key] = _clamp_mesh_size(float(controls[key]) * scale, global_mesh)
        elif kind == "growth_rate":
            value = float(perturbation["value"])
            for key in ("growth_rate", "radial_growth_rate", "perimeter_growth_rate"):
                if key in controls:
                    controls[key] = value
        elif kind == "bend_rows" and feature.get("type") == "BEND":
            controls["bend_rows"] = int(perturbation["value"])
        elif kind == "washer_rings" and feature.get("action") == "KEEP_WITH_WASHER":
            controls["washer_rings"] = int(perturbation["value"])
        elif kind == "suppress_small" and feature.get("type") in {"HOLE", "SLOT", "CUTOUT"} and feature.get("role") in {"RELIEF", "DRAIN"}:
            feature["action"] = "SUPPRESS"
            feature["controls"] = {"suppression_rule": "quality_exploration_action_swap"}
    return _validate_manifest(mutated)


def _perturbation_specs(manifest: Mapping[str, Any], count: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = [
        {"kind": "edge_length_scale", "scale": 0.5},
        {"kind": "edge_length_scale", "scale": 0.75},
        {"kind": "edge_length_scale", "scale": 1.25},
        {"kind": "edge_length_scale", "scale": 1.5},
        {"kind": "growth_rate", "value": 1.05},
        {"kind": "growth_rate", "value": 1.35},
    ]
    features = [feature for feature in manifest.get("features", []) if isinstance(feature, Mapping)]
    if any(feature.get("type") == "BEND" for feature in features):
        candidates.extend({"kind": "bend_rows", "value": value} for value in (1, 2, 4, 6))
    if any(feature.get("action") == "KEEP_WITH_WASHER" for feature in features):
        candidates.extend({"kind": "washer_rings", "value": value} for value in (0, 1, 3))
    if any(feature.get("type") in {"HOLE", "SLOT", "CUTOUT"} and feature.get("role") in {"RELIEF", "DRAIN"} for feature in features):
        candidates.append({"kind": "suppress_small"})
    return candidates[: max(0, count)]


def _record_from_reports(
    *,
    sample_id: str,
    evaluation_id: str,
    perturbation: Mapping[str, Any],
    manifest_path: Path,
    execution_report_path: Path,
    quality_report_path: Path,
    mesh_path: Path | None,
) -> dict[str, Any]:
    execution = _read_json(execution_report_path, "execution_report_read_failed") if execution_report_path.is_file() else {}
    quality = _read_json(quality_report_path, "quality_report_read_failed") if quality_report_path.is_file() else {}
    try:
        quality_score = compute_quality_score(quality, execution)
        blocked_reason = None
    except CdfQualityExplorationError as exc:
        quality_score = None
        blocked_reason = exc.code
    accepted = bool(execution.get("accepted")) and bool(quality.get("accepted"))
    mesh_ok = mesh_path is not None and mesh_path.is_file() and mesh_path.stat().st_size > 0
    status = "PASSED" if accepted and mesh_ok and quality_score is not None else "FAILED"
    if status == "PASSED" and (_is_near_fail_quality(quality) or _is_near_fail_score(quality_score)):
        status = "NEAR_FAIL"
    if blocked_reason is not None:
        status = "BLOCKED"
    return {
        "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
        "sample_id": sample_id,
        "evaluation_id": evaluation_id,
        "status": status,
        "error_code": blocked_reason,
        "perturbation": dict(perturbation),
        "manifest_path": manifest_path.as_posix(),
        "execution_report_path": execution_report_path.as_posix(),
        "quality_report_path": quality_report_path.as_posix(),
        "mesh_path": mesh_path.as_posix() if mesh_path is not None else None,
        "quality_score": quality_score,
        "quality_metrics_available": quality_score is not None,
        "accepted": accepted,
        "mesh_nonempty": mesh_ok,
    }


def _copy_cad_input(source_sample: Path, evaluation_dir: Path) -> None:
    target_cad = evaluation_dir / "cad"
    target_cad.mkdir(parents=True, exist_ok=True)
    source = source_sample / "cad" / "input.step"
    if not source.is_file():
        raise CdfQualityExplorationError("missing_input_step", "accepted sample is missing cad/input.step", source_sample)
    shutil.copyfile(source, target_cad / "input.step")


def run_quality_exploration(
    *,
    dataset_root: str | Path,
    output_dir: str | Path,
    ansa_executable: str | Path,
    perturbations_per_sample: int = 3,
    limit: int | None = None,
    timeout_sec_per_sample: int = 180,
    execute: bool = True,
) -> QualityExplorationResult:
    started = time.monotonic()
    root = Path(dataset_root)
    out = Path(output_dir)
    sample_dirs = _accepted_sample_dirs(root)
    if limit is not None:
        sample_dirs = sample_dirs[: max(0, int(limit))]
    if not sample_dirs:
        raise CdfQualityExplorationError("empty_dataset", "quality exploration requires accepted samples", root)
    config = AnsaRunnerConfig(
        ansa_executable=str(ansa_executable),
        timeout_sec_per_sample=timeout_sec_per_sample,
        save_ansa_database=False,
    )
    records: list[dict[str, Any]] = []
    for sample_dir in sample_dirs:
        sample_id = sample_dir.name
        baseline_manifest = _read_json(sample_dir / "labels" / "amg_manifest.json", "manifest_read_failed")
        records.append(
            _record_from_reports(
                sample_id=sample_id,
                evaluation_id="baseline",
                perturbation={"kind": "baseline"},
                manifest_path=sample_dir / "labels" / "amg_manifest.json",
                execution_report_path=sample_dir / "reports" / "ansa_execution_report.json",
                quality_report_path=sample_dir / "reports" / "ansa_quality_report.json",
                mesh_path=sample_dir / "meshes" / "ansa_oracle_mesh.bdf",
            )
        )
        for index, perturbation in enumerate(_perturbation_specs(baseline_manifest, perturbations_per_sample), start=1):
            evaluation_id = f"perturb_{index:03d}"
            evaluation_dir = out / "samples" / sample_id / evaluation_id
            _copy_cad_input(sample_dir, evaluation_dir)
            candidate_manifest = perturb_manifest(baseline_manifest, perturbation)
            manifest_path = evaluation_dir / "labels" / "amg_manifest.json"
            _write_json(manifest_path, candidate_manifest)
            result = run_ansa_oracle(
                AnsaRunRequest(
                    sample_dir=evaluation_dir,
                    config=config,
                    manifest_path=manifest_path,
                    execution_report_path=evaluation_dir / "reports" / "ansa_execution_report.json",
                    quality_report_path=evaluation_dir / "reports" / "ansa_quality_report.json",
                ),
                execute=execute,
            )
            if result.status not in {"COMPLETED", "FAILED"}:
                records.append(
                    {
                        "schema": "CDF_QUALITY_EXPLORATION_RECORD_V1",
                        "sample_id": sample_id,
                        "evaluation_id": evaluation_id,
                        "status": "BLOCKED",
                        "error_code": result.error_code or result.status.lower(),
                        "perturbation": dict(perturbation),
                        "manifest_path": manifest_path.as_posix(),
                        "execution_report_path": (evaluation_dir / "reports" / "ansa_execution_report.json").as_posix(),
                        "quality_report_path": (evaluation_dir / "reports" / "ansa_quality_report.json").as_posix(),
                        "mesh_path": (evaluation_dir / "meshes" / "ansa_oracle_mesh.bdf").as_posix(),
                        "quality_score": None,
                        "quality_metrics_available": False,
                        "accepted": False,
                        "mesh_nonempty": False,
                    }
                )
                continue
            records.append(
                _record_from_reports(
                    sample_id=sample_id,
                    evaluation_id=evaluation_id,
                    perturbation=perturbation,
                    manifest_path=manifest_path,
                    execution_report_path=evaluation_dir / "reports" / "ansa_execution_report.json",
                    quality_report_path=evaluation_dir / "reports" / "ansa_quality_report.json",
                    mesh_path=evaluation_dir / "meshes" / "ansa_oracle_mesh.bdf",
                )
            )
    status_counts = Counter(record["status"] for record in records)
    scores = [float(record["quality_score"]) for record in records if isinstance(record.get("quality_score"), (int, float))]
    variance = statistics.pvariance(scores) if len(scores) >= 2 else 0.0
    summary = {
        "schema": "CDF_QUALITY_EXPLORATION_SUMMARY_V1",
        "status": "SUCCESS" if status_counts.get("BLOCKED", 0) == 0 else "BLOCKED",
        "dataset_root": root.as_posix(),
        "output_dir": out.as_posix(),
        "baseline_count": len(sample_dirs),
        "evaluated_count": max(0, len(records) - len(sample_dirs)),
        "passed_count": status_counts.get("PASSED", 0),
        "near_fail_count": status_counts.get("NEAR_FAIL", 0),
        "failed_count": status_counts.get("FAILED", 0),
        "blocked_count": status_counts.get("BLOCKED", 0),
        "quality_score_variance": variance,
        "runtime_sec": round(max(0.0, time.monotonic() - started), 6),
        "records": records,
    }
    summary_path = out / "quality_exploration_summary.json"
    _write_json(summary_path, summary)
    return QualityExplorationResult(
        status=str(summary["status"]),
        output_dir=out.as_posix(),
        summary_path=summary_path.as_posix(),
        baseline_count=len(sample_dirs),
        evaluated_count=int(summary["evaluated_count"]),
        passed_count=int(summary["passed_count"]),
        near_fail_count=int(summary["near_fail_count"]),
        failed_count=int(summary["failed_count"]),
        blocked_count=int(summary["blocked_count"]),
        quality_score_variance=variance,
    )
