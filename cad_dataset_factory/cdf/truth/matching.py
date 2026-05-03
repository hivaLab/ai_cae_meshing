"""Match generated CDF truth features to detected B-rep candidates."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cad_dataset_factory.cdf.brep import BrepGraph
from cad_dataset_factory.cdf.domain import BendTruth, CutoutTruth, FeatureTruthDocument, FlangeTruth, HoleTruth, SlotTruth

REPORT_SCHEMA = "CDF_FEATURE_MATCHING_REPORT_SM_V1"


class FeatureMatchingError(ValueError):
    """Raised when truth-to-candidate matching cannot be completed safely."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = code if feature_id is None else f"{code} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class _ScoredPair:
    feature_id: str
    candidate_id: str
    score: float
    metrics: dict[str, float | None]


def _jsonable(value: Any, *, code: str) -> dict[str, Any]:
    try:
        normalized = json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FeatureMatchingError(code, "document must be JSON-compatible") from exc
    if not isinstance(normalized, dict):
        raise FeatureMatchingError(code, "document must be a JSON object")
    return normalized


def _candidate_metadata(graph: BrepGraph) -> list[dict[str, Any]]:
    row_count = int(graph.arrays.get("feature_candidate_features", ()).shape[0]) if "feature_candidate_features" in graph.arrays else 0
    if row_count <= 0:
        raise FeatureMatchingError("missing_candidates", "graph does not contain feature candidate rows")

    if graph.candidate_metadata:
        metadata = [dict(item) for item in graph.candidate_metadata]
    elif "feature_candidate_metadata_json" in graph.arrays:
        metadata = []
        try:
            for raw in graph.arrays["feature_candidate_metadata_json"].tolist():
                metadata.append(json.loads(str(raw)))
        except (TypeError, ValueError) as exc:
            raise FeatureMatchingError("malformed_candidates", "feature_candidate_metadata_json must be parseable JSON") from exc
    else:
        raise FeatureMatchingError("missing_candidates", "graph does not contain feature candidate metadata")

    if len(metadata) != row_count:
        raise FeatureMatchingError("malformed_candidates", "candidate metadata count must match candidate feature rows")

    seen: set[str] = set()
    for item in metadata:
        candidate_id = item.get("candidate_id")
        feature_type = item.get("type")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise FeatureMatchingError("malformed_candidates", "candidate metadata requires candidate_id")
        if candidate_id in seen:
            raise FeatureMatchingError("malformed_candidates", "candidate ids must be unique")
        seen.add(candidate_id)
        if feature_type not in {"HOLE", "SLOT", "CUTOUT", "BEND", "FLANGE"}:
            raise FeatureMatchingError("malformed_candidates", "candidate type must be canonical")
    return metadata


def _truth_center_xy(feature: HoleTruth | SlotTruth | CutoutTruth) -> tuple[float, float]:
    if isinstance(feature, HoleTruth) and feature.center_mm is not None:
        return (float(feature.center_mm[0]), float(feature.center_mm[1]))
    if feature.center_uv_mm is not None:
        return (float(feature.center_uv_mm[0]), float(feature.center_uv_mm[1]))
    raise FeatureMatchingError("missing_truth_center", "truth feature requires center coordinates", feature.feature_id)


def _candidate_center_xy(candidate: dict[str, Any]) -> tuple[float, float]:
    center = candidate.get("center_mm")
    if not isinstance(center, list | tuple) or len(center) < 2:
        raise FeatureMatchingError("malformed_candidates", "candidate center_mm must be a 3-vector")
    return (float(center[0]), float(center[1]))


def _center_error(feature: HoleTruth | SlotTruth | CutoutTruth, candidate: dict[str, Any]) -> float:
    truth_x, truth_y = _truth_center_xy(feature)
    cand_x, cand_y = _candidate_center_xy(candidate)
    return math.hypot(truth_x - cand_x, truth_y - cand_y)


def _finite_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _score_hole(feature: HoleTruth, candidate: dict[str, Any]) -> tuple[float, dict[str, float | None], float]:
    center_error = _center_error(feature, candidate)
    radius_error = abs(float(feature.radius_mm) - _finite_float(candidate.get("radius_mm")))
    score = center_error + radius_error
    threshold = max(2.0, 0.25 * float(feature.radius_mm))
    return score, {
        "center_error_mm": center_error,
        "radius_error_mm": radius_error,
        "width_error_mm": None,
        "length_error_mm": None,
        "angle_error_deg": None,
        "axis_error_deg": 0.0,
    }, threshold


def _score_slot(feature: SlotTruth, candidate: dict[str, Any]) -> tuple[float, dict[str, float | None], float]:
    center_error = _center_error(feature, candidate)
    width_error = abs(float(feature.width_mm) - _finite_float(candidate.get("width_mm")))
    length_error = abs(float(feature.length_mm) - _finite_float(candidate.get("length_mm")))
    score = center_error + width_error + length_error
    threshold = max(3.0, 0.15 * float(feature.length_mm))
    return score, {
        "center_error_mm": center_error,
        "radius_error_mm": None,
        "width_error_mm": width_error,
        "length_error_mm": length_error,
        "angle_error_deg": None,
        "axis_error_deg": 0.0,
    }, threshold


def _score_cutout(feature: CutoutTruth, candidate: dict[str, Any]) -> tuple[float, dict[str, float | None], float]:
    center_error = _center_error(feature, candidate)
    truth_sizes = sorted((float(feature.width_mm), float(feature.height_mm)), reverse=True)
    candidate_sizes = sorted((_finite_float(candidate.get("width_mm")), _finite_float(candidate.get("length_mm"))), reverse=True)
    width_error = abs(truth_sizes[0] - candidate_sizes[0])
    length_error = abs(truth_sizes[1] - candidate_sizes[1])
    score = center_error + width_error + length_error
    threshold = max(2.0, 0.15 * max(truth_sizes))
    return score, {
        "center_error_mm": center_error,
        "radius_error_mm": None,
        "width_error_mm": width_error,
        "length_error_mm": length_error,
        "angle_error_deg": None,
        "axis_error_deg": 0.0,
    }, threshold


def _score_bend(feature: BendTruth, candidate: dict[str, Any]) -> tuple[float, dict[str, float | None], float]:
    angle_error = abs(float(feature.angle_deg) - _finite_float(candidate.get("size_2_mm")))
    length_penalty = 0.0 if _finite_float(candidate.get("length_mm")) > 0.0 else 10.0
    score = angle_error / 10.0 + length_penalty
    return score, {
        "center_error_mm": None,
        "radius_error_mm": None,
        "width_error_mm": None,
        "length_error_mm": None,
        "angle_error_deg": angle_error,
        "axis_error_deg": None,
    }, 2.0


def _score_flange(feature: FlangeTruth, candidate: dict[str, Any]) -> tuple[float, dict[str, float | None], float]:
    width = float(feature.width_mm)
    candidate_widths = [
        _finite_float(candidate.get("width_mm")),
        _finite_float(candidate.get("size_2_mm")),
        _finite_float(candidate.get("size_1_mm")),
    ]
    width_error = min(abs(width - value) for value in candidate_widths if value > 0.0)
    score = width_error
    return score, {
        "center_error_mm": None,
        "radius_error_mm": None,
        "width_error_mm": width_error,
        "length_error_mm": None,
        "angle_error_deg": None,
        "axis_error_deg": None,
    }, max(2.0, 0.12 * width)


def _score_pair(feature: Any, candidate: dict[str, Any]) -> tuple[float, dict[str, float | None], float]:
    if candidate.get("type") != feature.type:
        return math.inf, {}, -1.0
    if isinstance(feature, HoleTruth):
        return _score_hole(feature, candidate)
    if isinstance(feature, SlotTruth):
        return _score_slot(feature, candidate)
    if isinstance(feature, CutoutTruth):
        return _score_cutout(feature, candidate)
    if isinstance(feature, BendTruth):
        return _score_bend(feature, candidate)
    if isinstance(feature, FlangeTruth):
        return _score_flange(feature, candidate)
    raise FeatureMatchingError("unsupported_truth_feature", "truth feature type is not matchable", feature.feature_id)


def match_feature_truth_to_candidates(feature_truth: FeatureTruthDocument, graph: BrepGraph) -> list[dict[str, Any]]:
    """Return one-to-one truth-to-candidate matches for a generated CDF sample."""

    candidates = _candidate_metadata(graph)
    pairs: list[_ScoredPair] = []
    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    for feature in feature_truth.features:
        for candidate in candidates:
            score, metrics, threshold = _score_pair(feature, candidate)
            if score <= threshold:
                pairs.append(
                    _ScoredPair(
                        feature_id=feature.feature_id,
                        candidate_id=candidate["candidate_id"],
                        score=score,
                        metrics=metrics,
                    )
                )

    matches: list[_ScoredPair] = []
    used_features: set[str] = set()
    used_candidates: set[str] = set()
    for pair in sorted(pairs, key=lambda item: (item.score, item.feature_id, item.candidate_id)):
        if pair.feature_id in used_features or pair.candidate_id in used_candidates:
            continue
        matches.append(pair)
        used_features.add(pair.feature_id)
        used_candidates.add(pair.candidate_id)

    for feature in feature_truth.features:
        if feature.feature_id in used_features:
            continue
        duplicate_candidates = [pair for pair in pairs if pair.feature_id == feature.feature_id and pair.candidate_id in used_candidates]
        if duplicate_candidates:
            raise FeatureMatchingError(
                "duplicate_candidate_assignment",
                "best available candidate was already assigned to another truth feature",
                feature.feature_id,
            )

    return [
        _jsonable(
            {
                "feature_id": pair.feature_id,
                "type": candidate_by_id[pair.candidate_id]["type"],
                "detected_feature_id": pair.candidate_id,
                "score": pair.score,
                **pair.metrics,
            },
            code="malformed_match",
        )
        for pair in matches
    ]


def _recall_by_type(features: list[Any], matches: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    matched_ids = {match["feature_id"] for match in matches}
    result: dict[str, dict[str, float | int]] = {}
    for feature in features:
        bucket = result.setdefault(feature.type, {"truth_count": 0, "matched_count": 0, "recall": 0.0})
        bucket["truth_count"] = int(bucket["truth_count"]) + 1
        if feature.feature_id in matched_ids:
            bucket["matched_count"] = int(bucket["matched_count"]) + 1
    for bucket in result.values():
        truth_count = int(bucket["truth_count"])
        matched_count = int(bucket["matched_count"])
        bucket["recall"] = matched_count / truth_count if truth_count else 1.0
    return result


def build_feature_matching_report(sample_id: str, feature_truth: FeatureTruthDocument, graph: BrepGraph) -> dict[str, Any]:
    """Build a JSON-compatible CDF_FEATURE_MATCHING_REPORT_SM_V1 document."""

    if sample_id != feature_truth.sample_id:
        raise FeatureMatchingError("sample_id_mismatch", f"expected {feature_truth.sample_id}, got {sample_id}")
    candidates = _candidate_metadata(graph)
    matches = match_feature_truth_to_candidates(feature_truth, graph)
    matched_truth_ids = {match["feature_id"] for match in matches}
    matched_candidate_ids = {match["detected_feature_id"] for match in matches}
    truth_ids = [feature.feature_id for feature in feature_truth.features]
    detected_ids = [candidate["candidate_id"] for candidate in candidates]
    unmatched_truth = [feature_id for feature_id in truth_ids if feature_id not in matched_truth_ids]
    unmatched_detected = [candidate_id for candidate_id in detected_ids if candidate_id not in matched_candidate_ids]
    report = {
        "schema": REPORT_SCHEMA,
        "sample_id": sample_id,
        "accepted": not unmatched_truth and not unmatched_detected,
        "truth_feature_count": len(truth_ids),
        "detected_feature_count": len(detected_ids),
        "unmatched_truth_features": unmatched_truth,
        "unmatched_detected_features": unmatched_detected,
        "matches": matches,
        "recall_by_type": _recall_by_type(list(feature_truth.features), matches),
        "false_match_count": len(unmatched_detected),
    }
    return _jsonable(report, code="malformed_report")


def write_feature_matching_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a feature matching report to JSON."""

    normalized = _jsonable(report, code="malformed_report")
    if normalized.get("schema") != REPORT_SCHEMA:
        raise FeatureMatchingError("malformed_report", f"schema must be {REPORT_SCHEMA}")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
