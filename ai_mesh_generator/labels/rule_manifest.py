"""Deterministic AMG label rules for rule-only manifest generation."""

from __future__ import annotations

import math
from typing import Any

from ai_mesh_generator.labels.sizing import chord_error_size, clamp, make_even, safe_ceil

KEEP_REFINED = "KEEP_REFINED"
KEEP_WITH_WASHER = "KEEP_WITH_WASHER"
SUPPRESS = "SUPPRESS"
KEEP_WITH_BEND_ROWS = "KEEP_WITH_BEND_ROWS"
KEEP_WITH_FLANGE_SIZE = "KEEP_WITH_FLANGE_SIZE"


def _mesh_bounds(mesh_policy: dict[str, Any]) -> tuple[float, float, float, float]:
    h0 = float(mesh_policy["h0_mm"])
    h_min = float(mesh_policy.get("h_min_mm", 0.30 * h0))
    h_max = float(mesh_policy.get("h_max_mm", 1.80 * h0))
    growth = float(mesh_policy.get("growth_rate_max", 1.25))
    return h0, h_min, h_max, growth


def _allow_suppression(role: str, feature_policy: dict[str, Any] | None) -> bool:
    policy = feature_policy or {}
    if "allow_small_feature_suppression" in policy:
        return bool(policy["allow_small_feature_suppression"])
    if role == "RELIEF":
        return bool(policy.get("small_relief_hole_suppress", False))
    if role == "DRAIN":
        return bool(policy.get("small_drain_hole_suppress", False))
    return False


def _bounded_target(value: float, mesh_policy: dict[str, Any]) -> float:
    _, h_min, h_max, _ = _mesh_bounds(mesh_policy)
    return clamp(value, h_min, h_max)


def hole_rule(
    *,
    radius_mm: float,
    role: str,
    thickness_mm: float,
    mesh_policy: dict[str, Any],
    feature_policy: dict[str, Any] | None = None,
    clearance_to_boundary_mm: float = math.inf,
    clearance_to_nearest_feature_mm: float = math.inf,
) -> dict[str, Any]:
    h0, _, _, growth = _mesh_bounds(mesh_policy)
    role = role.upper()
    diameter = 2.0 * radius_mm

    if role in {"BOLT", "MOUNT"}:
        action = KEEP_WITH_WASHER
    elif role in {"RELIEF", "DRAIN"} and _allow_suppression(role, feature_policy):
        action = SUPPRESS if diameter <= min(0.60 * h0, 2.0 * thickness_mm) else KEEP_REFINED
    else:
        action = KEEP_REFINED

    n_min = int((feature_policy or {}).get(
        "bolt_hole_min_divisions" if role in {"BOLT", "MOUNT"} else "retained_hole_min_divisions",
        24 if role in {"BOLT", "MOUNT"} else 12,
    ))
    n_theta = make_even(max(n_min, safe_ceil((2.0 * math.pi * radius_mm) / h0)))
    h_hole = _bounded_target((2.0 * math.pi * radius_mm) / n_theta, mesh_policy)

    if action == SUPPRESS:
        return {"action": SUPPRESS, "controls": {"suppression_rule": "small_relief_or_drain"}}

    controls: dict[str, Any] = {
        "edge_target_length_mm": h_hole,
        "circumferential_divisions": n_theta,
        "radial_growth_rate": min(1.25, growth),
    }
    if action == KEEP_WITH_WASHER:
        washer_rings = 2
        raw_radius = max(2.0 * radius_mm, radius_mm + washer_rings * h_hole)
        clearance = min(clearance_to_boundary_mm, clearance_to_nearest_feature_mm)
        limit = math.inf if math.isinf(clearance) else 0.45 * clearance
        washer_radius = min(raw_radius, limit)
        if washer_radius < radius_mm + 1.5 * h_hole:
            return {"action": KEEP_REFINED, "controls": controls}
        controls.update(
            {
                "washer_rings": washer_rings,
                "washer_outer_radius_mm": washer_radius,
            }
        )
    return {"action": action, "controls": controls}


def slot_rule(
    *,
    width_mm: float,
    length_mm: float,
    role: str,
    thickness_mm: float,
    mesh_policy: dict[str, Any],
    feature_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    h0, _, _, growth = _mesh_bounds(mesh_policy)
    role = role.upper()
    if role in {"RELIEF", "DRAIN"} and _allow_suppression(role, feature_policy):
        action = SUPPRESS if width_mm <= min(0.60 * h0, 2.0 * thickness_mm) else KEEP_REFINED
    else:
        action = KEEP_REFINED
    if action == SUPPRESS:
        return {"action": SUPPRESS, "controls": {"suppression_rule": "small_relief_or_drain"}}

    h_slot = _bounded_target(min(h0, width_mm / 3.0), mesh_policy)
    end_radius = width_mm / 2.0
    min_end_divisions = int((feature_policy or {}).get("slot_end_min_divisions", 12))
    return {
        "action": KEEP_REFINED,
        "controls": {
            "edge_target_length_mm": h_slot,
            "end_arc_divisions": make_even(max(min_end_divisions, safe_ceil(math.pi * end_radius / h_slot))),
            "straight_edge_divisions": max(2, safe_ceil(max(length_mm - width_mm, 0.0) / h_slot)),
            "growth_rate": min(1.25, growth),
        },
    }


def cutout_rule(
    *,
    width_mm: float,
    height_mm: float,
    area_mm2: float,
    midsurface_area_mm2: float,
    role: str,
    mesh_policy: dict[str, Any],
    feature_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = role.upper()
    area_ratio = area_mm2 / midsurface_area_mm2
    if role in {"RELIEF", "DRAIN"} and _allow_suppression(role, feature_policy) and area_ratio < 0.01:
        return {"action": SUPPRESS, "controls": {"suppression_rule": "small_relief_or_drain_area"}}
    h0, _, _, growth = _mesh_bounds(mesh_policy)
    return {
        "action": KEEP_REFINED,
        "controls": {
            "edge_target_length_mm": _bounded_target(min(h0, min(width_mm, height_mm) / 4.0), mesh_policy),
            "perimeter_growth_rate": min(1.25, growth),
        },
    }


def bend_rule(
    *,
    inner_radius_mm: float,
    angle_deg: float,
    thickness_mm: float,
    mesh_policy: dict[str, Any],
    feature_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    h0, h_min, h_max, growth = _mesh_bounds(mesh_policy)
    policy = feature_policy or {}
    min_rows = int(policy.get("min_bend_rows", 2))
    max_rows = int(policy.get("max_bend_rows", 6))
    neutral_radius = inner_radius_mm + thickness_mm / 2.0
    arc_length = math.radians(angle_deg) * neutral_radius
    h_curv = chord_error_size(neutral_radius, thickness_mm, h0, h_min, h0)
    rows = int(clamp(safe_ceil(arc_length / h_curv), min_rows, max_rows))
    return {
        "action": KEEP_WITH_BEND_ROWS,
        "controls": {
            "bend_rows": rows,
            "bend_target_length_mm": clamp(arc_length / rows, h_min, h_max),
            "growth_rate": min(1.25, growth),
        },
    }


def flange_rule(
    *,
    width_mm: float,
    mesh_policy: dict[str, Any],
    feature_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    h0, h_min, _, _ = _mesh_bounds(mesh_policy)
    min_across = int((feature_policy or {}).get("min_flange_elements_across_width", 2))
    n_flange = max(min_across, safe_ceil(width_mm / h0))
    target = clamp(width_mm / n_flange, h_min, h0)
    return {
        "action": KEEP_WITH_FLANGE_SIZE,
        "controls": {
            "flange_target_length_mm": target,
            "min_elements_across_width": min_across,
        },
    }
