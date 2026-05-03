"""Deterministic CDF feature layout sampling and clearance validation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import Field

from cad_dataset_factory.cdf.cadgen import FlatPanelFeatureSpec
from cad_dataset_factory.cdf.domain import CdfBaseModel, FeatureRole, FeatureType

SUPPORTED_FEATURE_TYPES = {FeatureType.HOLE, FeatureType.SLOT, FeatureType.CUTOUT}


class FeaturePlacementError(ValueError):
    """Raised when a feature layout cannot be sampled or validated safely."""

    def __init__(self, code: str, message: str, feature_id: str | None = None) -> None:
        self.code = code
        self.feature_id = feature_id
        prefix = code if feature_id is None else f"{code} [{feature_id}]"
        super().__init__(f"{prefix}: {message}")


class PlacementPolicy(CdfBaseModel):
    h0_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)
    max_attempts: int = Field(default=1000, gt=0)
    min_patch_size_factor: float = Field(default=4.0, gt=0)

    @property
    def boundary_clearance_mm(self) -> float:
        return max(0.75 * self.h0_mm, 2.0 * self.thickness_mm)

    @property
    def feature_clearance_mm(self) -> float:
        return max(0.75 * self.h0_mm, 2.0 * self.thickness_mm)

    @property
    def bend_clearance_mm(self) -> float:
        return max(1.0 * self.h0_mm, 3.0 * self.thickness_mm)


class PatchRegion(CdfBaseModel):
    patch_id: str = "PATCH_MAIN_0001"
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


class BendKeepout(CdfBaseModel):
    bend_id: str
    start_uv_mm: tuple[float, float]
    end_uv_mm: tuple[float, float]


class FeaturePlacementCandidate(CdfBaseModel):
    feature_id: str
    type: FeatureType
    role: FeatureRole
    center_uv_mm: tuple[float, float]
    radius_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    angle_deg: float = 0.0
    corner_radius_mm: float | None = Field(default=None, ge=0)


class FeatureLayoutReport(CdfBaseModel):
    accepted: bool
    reason: str | None = None
    feature_id: str | None = None
    other_feature_id: str | None = None
    bend_id: str | None = None
    clearance_to_boundary_mm: float | None = None
    clearance_to_nearest_feature_mm: float | None = None
    clearance_to_bend_mm: float | None = None
    required_boundary_clearance_mm: float
    required_feature_clearance_mm: float
    required_bend_clearance_mm: float


@dataclass(frozen=True)
class _FeatureRequest:
    type: FeatureType
    role: FeatureRole
    radius_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    length_mm: float | None = None
    angle_deg: float = 0.0
    corner_radius_mm: float | None = None
    feature_id: str | None = None


def _empty_report(policy: PlacementPolicy, *, accepted: bool, reason: str | None = None) -> FeatureLayoutReport:
    return FeatureLayoutReport(
        accepted=accepted,
        reason=reason,
        required_boundary_clearance_mm=policy.boundary_clearance_mm,
        required_feature_clearance_mm=policy.feature_clearance_mm,
        required_bend_clearance_mm=policy.bend_clearance_mm,
    )


def _check_patch(patch: PatchRegion, policy: PlacementPolicy) -> None:
    min_size = policy.min_patch_size_factor * policy.h0_mm
    if min(patch.width_mm, patch.height_mm) < min_size:
        raise FeaturePlacementError(
            "invalid_patch_size",
            f"minimum patch dimension must be >= {policy.min_patch_size_factor} * h0_mm",
            patch.patch_id,
        )


def _ensure_supported(feature_type: FeatureType, feature_id: str | None = None) -> None:
    if feature_type not in SUPPORTED_FEATURE_TYPES:
        raise FeaturePlacementError("unsupported_feature_type", "T-203 supports HOLE, SLOT, and CUTOUT only", feature_id)


def _ensure_axis_aligned(angle_deg: float, feature_id: str | None = None) -> None:
    if not math.isclose(angle_deg, 0.0, abs_tol=1e-9):
        raise FeaturePlacementError("unsupported_feature_angle", "T-203 v1 supports axis-aligned features only", feature_id)


def _bounding_radius(candidate: FeaturePlacementCandidate | _FeatureRequest) -> float:
    _ensure_supported(candidate.type, candidate.feature_id)
    _ensure_axis_aligned(candidate.angle_deg, candidate.feature_id)
    if candidate.type == FeatureType.HOLE:
        if candidate.radius_mm is None:
            raise FeaturePlacementError("invalid_feature_dimensions", "HOLE requires radius_mm", candidate.feature_id)
        return candidate.radius_mm
    if candidate.type == FeatureType.SLOT:
        if candidate.width_mm is None or candidate.length_mm is None:
            raise FeaturePlacementError("invalid_feature_dimensions", "SLOT requires width_mm and length_mm", candidate.feature_id)
        if candidate.length_mm < candidate.width_mm:
            raise FeaturePlacementError("invalid_feature_dimensions", "SLOT length_mm must be >= width_mm", candidate.feature_id)
        return 0.5 * math.hypot(candidate.length_mm, candidate.width_mm)
    if candidate.type == FeatureType.CUTOUT:
        if candidate.width_mm is None or candidate.height_mm is None:
            raise FeaturePlacementError("invalid_feature_dimensions", "CUTOUT requires width_mm and height_mm", candidate.feature_id)
        if candidate.corner_radius_mm not in (None, 0.0):
            raise FeaturePlacementError("unsupported_corner_radius", "rounded CUTOUT corners are deferred", candidate.feature_id)
        return 0.5 * math.hypot(candidate.width_mm, candidate.height_mm)
    raise FeaturePlacementError("unsupported_feature_type", "T-203 supports HOLE, SLOT, and CUTOUT only", candidate.feature_id)


def _boundary_clearance(candidate: FeaturePlacementCandidate, patch: PatchRegion) -> float:
    radius = _bounding_radius(candidate)
    u, v = candidate.center_uv_mm
    return min(u, patch.width_mm - u, v, patch.height_mm - v) - radius


def _feature_clearance(a: FeaturePlacementCandidate, b: FeaturePlacementCandidate) -> float:
    au, av = a.center_uv_mm
    bu, bv = b.center_uv_mm
    return math.hypot(au - bu, av - bv) - _bounding_radius(a) - _bounding_radius(b)


def _point_segment_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if math.isclose(dx, 0.0, abs_tol=1e-12) and math.isclose(dy, 0.0, abs_tol=1e-12):
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _bend_clearance(candidate: FeaturePlacementCandidate, bend: BendKeepout) -> float:
    return _point_segment_distance(candidate.center_uv_mm, bend.start_uv_mm, bend.end_uv_mm) - _bounding_radius(candidate)


def validate_feature_layout(
    candidates: Sequence[FeaturePlacementCandidate | Mapping[str, Any]],
    patch: PatchRegion,
    policy: PlacementPolicy,
    bend_keepouts: Sequence[BendKeepout | Mapping[str, Any]] | None = None,
) -> FeatureLayoutReport:
    """Validate feature boundary, feature-feature, bend, and patch clearances."""

    _check_patch(patch, policy)
    normalized = [
        candidate if isinstance(candidate, FeaturePlacementCandidate) else FeaturePlacementCandidate.model_validate(candidate)
        for candidate in candidates
    ]
    bends = [bend if isinstance(bend, BendKeepout) else BendKeepout.model_validate(bend) for bend in bend_keepouts or ()]

    seen_ids: set[str] = set()
    for candidate in normalized:
        if candidate.feature_id in seen_ids:
            raise FeaturePlacementError("duplicate_feature_id", "feature ids must be unique", candidate.feature_id)
        seen_ids.add(candidate.feature_id)
        boundary = _boundary_clearance(candidate, patch)
        if boundary < policy.boundary_clearance_mm:
            return FeatureLayoutReport(
                accepted=False,
                reason="boundary_clearance_failed",
                feature_id=candidate.feature_id,
                clearance_to_boundary_mm=boundary,
                required_boundary_clearance_mm=policy.boundary_clearance_mm,
                required_feature_clearance_mm=policy.feature_clearance_mm,
                required_bend_clearance_mm=policy.bend_clearance_mm,
            )

    for index, candidate in enumerate(normalized):
        for other in normalized[index + 1 :]:
            clearance = _feature_clearance(candidate, other)
            if clearance < policy.feature_clearance_mm:
                return FeatureLayoutReport(
                    accepted=False,
                    reason="feature_feature_clearance_failed",
                    feature_id=other.feature_id,
                    other_feature_id=candidate.feature_id,
                    clearance_to_nearest_feature_mm=clearance,
                    required_boundary_clearance_mm=policy.boundary_clearance_mm,
                    required_feature_clearance_mm=policy.feature_clearance_mm,
                    required_bend_clearance_mm=policy.bend_clearance_mm,
                )

    for candidate in normalized:
        for bend in bends:
            clearance = _bend_clearance(candidate, bend)
            if clearance < policy.bend_clearance_mm:
                return FeatureLayoutReport(
                    accepted=False,
                    reason="bend_clearance_failed",
                    feature_id=candidate.feature_id,
                    bend_id=bend.bend_id,
                    clearance_to_bend_mm=clearance,
                    required_boundary_clearance_mm=policy.boundary_clearance_mm,
                    required_feature_clearance_mm=policy.feature_clearance_mm,
                    required_bend_clearance_mm=policy.bend_clearance_mm,
                )

    return _empty_report(policy, accepted=True)


def _as_rng(seed: int | random.Random | None) -> random.Random:
    if isinstance(seed, random.Random):
        return seed
    return random.Random(seed)


def _request_from_mapping(data: FeaturePlacementCandidate | Mapping[str, Any]) -> _FeatureRequest:
    raw = data.model_dump(mode="json") if isinstance(data, FeaturePlacementCandidate) else dict(data)
    try:
        feature_type = FeatureType(raw["type"])
    except (KeyError, ValueError) as exc:
        raise FeaturePlacementError("unsupported_feature_type", "feature request requires supported type") from exc
    try:
        role = FeatureRole(raw["role"])
    except (KeyError, ValueError) as exc:
        raise FeaturePlacementError("unsupported_feature_role", "feature request requires canonical role") from exc
    return _FeatureRequest(
        type=feature_type,
        role=role,
        radius_mm=raw.get("radius_mm"),
        width_mm=raw.get("width_mm"),
        height_mm=raw.get("height_mm"),
        length_mm=raw.get("length_mm"),
        angle_deg=float(raw.get("angle_deg", 0.0)),
        corner_radius_mm=raw.get("corner_radius_mm"),
        feature_id=raw.get("feature_id"),
    )


def _feature_id(feature_type: FeatureType, role: FeatureRole, counters: dict[tuple[FeatureType, FeatureRole], int]) -> str:
    key = (feature_type, role)
    counters[key] = counters.get(key, 0) + 1
    return f"{feature_type.value}_{role.value}_{counters[key]:04d}"


def _candidate_from_request(
    request: _FeatureRequest,
    *,
    feature_id: str,
    center_uv_mm: tuple[float, float],
) -> FeaturePlacementCandidate:
    return FeaturePlacementCandidate(
        feature_id=feature_id,
        type=request.type,
        role=request.role,
        center_uv_mm=center_uv_mm,
        radius_mm=request.radius_mm,
        width_mm=request.width_mm,
        height_mm=request.height_mm,
        length_mm=request.length_mm,
        angle_deg=request.angle_deg,
        corner_radius_mm=request.corner_radius_mm,
    )


def sample_feature_layout(
    *,
    patch: PatchRegion,
    policy: PlacementPolicy,
    feature_specs: Sequence[FeaturePlacementCandidate | Mapping[str, Any]],
    seed: int | random.Random | None = None,
    bend_keepouts: Sequence[BendKeepout | Mapping[str, Any]] | None = None,
) -> list[FeaturePlacementCandidate]:
    """Sample a deterministic layout that satisfies clearance constraints."""

    _check_patch(patch, policy)
    rng = _as_rng(seed)
    counters: dict[tuple[FeatureType, FeatureRole], int] = {}
    placed: list[FeaturePlacementCandidate] = []

    for raw_request in feature_specs:
        request = _request_from_mapping(raw_request)
        radius = _bounding_radius(request)
        feature_id = request.feature_id or _feature_id(request.type, request.role, counters)
        margin = radius + policy.boundary_clearance_mm
        if margin * 2.0 > patch.width_mm or margin * 2.0 > patch.height_mm:
            raise FeaturePlacementError("placement_exhausted", "feature cannot fit inside patch boundary", feature_id)

        for _ in range(policy.max_attempts):
            center = (
                rng.uniform(margin, patch.width_mm - margin),
                rng.uniform(margin, patch.height_mm - margin),
            )
            candidate = _candidate_from_request(request, feature_id=feature_id, center_uv_mm=center)
            report = validate_feature_layout([*placed, candidate], patch, policy, bend_keepouts)
            if report.accepted:
                placed.append(candidate)
                break
        else:
            raise FeaturePlacementError("placement_exhausted", "max placement attempts exhausted", feature_id)

    return placed


def to_flat_panel_feature_specs(candidates: Sequence[FeaturePlacementCandidate | Mapping[str, Any]]) -> list[FlatPanelFeatureSpec]:
    """Convert accepted placement candidates to T-201 flat-panel feature specs."""

    specs: list[FlatPanelFeatureSpec] = []
    for raw_candidate in candidates:
        candidate = (
            raw_candidate
            if isinstance(raw_candidate, FeaturePlacementCandidate)
            else FeaturePlacementCandidate.model_validate(raw_candidate)
        )
        _bounding_radius(candidate)
        specs.append(
            FlatPanelFeatureSpec(
                feature_id=candidate.feature_id,
                type=candidate.type,
                role=candidate.role,
                center_uv_mm=candidate.center_uv_mm,
                radius_mm=candidate.radius_mm,
                width_mm=candidate.width_mm,
                height_mm=candidate.height_mm,
                length_mm=candidate.length_mm,
                angle_deg=candidate.angle_deg,
                corner_radius_mm=candidate.corner_radius_mm,
            )
        )
    return specs
