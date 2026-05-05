"""Recommend quality-ranked AMG manifests and validate them with real ANSA."""

from __future__ import annotations

import argparse
import base64
import json
import statistics
import subprocess
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from jsonschema import Draft202012Validator

from ai_mesh_generator.amg.dataset import AmgDatasetSample, load_amg_dataset_sample, load_dataset_index
from ai_mesh_generator.amg.inference.real_mesh import DEFAULT_ANSA_EXECUTABLE, DEFAULT_BATCH_SCRIPT, _build_ansa_command, _mesh_is_real
from ai_mesh_generator.amg.quality_features import build_quality_feature_vector, control_vector
from ai_mesh_generator.amg.training.quality import QualityControlRanker

MANIFEST_SCHEMA = "AMG_MANIFEST_SM_V1"
SUMMARY_SCHEMA = "AMG_QUALITY_RECOMMENDATION_SUMMARY_V1"
SAMPLE_SCHEMA = "AMG_QUALITY_RECOMMENDATION_SAMPLE_REPORT_V1"
DEFAULT_SEVERE_REGRESSION_THRESHOLD = -1.0
DEFAULT_MIN_PREDICTED_IMPROVEMENT: float | None = None


class AmgQualityRecommendationError(ValueError):
    """Raised when quality recommendation cannot proceed safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class QualityRecommendationConfig:
    dataset_root: Path
    quality_exploration_root: Path
    training_root: Path
    output_dir: Path
    ansa_executable: Path = Path(DEFAULT_ANSA_EXECUTABLE)
    split: str = "test"
    limit: int | None = None
    sample_ids: tuple[str, ...] = ()
    batch_script: Path = DEFAULT_BATCH_SCRIPT
    timeout_sec_per_sample: int = 180
    risk_aware: bool = False
    min_predicted_improvement: float | None = DEFAULT_MIN_PREDICTED_IMPROVEMENT
    max_control_distance: float | None = None
    severe_regression_threshold: float = DEFAULT_SEVERE_REGRESSION_THRESHOLD
    compare_baseline: bool = False


@dataclass(frozen=True)
class CandidateManifestScore:
    sample_id: str
    evaluation_id: str
    manifest_path: str
    predicted_score: float
    rank: int
    is_baseline: bool
    manifest: dict[str, Any]
    predicted_margin_vs_baseline: float | None = None
    control_distance_from_baseline: float | None = None


@dataclass(frozen=True)
class QualityRecommendationSampleResult:
    sample_id: str
    status: str
    baseline_score: float | None
    recommended_score: float | None
    improvement_delta: float | None
    selected_evaluation_id: str | None
    selected_manifest_path: str | None
    report_path: str
    selection_reason: str | None = None
    risk_rejected_candidate_count: int = 0
    error_code: str | None = None


@dataclass(frozen=True)
class QualityRecommendationResult:
    status: str
    output_dir: str
    summary_path: str
    attempted_count: int
    valid_pair_count: int
    improved_count: int
    improvement_rate: float
    median_improvement_delta: float | None
    mean_improvement_delta: float | None
    worst_improvement_delta: float | None
    lower_tail_delta_p10: float | None
    lower_tail_delta_p25: float | None
    severe_regression_count: int
    selected_non_baseline_count: int
    selected_baseline_count: int
    risk_rejected_candidate_count: int
    failure_reason_counts: dict[str, int]
    sample_results: tuple[QualityRecommendationSampleResult, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgQualityRecommendationError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgQualityRecommendationError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgQualityRecommendationError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(dict(manifest), allow_nan=False))
    schema = _read_json(_repo_root() / "contracts" / f"{MANIFEST_SCHEMA}.schema.json", "schema_read_failed")
    errors = sorted(Draft202012Validator(schema).iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise AmgQualityRecommendationError("manifest_schema_invalid", f"{location}: {first.message}")
    return normalized


def _accepted_sample_paths(dataset_root: Path) -> dict[str, Path]:
    index = load_dataset_index(dataset_root)
    records: dict[str, Path] = {}
    for item in index["accepted_samples"]:
        if isinstance(item, str):
            sample_id = item
            sample_dir = dataset_root / "samples" / sample_id
        elif isinstance(item, Mapping):
            sample_id = item.get("sample_id")
            if not isinstance(sample_id, str):
                raise AmgQualityRecommendationError("dataset_index_schema_invalid", "accepted records require sample_id", dataset_root)
            sample_dir = Path(str(item.get("sample_dir", f"samples/{sample_id}")))
            sample_dir = sample_dir if sample_dir.is_absolute() else dataset_root / sample_dir
        else:
            raise AmgQualityRecommendationError("dataset_index_schema_invalid", "accepted records must be strings or objects", dataset_root)
        records[sample_id] = sample_dir
    return records


def _split_ids(dataset_root: Path, split: str) -> list[str]:
    path = dataset_root / "splits" / f"{split}.txt"
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_recommendation_samples(
    dataset_root: str | Path,
    *,
    split: str = "test",
    limit: int | None = None,
    sample_ids: Sequence[str] | None = None,
) -> list[AmgDatasetSample]:
    """Select recommendation samples from an explicit list or dataset split."""

    root = Path(dataset_root)
    accepted = _accepted_sample_paths(root)
    selected = list(sample_ids or ())
    if not selected:
        selected = _split_ids(root, split)
    if limit is not None:
        if limit <= 0:
            raise AmgQualityRecommendationError("invalid_limit", "limit must be positive")
        selected = selected[:limit]
    if not selected:
        raise AmgQualityRecommendationError("empty_recommendation_selection", f"split has no samples: {split}", root)
    missing = [sample_id for sample_id in selected if sample_id not in accepted]
    if missing:
        raise AmgQualityRecommendationError("sample_not_accepted", f"sample is not accepted: {missing[0]}", root)
    return [load_amg_dataset_sample(accepted[sample_id]) for sample_id in selected]


def _quality_summary_path(root: Path) -> Path:
    if root.is_file():
        return root
    path = root / "quality_exploration_summary.json"
    if not path.is_file():
        raise AmgQualityRecommendationError("missing_quality_exploration_summary", "quality exploration summary not found", root)
    return path


def _resolve_manifest_path(path_text: str, quality_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute() or path.exists():
        return path
    candidate = quality_root / path
    return candidate if candidate.exists() else path


def load_candidate_manifests(
    *,
    quality_exploration_root: str | Path,
    sample_id: str,
) -> list[dict[str, Any]]:
    """Load candidate manifests without consulting quality labels or statuses."""

    quality_root = Path(quality_exploration_root)
    summary = _read_json(_quality_summary_path(quality_root), "quality_summary_read_failed")
    records = summary.get("records", [])
    if not isinstance(records, list):
        raise AmgQualityRecommendationError("malformed_quality_summary", "records must be a list", quality_root)
    candidates: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping) or record.get("sample_id") != sample_id:
            continue
        evaluation_id = record.get("evaluation_id")
        manifest_path_text = record.get("manifest_path")
        if not isinstance(evaluation_id, str) or not isinstance(manifest_path_text, str):
            continue
        manifest_path = _resolve_manifest_path(manifest_path_text, quality_root)
        manifest = _validate_manifest(_read_json(manifest_path, "manifest_read_failed"))
        candidates.append(
            {
                "sample_id": sample_id,
                "evaluation_id": evaluation_id,
                "manifest_path": manifest_path.as_posix(),
                "manifest": manifest,
                "is_baseline": evaluation_id == "baseline",
            }
        )
    if not candidates:
        raise AmgQualityRecommendationError("missing_candidate_manifests", f"no candidate manifests found for {sample_id}", quality_root)
    candidates.sort(key=lambda item: (0 if item["is_baseline"] else 1, str(item["evaluation_id"]), str(item["manifest_path"])))
    return candidates


def _checkpoint_path(training_root: Path) -> Path:
    if training_root.is_file():
        return training_root
    path = training_root / "quality_ranker_checkpoint.pt"
    if not path.is_file():
        raise AmgQualityRecommendationError("missing_quality_ranker_checkpoint", "quality ranker checkpoint not found", training_root)
    return path


def load_quality_ranker(training_root: str | Path) -> QualityControlRanker:
    """Load the T-708 quality ranker checkpoint."""

    checkpoint_path = _checkpoint_path(Path(training_root))
    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
    except OSError as exc:
        raise AmgQualityRecommendationError("checkpoint_read_failed", f"could not read {checkpoint_path}", checkpoint_path) from exc
    if not isinstance(checkpoint, Mapping):
        raise AmgQualityRecommendationError("malformed_checkpoint", "checkpoint must contain a mapping payload", checkpoint_path)
    input_dim = checkpoint.get("input_dim")
    hidden_dim = checkpoint.get("hidden_dim", 32)
    if not isinstance(input_dim, int) or input_dim <= 0:
        raise AmgQualityRecommendationError("malformed_checkpoint", "checkpoint requires positive input_dim", checkpoint_path)
    if not isinstance(hidden_dim, int) or hidden_dim <= 0:
        raise AmgQualityRecommendationError("malformed_checkpoint", "checkpoint requires positive hidden_dim", checkpoint_path)
    model = QualityControlRanker(input_dim=input_dim, hidden_dim=hidden_dim)
    try:
        model.load_state_dict(checkpoint["model_state"])
    except (KeyError, RuntimeError) as exc:
        raise AmgQualityRecommendationError("malformed_checkpoint", "checkpoint model_state is invalid", checkpoint_path) from exc
    model.eval()
    return model


def score_candidate_manifests(
    sample: AmgDatasetSample,
    candidates: Sequence[Mapping[str, Any]],
    ranker: QualityControlRanker,
) -> list[CandidateManifestScore]:
    """Predict lower-is-better quality scores for candidate manifests."""

    if not candidates:
        raise AmgQualityRecommendationError("missing_candidate_manifests", f"no candidates for {sample.sample_id}", sample.sample_dir)
    rows = np.stack([build_quality_feature_vector(sample, candidate["manifest"]) for candidate in candidates])
    if rows.shape[1] != ranker.input_dim:
        raise AmgQualityRecommendationError("feature_dimension_mismatch", "candidate feature vector does not match ranker input_dim", sample.sample_dir)
    with torch.no_grad():
        predictions = ranker(torch.as_tensor(rows, dtype=torch.float32)).detach().cpu().tolist()
    baseline_index = next((index for index, candidate in enumerate(candidates) if bool(candidate.get("is_baseline"))), None)
    baseline_prediction = float(predictions[baseline_index]) if baseline_index is not None else None
    baseline_controls = control_vector(candidates[baseline_index]["manifest"]) if baseline_index is not None else None
    ordered = sorted(
        [
            CandidateManifestScore(
                sample_id=sample.sample_id,
                evaluation_id=str(candidate["evaluation_id"]),
                manifest_path=str(candidate["manifest_path"]),
                predicted_score=float(prediction),
                rank=0,
                is_baseline=bool(candidate.get("is_baseline")),
                manifest=dict(candidate["manifest"]),
                predicted_margin_vs_baseline=(None if baseline_prediction is None else baseline_prediction - float(prediction)),
                control_distance_from_baseline=(
                    None
                    if baseline_controls is None
                    else float(np.linalg.norm(control_vector(candidate["manifest"]) - baseline_controls))
                ),
            )
            for candidate, prediction in zip(candidates, predictions, strict=True)
        ],
        key=lambda item: (item.predicted_score, item.evaluation_id, item.manifest_path),
    )
    return [
        CandidateManifestScore(
            sample_id=item.sample_id,
            evaluation_id=item.evaluation_id,
            manifest_path=item.manifest_path,
            predicted_score=item.predicted_score,
            rank=index,
            is_baseline=item.is_baseline,
            manifest=item.manifest,
            predicted_margin_vs_baseline=item.predicted_margin_vs_baseline,
            control_distance_from_baseline=item.control_distance_from_baseline,
        )
        for index, item in enumerate(ordered, start=1)
    ]


def _select_recommendation_candidate(
    scored: Sequence[CandidateManifestScore],
    *,
    risk_aware: bool,
    min_predicted_improvement: float | None,
    max_control_distance: float | None,
) -> tuple[CandidateManifestScore, str, list[dict[str, Any]]]:
    baseline = next((item for item in scored if item.is_baseline), None)
    if baseline is None:
        raise AmgQualityRecommendationError("missing_baseline_candidate", "candidate pool requires a baseline manifest")
    if not risk_aware:
        for item in scored:
            if not item.is_baseline:
                return item, "RANKER_ARGMIN_NON_BASELINE", []
        raise AmgQualityRecommendationError(
            "no_non_baseline_candidates",
            "candidate pool contains no non-baseline AI manifest candidates",
        )
    rejected: list[dict[str, Any]] = []
    for item in scored:
        if item.is_baseline:
            continue
        reasons: list[str] = []
        margin = float(item.predicted_margin_vs_baseline or 0.0)
        if min_predicted_improvement is not None and margin < min_predicted_improvement:
            reasons.append("predicted_margin_below_threshold")
        distance = item.control_distance_from_baseline
        if max_control_distance is not None and distance is not None and distance > max_control_distance:
            reasons.append("control_distance_above_threshold")
        if reasons:
            rejected.append(
                {
                    "evaluation_id": item.evaluation_id,
                    "predicted_score": item.predicted_score,
                    "predicted_margin_vs_baseline": item.predicted_margin_vs_baseline,
                    "control_distance_from_baseline": item.control_distance_from_baseline,
                    "reasons": reasons,
                }
            )
            continue
        return item, "RISK_AWARE_RANKER", rejected
    raise AmgQualityRecommendationError(
        "no_ai_candidate_passed_risk_gate",
        f"no non-baseline AI candidate met risk thresholds; rejected={len(rejected)}",
    )


def _copy_input_step(sample: AmgDatasetSample, run_dir: Path) -> None:
    source = sample.sample_dir / "cad" / "input.step"
    if not source.is_file():
        raise AmgQualityRecommendationError("missing_input_step", "sample requires cad/input.step", source)
    target = run_dir / "cad" / "input.step"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def _read_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_json(path, "report_read_failed")


def _has_continuous_quality(quality: Mapping[str, Any]) -> bool:
    return any(isinstance(quality.get(key), (int, float)) for key in (
        "average_shell_length_mm",
        "side_length_spread_ratio",
        "aspect_ratio_proxy_max",
        "triangles_percent",
    ))


def _quality_score(quality_report: Mapping[str, Any], execution_report: Mapping[str, Any]) -> float:
    quality = quality_report.get("quality", {})
    if not isinstance(quality, Mapping):
        raise AmgQualityRecommendationError("malformed_quality_report", "quality must be an object")
    hard_failed = int(quality.get("num_hard_failed_elements", 1))
    if not _has_continuous_quality(quality):
        if hard_failed > 0:
            return 1000.0 * hard_failed
        raise AmgQualityRecommendationError("quality_metric_unavailable", "continuous metrics are required for accepted meshes")
    violating = float(quality.get("violating_shell_elements_total", 0.0) or 0.0)
    spread = float(quality.get("side_length_spread_ratio", 0.0) or 0.0)
    aspect_proxy = max(1.0, float(quality.get("aspect_ratio_proxy_max", 1.0) or 1.0))
    triangles_percent = float(quality.get("triangles_percent", 0.0) or 0.0)
    shell_elements = float(quality.get("num_shell_elements", quality_report.get("mesh_stats", {}).get("num_shell_elements", 0.0)) or 0.0)
    runtime = float(execution_report.get("runtime_sec", 0.0) or 0.0)
    boundary_error = 0.0
    feature_checks = quality_report.get("feature_checks", [])
    if isinstance(feature_checks, list):
        for check in feature_checks:
            if isinstance(check, Mapping) and isinstance(check.get("boundary_size_error"), (int, float)):
                boundary_error = max(boundary_error, abs(float(check["boundary_size_error"])))
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


def _decode_command_payload(command: Sequence[str]) -> dict[str, Any]:
    for token in command:
        if token.startswith("-process_string:"):
            encoded = token.split(":", 1)[1]
            encoded += "=" * (-len(encoded) % 4)
            return json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
    return {}


def _run_ansa_manifest(
    *,
    sample: AmgDatasetSample,
    run_dir: Path,
    manifest: Mapping[str, Any],
    executable: Path,
    batch_script: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    _copy_input_step(sample, run_dir)
    manifest_path = run_dir / "labels" / "amg_manifest.json"
    execution_path = run_dir / "reports" / "ansa_execution_report.json"
    quality_path = run_dir / "reports" / "ansa_quality_report.json"
    mesh_path = run_dir / "meshes" / "ansa_oracle_mesh.bdf"
    _write_json(manifest_path, _validate_manifest(manifest))
    command = _build_ansa_command(
        executable=executable,
        batch_script=batch_script,
        sample_dir=run_dir,
        manifest_path=manifest_path,
        execution_report_path=execution_path,
        quality_report_path=quality_path,
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_sec, check=False)
        returncode: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = None
        stdout = exc.stdout if isinstance(exc.stdout, str) else None
        stderr = exc.stderr if isinstance(exc.stderr, str) else None
    execution = _read_report(execution_path)
    quality = _read_report(quality_path)
    status = "VALID_EVIDENCE"
    reason: str | None = None
    score: float | None = None
    if execution is None:
        status, reason = "INVALID_EVIDENCE", "missing_execution_report"
    elif quality is None:
        status, reason = "INVALID_EVIDENCE", "missing_quality_report"
    elif isinstance(execution.get("outputs"), Mapping) and "controlled_failure_reason" in execution["outputs"]:
        status, reason = "INVALID_EVIDENCE", "controlled_failure_report"
    elif execution.get("ansa_version") in {"unavailable", "mock-ansa"}:
        status, reason = "INVALID_EVIDENCE", "non_real_ansa_report"
    elif not _mesh_is_real(mesh_path):
        status, reason = "INVALID_EVIDENCE", "missing_or_placeholder_mesh"
    else:
        try:
            score = _quality_score(quality, execution)
        except AmgQualityRecommendationError as exc:
            status, reason = "INVALID_EVIDENCE", exc.code
    return {
        "status": status,
        "reason": reason,
        "quality_score": score,
        "manifest_path": manifest_path.as_posix(),
        "execution_report_path": execution_path.as_posix(),
        "quality_report_path": quality_path.as_posix(),
        "mesh_path": mesh_path.as_posix(),
        "command_payload": _decode_command_payload(command),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "runtime_sec": round(max(0.0, time.monotonic() - started), 6),
    }


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return _repo_root() / path


def run_quality_recommendation(config: QualityRecommendationConfig) -> QualityRecommendationResult:
    """Score candidate manifests, run baseline/recommended manifests in real ANSA, and summarize improvement."""

    executable = _resolve_path(config.ansa_executable)
    batch_script = _resolve_path(config.batch_script)
    if not executable.is_file():
        raise AmgQualityRecommendationError("ansa_executable_not_found", f"ANSA executable not found: {executable}", executable)
    if not batch_script.is_file():
        raise AmgQualityRecommendationError("batch_script_not_found", f"batch script not found: {batch_script}", batch_script)
    samples = select_recommendation_samples(
        config.dataset_root,
        split=config.split,
        limit=config.limit,
        sample_ids=config.sample_ids,
    )
    ranker = load_quality_ranker(config.training_root)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[QualityRecommendationSampleResult] = []
    failure_counts: Counter[str] = Counter()
    deltas: list[float] = []
    selected_non_baseline = 0
    selected_baseline = 0
    risk_rejected_total = 0
    improved = 0
    valid_pairs = 0
    for sample in samples:
        sample_dir = config.output_dir / "samples" / sample.sample_id
        report_path = sample_dir / "recommendation_report.json"
        try:
            candidates = load_candidate_manifests(quality_exploration_root=config.quality_exploration_root, sample_id=sample.sample_id)
            scored = score_candidate_manifests(sample, candidates, ranker)
            baseline = next((item for item in scored if item.is_baseline), None)
            if baseline is None:
                raise AmgQualityRecommendationError("missing_baseline_candidate", "candidate pool requires a baseline manifest", sample.sample_dir)
            recommended, selection_reason, risk_rejections = _select_recommendation_candidate(
                scored,
                risk_aware=config.risk_aware,
                min_predicted_improvement=config.min_predicted_improvement,
                max_control_distance=config.max_control_distance,
            )
            risk_rejected_total += len(risk_rejections)
            if not recommended.is_baseline:
                selected_non_baseline += 1
            else:
                selected_baseline += 1
            baseline_run: dict[str, Any] | None = None
            baseline_score: float | None = None
            if config.compare_baseline:
                baseline_run = _run_ansa_manifest(
                    sample=sample,
                    run_dir=sample_dir / "baseline",
                    manifest=baseline.manifest,
                    executable=executable,
                    batch_script=batch_script,
                    timeout_sec=config.timeout_sec_per_sample,
                )
            recommended_run = _run_ansa_manifest(
                sample=sample,
                run_dir=sample_dir / "recommended",
                manifest=recommended.manifest,
                executable=executable,
                batch_script=batch_script,
                timeout_sec=config.timeout_sec_per_sample,
            )
            if baseline_run is not None and baseline_run["status"] != "VALID_EVIDENCE":
                raise AmgQualityRecommendationError(str(baseline_run["reason"]), "baseline ANSA evidence is invalid", sample.sample_dir)
            if recommended_run["status"] != "VALID_EVIDENCE":
                raise AmgQualityRecommendationError(str(recommended_run["reason"]), "recommended ANSA evidence is invalid", sample.sample_dir)
            recommended_score = float(recommended_run["quality_score"])
            delta: float | None = None
            if baseline_run is not None:
                baseline_score = float(baseline_run["quality_score"])
                delta = baseline_score - recommended_score
                deltas.append(delta)
                if delta > 0.01:
                    improved += 1
            valid_pairs += 1
            status = "VALID_MESH" if delta is None else ("IMPROVED" if delta > 0.01 else "NOT_IMPROVED")
            report = {
                "schema": SAMPLE_SCHEMA,
                "sample_id": sample.sample_id,
                "status": status,
                "candidate_scores": [item.__dict__ | {"manifest": None} for item in scored],
                "selected_evaluation_id": recommended.evaluation_id,
                "selected_manifest_path": recommended.manifest_path,
                "selection_reason": selection_reason,
                "risk_rejected_candidates": risk_rejections,
                "baseline_predicted_score": baseline.predicted_score,
                "recommended_predicted_score": recommended.predicted_score,
                "recommended_predicted_margin_vs_baseline": recommended.predicted_margin_vs_baseline,
                "recommended_control_distance_from_baseline": recommended.control_distance_from_baseline,
                "baseline_run": baseline_run,
                "recommended_run": recommended_run,
                "baseline_quality_score": baseline_score,
                "recommended_quality_score": recommended_score,
                "improvement_delta": delta,
            }
            _write_json(report_path, report)
            results.append(
                QualityRecommendationSampleResult(
                    sample_id=sample.sample_id,
                    status=status,
                    baseline_score=baseline_score,
                    recommended_score=recommended_score,
                    improvement_delta=delta,
                    selected_evaluation_id=recommended.evaluation_id,
                    selected_manifest_path=recommended.manifest_path,
                    report_path=report_path.as_posix(),
                    selection_reason=selection_reason,
                    risk_rejected_candidate_count=len(risk_rejections),
                )
            )
        except AmgQualityRecommendationError as exc:
            failure_counts[exc.code] += 1
            report = {
                "schema": SAMPLE_SCHEMA,
                "sample_id": sample.sample_id,
                "status": "FAILED",
                "error_code": exc.code,
                "message": str(exc),
            }
            _write_json(report_path, report)
            results.append(
                QualityRecommendationSampleResult(
                    sample_id=sample.sample_id,
                    status="FAILED",
                    baseline_score=None,
                    recommended_score=None,
                    improvement_delta=None,
                    selected_evaluation_id=None,
                    selected_manifest_path=None,
                    report_path=report_path.as_posix(),
                    selection_reason=None,
                    risk_rejected_candidate_count=0,
                    error_code=exc.code,
                )
            )
    attempted = len(results)
    improvement_rate = improved / valid_pairs if valid_pairs else 0.0
    median_delta = statistics.median(deltas) if deltas else None
    mean_delta = statistics.mean(deltas) if deltas else None
    worst_delta = min(deltas) if deltas else None
    lower_tail_p10 = _quantile(deltas, 0.10)
    lower_tail_p25 = _quantile(deltas, 0.25)
    severe_regression_count = sum(1 for delta in deltas if delta < config.severe_regression_threshold)
    status = "SUCCESS" if valid_pairs == attempted and attempted > 0 else "PARTIAL_FAILED"
    summary = {
        "schema": SUMMARY_SCHEMA,
        "status": status,
        "dataset_root": Path(config.dataset_root).as_posix(),
        "quality_exploration_root": Path(config.quality_exploration_root).as_posix(),
        "training_root": Path(config.training_root).as_posix(),
        "output_dir": config.output_dir.as_posix(),
        "split": config.split,
        "risk_aware": config.risk_aware,
        "min_predicted_improvement": config.min_predicted_improvement,
        "max_control_distance": config.max_control_distance,
        "compare_baseline": config.compare_baseline,
        "severe_regression_threshold": config.severe_regression_threshold,
        "attempted_count": attempted,
        "valid_pair_count": valid_pairs,
        "improved_count": improved,
        "improvement_rate": improvement_rate,
        "mean_improvement_delta": mean_delta,
        "median_improvement_delta": median_delta,
        "worst_improvement_delta": worst_delta,
        "lower_tail_delta_p10": lower_tail_p10,
        "lower_tail_delta_p25": lower_tail_p25,
        "severe_regression_count": severe_regression_count,
        "selected_non_baseline_count": selected_non_baseline,
        "selected_baseline_count": selected_baseline,
        "risk_rejected_candidate_count": risk_rejected_total,
        "failure_reason_counts": dict(sorted(failure_counts.items())),
        "sample_results": [result.__dict__ for result in results],
    }
    summary_path = config.output_dir / "recommendation_summary.json"
    _write_json(summary_path, summary)
    return QualityRecommendationResult(
        status=status,
        output_dir=config.output_dir.as_posix(),
        summary_path=summary_path.as_posix(),
        attempted_count=attempted,
        valid_pair_count=valid_pairs,
        improved_count=improved,
        improvement_rate=improvement_rate,
        median_improvement_delta=median_delta,
        mean_improvement_delta=mean_delta,
        worst_improvement_delta=worst_delta,
        lower_tail_delta_p10=lower_tail_p10,
        lower_tail_delta_p25=lower_tail_p25,
        severe_regression_count=severe_regression_count,
        selected_non_baseline_count=selected_non_baseline,
        selected_baseline_count=selected_baseline,
        risk_rejected_candidate_count=risk_rejected_total,
        failure_reason_counts=dict(sorted(failure_counts.items())),
        sample_results=tuple(results),
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recommend quality-ranked AMG manifests and validate with real ANSA.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--quality-exploration", required=True)
    parser.add_argument("--training", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--ansa-executable", default=DEFAULT_ANSA_EXECUTABLE)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--risk-aware", action="store_true")
    parser.add_argument("--min-predicted-improvement", type=float, default=DEFAULT_MIN_PREDICTED_IMPROVEMENT)
    parser.add_argument("--max-control-distance", type=float, default=None)
    parser.add_argument("--severe-regression-threshold", type=float, default=DEFAULT_SEVERE_REGRESSION_THRESHOLD)
    parser.add_argument("--compare-baseline", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_quality_recommendation(
            QualityRecommendationConfig(
                dataset_root=Path(args.dataset),
                quality_exploration_root=Path(args.quality_exploration),
                training_root=Path(args.training),
                output_dir=Path(args.out),
                ansa_executable=Path(args.ansa_executable),
                split=args.split,
                limit=args.limit,
                sample_ids=tuple(args.sample_id),
                timeout_sec_per_sample=args.timeout_sec,
                risk_aware=bool(args.risk_aware),
                min_predicted_improvement=(
                    None if args.min_predicted_improvement is None else float(args.min_predicted_improvement)
                ),
                max_control_distance=args.max_control_distance,
                severe_regression_threshold=float(args.severe_regression_threshold),
                compare_baseline=bool(args.compare_baseline),
            )
        )
    except AmgQualityRecommendationError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": result.status,
                "attempted_count": result.attempted_count,
                "valid_pair_count": result.valid_pair_count,
                "improvement_rate": result.improvement_rate,
                "median_improvement_delta": result.median_improvement_delta,
                "worst_improvement_delta": result.worst_improvement_delta,
                "severe_regression_count": result.severe_regression_count,
                "summary_path": result.summary_path,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.status == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
