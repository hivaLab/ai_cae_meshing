from __future__ import annotations

from cad_dataset_factory.cdf.labels.amg_rules import (
    KEEP_REFINED,
    KEEP_WITH_BEND_ROWS,
    KEEP_WITH_FLANGE_SIZE,
    KEEP_WITH_WASHER,
    SUPPRESS,
    bend_rule,
    cutout_rule,
    flange_rule,
    hole_rule,
    slot_rule,
)
from ai_mesh_generator.labels import rule_manifest

MESH_POLICY = {
    "h0_mm": 4.0,
    "h_min_mm": 1.2,
    "h_max_mm": 7.2,
    "growth_rate_max": 1.3,
}
FEATURE_POLICY = {
    "allow_small_feature_suppression": True,
    "retained_hole_min_divisions": 12,
    "bolt_hole_min_divisions": 24,
    "slot_end_min_divisions": 12,
    "min_flange_elements_across_width": 2,
    "min_bend_rows": 2,
    "max_bend_rows": 6,
}


def assert_targets_in_bounds(result: dict) -> None:
    controls = result["controls"]
    for key, value in controls.items():
        if key.endswith("_target_length_mm") or key == "edge_target_length_mm":
            assert MESH_POLICY["h_min_mm"] <= value <= MESH_POLICY["h_max_mm"]


def test_hole_label_rule() -> None:
    bolt = hole_rule(
        radius_mm=4.0,
        role="BOLT",
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
        clearance_to_boundary_mm=50.0,
        clearance_to_nearest_feature_mm=50.0,
    )
    assert bolt["action"] == KEEP_WITH_WASHER
    assert bolt["controls"]["washer_rings"] == 2
    assert_targets_in_bounds(bolt)

    unknown = hole_rule(
        radius_mm=1.0,
        role="UNKNOWN",
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert unknown["action"] == KEEP_REFINED

    relief = hole_rule(
        radius_mm=0.8,
        role="RELIEF",
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert relief["action"] == SUPPRESS


def test_hole_washer_downgrades_when_clearance_is_too_small() -> None:
    result = hole_rule(
        radius_mm=4.0,
        role="BOLT",
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
        clearance_to_boundary_mm=8.0,
        clearance_to_nearest_feature_mm=8.0,
    )
    assert result["action"] == KEEP_REFINED


def test_slot_label_rule() -> None:
    mount = slot_rule(
        width_mm=8.0,
        length_mm=32.0,
        role="MOUNT",
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert mount["action"] == KEEP_REFINED
    assert mount["controls"]["end_arc_divisions"] % 2 == 0
    assert_targets_in_bounds(mount)

    relief = slot_rule(
        width_mm=2.0,
        length_mm=10.0,
        role="RELIEF",
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert relief["action"] == SUPPRESS


def test_cutout_label_rule() -> None:
    passage = cutout_rule(
        width_mm=32.0,
        height_mm=20.0,
        area_mm2=640.0,
        midsurface_area_mm2=16000.0,
        role="PASSAGE",
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert passage["action"] == KEEP_REFINED
    assert_targets_in_bounds(passage)

    relief = cutout_rule(
        width_mm=8.0,
        height_mm=8.0,
        area_mm2=64.0,
        midsurface_area_mm2=16000.0,
        role="RELIEF",
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert relief["action"] == SUPPRESS


def test_bend_label_rule() -> None:
    result = bend_rule(
        inner_radius_mm=2.4,
        angle_deg=90.0,
        thickness_mm=1.2,
        mesh_policy=MESH_POLICY,
        feature_policy=FEATURE_POLICY,
    )
    assert result["action"] == KEEP_WITH_BEND_ROWS
    assert 2 <= result["controls"]["bend_rows"] <= 6
    assert_targets_in_bounds(result)


def test_flange_label_rule() -> None:
    result = flange_rule(width_mm=24.0, mesh_policy=MESH_POLICY, feature_policy=FEATURE_POLICY)
    assert result["action"] == KEEP_WITH_FLANGE_SIZE
    assert result["controls"]["min_elements_across_width"] == 2
    assert_targets_in_bounds(result)


def test_amg_rule_module_imports_without_cdf_dependency() -> None:
    result = rule_manifest.flange_rule(width_mm=24.0, mesh_policy=MESH_POLICY, feature_policy=FEATURE_POLICY)
    assert result["action"] == KEEP_WITH_FLANGE_SIZE
