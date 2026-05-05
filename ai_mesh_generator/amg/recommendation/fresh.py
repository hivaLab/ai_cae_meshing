"""Generate fresh quality-control candidates and evaluate them with real ANSA."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ai_mesh_generator.amg.dataset import AmgDatasetSample
from ai_mesh_generator.amg.quality_features import build_quality_feature_vector, control_vector
from ai_mesh_generator.amg.recommendation.quality import (
    DEFAULT_ANSA_EXECUTABLE,
    DEFAULT_BATCH_SCRIPT,
    AmgQualityRecommendationError,
    load_candidate_manifests,
    load_quality_ranker,
    select_recommendation_samples,
)
from ai_mesh_generator.amg.recommendation.quality import (
    _quality_score,
    _read_json,
    _resolve_path,
    _run_ansa_manifest,
    _validate_manifest,
    _write_json,
)
from ai_mesh_generator.amg.training.quality import QualityControlRanker

FRESH_SUMMARY_SCHEMA = "AMG_FRESH_QUALITY_EXPLORATION_SUMMARY_V1"
FRESH_RECORD_SCHEMA = "AMG_FRESH_QUALITY_EVIDENCE_V1"


class AmgFreshProposalError(ValueError):
    """Raised when fresh quality-control proposal cannot proceed safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class FreshProposalConfig:
    dataset_root: Path
    quality_exploration_root: Path
    training_root: Path
    output_dir: Path
    ansa_executable: Path = Path(DEFAULT_ANSA_EXECUTABLE)
    split: str = "test"
    limit: int | None = None
    sample_ids: tuple[str, ...] = ()
    candidates_per_sample: int = 8
    seed: int = 710
    batch_script: Path = DEFAULT_BATCH_SCRIPT
    timeout_sec_per_sample: int = 180


@dataclass(frozen=True)
class FreshCandidateManifest:
    sample_id: str
    candidate_id: str
    manifest: dict[str, Any]
    candidate_hash: str
    predicted_score: float | None = None
    rank: int | None = None


@dataclass(frozen=True)
class FreshProposalSampleResult:
    sample_id: str
    status: str
    candidate_count: int
    evaluated_count: int
    passed_count: int
    near_fail_count: int
    failed_count: int
    blocked_count: int
    report_path: str
    error_code: str | None = None


@dataclass(frozen=True)
class FreshProposalResult:
    status: str
    output_dir: str
    summary_path: str
    sample_count: int
    baseline_count: int
    generated_count: int
    evaluated_count: int
    passed_count: int
    near_fail_count: int
    failed_count: int
    blocked_count: int
    quality_score_variance: float
    unique_candidate_hash_count: int
    control_value_variance: float
    sample_results: tuple[FreshProposalSampleResult, ...]


def _canonical_manifest(manifest: Mapping[str, Any]) -> str:
    return json.dumps(dict(manifest), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_manifest(manifest).encode("utf-8")).hexdigest()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _global_mesh(manifest: Mapping[str, Any]) -> tuple[float, float, float]:
    mesh = manifest.get("global_mesh", {})
    if not isinstance(mesh, Mapping):
        raise AmgFreshProposalError("malformed_manifest", "global_mesh must be an object")
    h_min = float(mesh.get("h_min_mm", 0.1))
    h_max = float(mesh.get("h_max_mm", max(h_min, 10.0)))
    growth_max = float(mesh.get("growth_rate_max", 1.35))
    if h_min <= 0.0 or h_max < h_min or growth_max <= 1.0:
        raise AmgFreshProposalError("malformed_mesh_policy", "invalid mesh bounds in manifest")
    return h_min, h_max, growth_max


def _mutate_controls(manifest: Mapping[str, Any], *, index: int, seed: int) -> dict[str, Any]:
    mutated = copy.deepcopy(dict(manifest))
    h_min, h_max, growth_max = _global_mesh(mutated)
    h0 = float(mutated.get("global_mesh", {}).get("h0_mm", h_min))
    rng = random.Random((seed + 1009) * (index + 1))
    length_scale = rng.choice((0.42, 0.58, 0.72, 0.88, 1.12, 1.36, 1.62, 1.95))
    growth_target = _clamp(rng.choice((1.03, 1.08, 1.16, 1.24, 1.32, growth_max)), 1.01, growth_max)
    division_scale = rng.choice((0.65, 0.85, 1.15, 1.45, 1.8))
    features = mutated.get("features", [])
    if not isinstance(features, list):
        raise AmgFreshProposalError("malformed_manifest", "features must be a list")
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_type = str(feature.get("type", ""))
        if feature.get("action") == "SUPPRESS" and feature_type in {"HOLE", "SLOT", "CUTOUT"}:
            feature["action"] = "KEEP_REFINED"
            if feature_type == "CUTOUT":
                dims = _signature_dimensions(feature.get("geometry_signature"))
                min_dim = min(dims) if dims else h0
                feature["controls"] = {
                    "edge_target_length_mm": round(_clamp(min(h0, min_dim / max(2.0, 3.0 + (index % 4))), h_min, h_max), 6),
                    "perimeter_growth_rate": round(growth_target, 6),
                }
            elif feature_type == "SLOT":
                feature["controls"] = {
                    "edge_target_length_mm": round(_clamp(h0 * length_scale, h_min, h_max), 6),
                    "end_arc_divisions": int(_clamp(8 + (index % 8), 4, 48)),
                    "straight_edge_divisions": int(_clamp(2 + (index % 12), 1, 96)),
                    "growth_rate": round(growth_target, 6),
                }
            else:
                feature["controls"] = {
                    "edge_target_length_mm": round(_clamp(h0 * length_scale, h_min, h_max), 6),
                    "circumferential_divisions": int(_clamp(8 + 2 * (index % 12), 6, 64)),
                    "radial_growth_rate": round(growth_target, 6),
                }
        controls = feature.get("controls")
        if not isinstance(controls, dict):
            continue
        for key in ("edge_target_length_mm", "bend_target_length_mm", "flange_target_length_mm"):
            if isinstance(controls.get(key), (int, float)):
                controls[key] = round(_clamp(float(controls[key]) * length_scale, h_min, h_max), 6)
        for key in ("growth_rate", "radial_growth_rate", "perimeter_growth_rate"):
            if key in controls:
                controls[key] = round(growth_target, 6)
        for key in ("circumferential_divisions", "end_arc_divisions", "straight_edge_divisions", "min_elements_across_width"):
            if isinstance(controls.get(key), (int, float)):
                controls[key] = int(_clamp(round(float(controls[key]) * division_scale), 1, 96))
        if feature.get("action") == "KEEP_WITH_WASHER":
            controls["washer_rings"] = int(_clamp((index + seed) % 4, 0, 3))
        if feature.get("type") == "BEND":
            controls["bend_rows"] = int(_clamp(1 + ((index + seed) % 6), 1, 6))
        if feature.get("type") in {"SLOT", "CUTOUT"} and "min_elements_across_width" in controls:
            controls["min_elements_across_width"] = int(_clamp(controls["min_elements_across_width"], 1, 32))
    return _validate_manifest(mutated)


def _signature_dimensions(signature: Any) -> tuple[float, ...]:
    value = signature.get("geometry_signature") if isinstance(signature, Mapping) else signature
    if not isinstance(value, str):
        return ()
    pieces = value.split(":")
    numbers: list[float] = []
    for piece in pieces[1:]:
        try:
            numbers.append(float(piece))
        except ValueError:
            continue
    if value.startswith("CUTOUT:") and len(numbers) >= 4:
        return (numbers[-2], numbers[-1])
    if value.startswith("SLOT:") and len(numbers) >= 4:
        return (numbers[-2], numbers[-1])
    if value.startswith("HOLE:") and numbers:
        return (numbers[-1] * 2.0,)
    return tuple(numbers[-2:])


def _evaluated_manifest_hashes(sample_id: str, quality_exploration_root: Path) -> set[str]:
    try:
        candidates = load_candidate_manifests(quality_exploration_root=quality_exploration_root, sample_id=sample_id)
    except AmgQualityRecommendationError:
        return set()
    return {_manifest_hash(candidate["manifest"]) for candidate in candidates}


def generate_fresh_candidate_manifests(
    sample: AmgDatasetSample,
    baseline_manifest: Mapping[str, Any],
    *,
    candidates_per_sample: int = 8,
    seed: int = 710,
    disallowed_hashes: set[str] | None = None,
) -> list[FreshCandidateManifest]:
    """Generate deterministic fresh candidates without reading quality labels."""

    if candidates_per_sample <= 0:
        raise AmgFreshProposalError("invalid_candidate_count", "candidates_per_sample must be positive")
    baseline = _validate_manifest(baseline_manifest)
    blocked_hashes = set(disallowed_hashes or set())
    blocked_hashes.add(_manifest_hash(baseline))
    generated: list[FreshCandidateManifest] = []
    seen = set(blocked_hashes)
    for attempt in range(1, candidates_per_sample * 24 + 1):
        manifest = _mutate_controls(baseline, index=attempt, seed=seed)
        digest = _manifest_hash(manifest)
        if digest in seen:
            continue
        seen.add(digest)
        candidate_id = f"fresh_{len(generated) + 1:03d}"
        generated.append(
            FreshCandidateManifest(
                sample_id=sample.sample_id,
                candidate_id=candidate_id,
                manifest=manifest,
                candidate_hash=digest,
            )
        )
        if len(generated) >= candidates_per_sample:
            break
    if not generated:
        raise AmgFreshProposalError("all_duplicate_candidates", f"no fresh candidates generated for {sample.sample_id}", sample.sample_dir)
    return generated


def score_fresh_candidates(
    sample: AmgDatasetSample,
    candidates: Sequence[FreshCandidateManifest],
    ranker: QualityControlRanker,
) -> list[FreshCandidateManifest]:
    """Score fresh candidates with the trained lower-is-better ranker."""

    if not candidates:
        raise AmgFreshProposalError("missing_fresh_candidates", f"no fresh candidates for {sample.sample_id}", sample.sample_dir)
    rows = np.stack([build_quality_feature_vector(sample, candidate.manifest) for candidate in candidates])
    if rows.shape[1] != ranker.input_dim:
        raise AmgFreshProposalError("feature_dimension_mismatch", "fresh candidate feature vector does not match ranker input_dim", sample.sample_dir)
    with torch.no_grad():
        predictions = ranker(torch.as_tensor(rows, dtype=torch.float32)).detach().cpu().tolist()
    scored = [
        FreshCandidateManifest(
            sample_id=candidate.sample_id,
            candidate_id=candidate.candidate_id,
            manifest=candidate.manifest,
            candidate_hash=candidate.candidate_hash,
            predicted_score=float(prediction),
            rank=None,
        )
        for candidate, prediction in zip(candidates, predictions, strict=True)
    ]
    ordered = sorted(scored, key=lambda item: (float(item.predicted_score), item.candidate_id, item.candidate_hash))
    return [
        FreshCandidateManifest(
            sample_id=item.sample_id,
            candidate_id=item.candidate_id,
            manifest=item.manifest,
            candidate_hash=item.candidate_hash,
            predicted_score=item.predicted_score,
            rank=rank,
        )
        for rank, item in enumerate(ordered, start=1)
    ]


def _read_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return _read_json(path, "report_read_failed")


def _is_near_fail_quality(quality_report: Mapping[str, Any]) -> bool:
    quality = quality_report.get("quality", {})
    if not isinstance(quality, Mapping):
        return False
    if int(quality.get("num_hard_failed_elements", 0) or 0) > 0:
        return False
    return any(float(quality.get(key, 0.0) or 0.0) > 0.0 for key in ("violating_shell_elements_total", "unmeshed_shell_count"))


def _baseline_record(sample: AmgDatasetSample) -> dict[str, Any]:
    execution_path = sample.sample_dir / "reports" / "ansa_execution_report.json"
    quality_path = sample.sample_dir / "reports" / "ansa_quality_report.json"
    mesh_path = sample.sample_dir / "meshes" / "ansa_oracle_mesh.bdf"
    execution = _read_report(execution_path) or {}
    quality = _read_report(quality_path) or {}
    try:
        score = _quality_score(quality, execution)
        status = "NEAR_FAIL" if bool(execution.get("accepted")) and bool(quality.get("accepted")) and _is_near_fail_quality(quality) else "PASSED"
        error_code = None
    except AmgQualityRecommendationError as exc:
        score = None
        status = "BLOCKED"
        error_code = exc.code
    return {
        "schema": FRESH_RECORD_SCHEMA,
        "sample_id": sample.sample_id,
        "evaluation_id": "baseline",
        "candidate_id": "baseline",
        "candidate_hash": _manifest_hash(sample.manifest.manifest),
        "status": status,
        "error_code": error_code,
        "manifest_path": sample.manifest.manifest_path.as_posix(),
        "execution_report_path": execution_path.as_posix(),
        "quality_report_path": quality_path.as_posix(),
        "mesh_path": mesh_path.as_posix(),
        "predicted_score": None,
        "quality_score": score,
        "accepted": bool(execution.get("accepted")) and bool(quality.get("accepted")),
        "mesh_nonempty": mesh_path.is_file() and mesh_path.stat().st_size > 0,
        "is_fresh_candidate": False,
    }


def _record_from_run(
    *,
    sample_id: str,
    candidate: FreshCandidateManifest,
    manifest_path: Path,
    run: Mapping[str, Any],
) -> dict[str, Any]:
    execution_path = Path(str(run["execution_report_path"]))
    quality_path = Path(str(run["quality_report_path"]))
    mesh_path = Path(str(run["mesh_path"]))
    execution = _read_report(execution_path) or {}
    quality = _read_report(quality_path) or {}
    if run.get("status") != "VALID_EVIDENCE":
        status = "BLOCKED"
        error_code = str(run.get("reason") or "invalid_evidence")
        quality_score = None
        accepted = False
    else:
        quality_score = float(run["quality_score"])
        hard_failed = int(quality.get("quality", {}).get("num_hard_failed_elements", 1)) if isinstance(quality.get("quality", {}), Mapping) else 1
        accepted = bool(execution.get("accepted")) and bool(quality.get("accepted")) and hard_failed == 0
        if accepted and _is_near_fail_quality(quality):
            status = "NEAR_FAIL"
        elif accepted:
            status = "PASSED"
        else:
            status = "FAILED"
        error_code = None
    return {
        "schema": FRESH_RECORD_SCHEMA,
        "sample_id": sample_id,
        "evaluation_id": candidate.candidate_id,
        "candidate_id": candidate.candidate_id,
        "candidate_hash": candidate.candidate_hash,
        "status": status,
        "error_code": error_code,
        "manifest_path": manifest_path.as_posix(),
        "execution_report_path": execution_path.as_posix(),
        "quality_report_path": quality_path.as_posix(),
        "mesh_path": mesh_path.as_posix(),
        "predicted_score": candidate.predicted_score,
        "prediction_rank": candidate.rank,
        "quality_score": quality_score,
        "accepted": accepted,
        "mesh_nonempty": mesh_path.is_file() and mesh_path.stat().st_size > 0,
        "is_fresh_candidate": True,
    }


def _control_variance(records: Sequence[Mapping[str, Any]]) -> float:
    values: list[float] = []
    for record in records:
        path = record.get("manifest_path")
        if not isinstance(path, str):
            continue
        manifest_path = Path(path)
        if not manifest_path.is_file():
            continue
        try:
            values.extend(float(value) for value in control_vector(_read_json(manifest_path, "manifest_read_failed")))
        except Exception:
            continue
    return statistics.pvariance(values) if len(values) > 1 else 0.0


def _summarize_sample(sample_id: str, sample_dir: Path, records: Sequence[Mapping[str, Any]]) -> FreshProposalSampleResult:
    counts = Counter(str(record.get("status")) for record in records if record.get("is_fresh_candidate"))
    report_path = sample_dir / "fresh_proposal_report.json"
    report = {
        "schema": "AMG_FRESH_QUALITY_SAMPLE_REPORT_V1",
        "sample_id": sample_id,
        "status": "SUCCESS" if counts.get("BLOCKED", 0) == 0 else "BLOCKED",
        "records": list(records),
    }
    _write_json(report_path, report)
    return FreshProposalSampleResult(
        sample_id=sample_id,
        status=str(report["status"]),
        candidate_count=sum(counts.values()),
        evaluated_count=sum(counts.values()),
        passed_count=counts.get("PASSED", 0),
        near_fail_count=counts.get("NEAR_FAIL", 0),
        failed_count=counts.get("FAILED", 0),
        blocked_count=counts.get("BLOCKED", 0),
        report_path=report_path.as_posix(),
        error_code="blocked_fresh_candidate" if counts.get("BLOCKED", 0) else None,
    )


def run_fresh_quality_proposal(config: FreshProposalConfig) -> FreshProposalResult:
    """Generate fresh candidates, run real ANSA, and write appendable evidence."""

    executable = _resolve_path(config.ansa_executable)
    batch_script = _resolve_path(config.batch_script)
    if not executable.is_file():
        raise AmgFreshProposalError("ansa_executable_not_found", f"ANSA executable not found: {executable}", executable)
    if not batch_script.is_file():
        raise AmgFreshProposalError("batch_script_not_found", f"batch script not found: {batch_script}", batch_script)
    samples = select_recommendation_samples(
        config.dataset_root,
        split=config.split,
        limit=config.limit,
        sample_ids=config.sample_ids,
    )
    ranker = load_quality_ranker(config.training_root)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    all_records: list[dict[str, Any]] = []
    sample_results: list[FreshProposalSampleResult] = []
    for sample_index, sample in enumerate(samples, start=1):
        sample_out = config.output_dir / "samples" / sample.sample_id
        sample_records: list[dict[str, Any]] = [_baseline_record(sample)]
        try:
            disallowed = _evaluated_manifest_hashes(sample.sample_id, config.quality_exploration_root)
            fresh = generate_fresh_candidate_manifests(
                sample,
                sample.manifest.manifest,
                candidates_per_sample=config.candidates_per_sample,
                seed=config.seed + sample_index,
                disallowed_hashes=disallowed,
            )
            scored = score_fresh_candidates(sample, fresh, ranker)
            for candidate in scored:
                run_dir = sample_out / candidate.candidate_id
                manifest_path = run_dir / "labels" / "amg_manifest.json"
                run = _run_ansa_manifest(
                    sample=sample,
                    run_dir=run_dir,
                    manifest=candidate.manifest,
                    executable=executable,
                    batch_script=batch_script,
                    timeout_sec=config.timeout_sec_per_sample,
                )
                sample_records.append(_record_from_run(sample_id=sample.sample_id, candidate=candidate, manifest_path=manifest_path, run=run))
        except (AmgFreshProposalError, AmgQualityRecommendationError) as exc:
            sample_records.append(
                {
                    "schema": FRESH_RECORD_SCHEMA,
                    "sample_id": sample.sample_id,
                    "evaluation_id": "fresh_error",
                    "candidate_id": "fresh_error",
                    "candidate_hash": None,
                    "status": "BLOCKED",
                    "error_code": exc.code,
                    "message": str(exc),
                    "manifest_path": None,
                    "execution_report_path": None,
                    "quality_report_path": None,
                    "mesh_path": None,
                    "predicted_score": None,
                    "quality_score": None,
                    "accepted": False,
                    "mesh_nonempty": False,
                    "is_fresh_candidate": True,
                }
            )
        all_records.extend(sample_records)
        sample_results.append(_summarize_sample(sample.sample_id, sample_out, sample_records))

    counts = Counter(str(record.get("status")) for record in all_records if record.get("is_fresh_candidate"))
    scores = [float(record["quality_score"]) for record in all_records if isinstance(record.get("quality_score"), (int, float))]
    fresh_hashes = [str(record["candidate_hash"]) for record in all_records if record.get("is_fresh_candidate") and isinstance(record.get("candidate_hash"), str)]
    summary = {
        "schema": FRESH_SUMMARY_SCHEMA,
        "status": "SUCCESS" if counts.get("BLOCKED", 0) == 0 and fresh_hashes else "BLOCKED",
        "dataset_root": config.dataset_root.as_posix(),
        "source_quality_exploration_root": config.quality_exploration_root.as_posix(),
        "training_root": config.training_root.as_posix(),
        "output_dir": config.output_dir.as_posix(),
        "split": config.split,
        "sample_count": len(samples),
        "baseline_count": len(samples),
        "generated_count": len(fresh_hashes),
        "evaluated_count": sum(counts.values()),
        "passed_count": counts.get("PASSED", 0),
        "near_fail_count": counts.get("NEAR_FAIL", 0),
        "failed_count": counts.get("FAILED", 0),
        "blocked_count": counts.get("BLOCKED", 0),
        "quality_score_variance": statistics.pvariance(scores) if len(scores) > 1 else 0.0,
        "unique_candidate_hash_count": len(set(fresh_hashes)),
        "control_value_variance": _control_variance(all_records),
        "records": all_records,
        "sample_results": [result.__dict__ for result in sample_results],
    }
    summary_path = config.output_dir / "quality_exploration_summary.json"
    _write_json(summary_path, summary)
    return FreshProposalResult(
        status=str(summary["status"]),
        output_dir=config.output_dir.as_posix(),
        summary_path=summary_path.as_posix(),
        sample_count=len(samples),
        baseline_count=len(samples),
        generated_count=int(summary["generated_count"]),
        evaluated_count=int(summary["evaluated_count"]),
        passed_count=int(summary["passed_count"]),
        near_fail_count=int(summary["near_fail_count"]),
        failed_count=int(summary["failed_count"]),
        blocked_count=int(summary["blocked_count"]),
        quality_score_variance=float(summary["quality_score_variance"]),
        unique_candidate_hash_count=int(summary["unique_candidate_hash_count"]),
        control_value_variance=float(summary["control_value_variance"]),
        sample_results=tuple(sample_results),
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fresh AMG quality-control candidates and evaluate with real ANSA.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--quality-exploration", required=True)
    parser.add_argument("--training", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--candidates-per-sample", type=int, default=8)
    parser.add_argument("--seed", type=int, default=710)
    parser.add_argument("--ansa-executable", default=DEFAULT_ANSA_EXECUTABLE)
    parser.add_argument("--timeout-sec", type=int, default=180)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_fresh_quality_proposal(
            FreshProposalConfig(
                dataset_root=Path(args.dataset),
                quality_exploration_root=Path(args.quality_exploration),
                training_root=Path(args.training),
                output_dir=Path(args.out),
                ansa_executable=Path(args.ansa_executable),
                split=args.split,
                limit=args.limit,
                sample_ids=tuple(args.sample_id),
                candidates_per_sample=args.candidates_per_sample,
                seed=args.seed,
                timeout_sec_per_sample=args.timeout_sec,
            )
        )
    except (AmgFreshProposalError, AmgQualityRecommendationError) as exc:
        code = getattr(exc, "code", "fresh_proposal_failed")
        print(json.dumps({"status": "FAILED", "error_code": code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": result.status,
                "sample_count": result.sample_count,
                "generated_count": result.generated_count,
                "evaluated_count": result.evaluated_count,
                "blocked_count": result.blocked_count,
                "quality_score_variance": result.quality_score_variance,
                "summary_path": result.summary_path,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.status == "SUCCESS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
