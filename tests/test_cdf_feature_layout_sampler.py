from __future__ import annotations

import pytest

from cad_dataset_factory.cdf.cadgen import FlatPanelSpec, build_flat_panel_part
from cad_dataset_factory.cdf.sampling import (
    BendKeepout,
    FeaturePlacementCandidate,
    FeaturePlacementError,
    PatchRegion,
    PlacementPolicy,
    sample_feature_layout,
    to_flat_panel_feature_specs,
    validate_feature_layout,
)


def patch() -> PatchRegion:
    return PatchRegion(width_mm=120.0, height_mm=80.0)


def policy(max_attempts: int = 200) -> PlacementPolicy:
    return PlacementPolicy(h0_mm=4.0, thickness_mm=1.2, max_attempts=max_attempts)


def hole(feature_id: str, center: tuple[float, float]) -> FeaturePlacementCandidate:
    return FeaturePlacementCandidate(
        feature_id=feature_id,
        type="HOLE",
        role="BOLT",
        center_uv_mm=center,
        radius_mm=4.0,
    )


def test_valid_layout_passes_boundary_clearance() -> None:
    report = validate_feature_layout(
        [
            hole("HOLE_BOLT_0001", (24.0, 30.0)),
            FeaturePlacementCandidate(
                feature_id="SLOT_MOUNT_0001",
                type="SLOT",
                role="MOUNT",
                center_uv_mm=(70.0, 30.0),
                width_mm=6.0,
                length_mm=20.0,
            ),
        ],
        patch(),
        policy(),
    )

    assert report.accepted is True
    assert report.reason is None
    assert report.required_boundary_clearance_mm == 3.0
    assert report.required_bend_clearance_mm == 4.0


def test_feature_too_close_to_boundary_returns_structured_rejection() -> None:
    report = validate_feature_layout([hole("HOLE_BOLT_0001", (5.0, 40.0))], patch(), policy())

    assert report.accepted is False
    assert report.reason == "boundary_clearance_failed"
    assert report.feature_id == "HOLE_BOLT_0001"
    assert report.clearance_to_boundary_mm == pytest.approx(1.0)


def test_feature_feature_clearance_failure_returns_structured_rejection() -> None:
    report = validate_feature_layout(
        [
            hole("HOLE_BOLT_0001", (30.0, 40.0)),
            hole("HOLE_BOLT_0002", (38.0, 40.0)),
        ],
        patch(),
        policy(),
    )

    assert report.accepted is False
    assert report.reason == "feature_feature_clearance_failed"
    assert report.feature_id == "HOLE_BOLT_0002"
    assert report.other_feature_id == "HOLE_BOLT_0001"
    assert report.clearance_to_nearest_feature_mm == pytest.approx(0.0)


def test_bend_clearance_failure_returns_structured_rejection() -> None:
    report = validate_feature_layout(
        [hole("HOLE_BOLT_0001", (56.0, 40.0))],
        patch(),
        policy(),
        bend_keepouts=[BendKeepout(bend_id="BEND_STRUCTURAL_0001", start_uv_mm=(50.0, 0.0), end_uv_mm=(50.0, 80.0))],
    )

    assert report.accepted is False
    assert report.reason == "bend_clearance_failed"
    assert report.feature_id == "HOLE_BOLT_0001"
    assert report.bend_id == "BEND_STRUCTURAL_0001"
    assert report.clearance_to_bend_mm == pytest.approx(2.0)


def test_invalid_patch_size_raises_structured_error() -> None:
    with pytest.raises(FeaturePlacementError) as exc_info:
        validate_feature_layout(
            [hole("HOLE_BOLT_0001", (8.0, 8.0))],
            PatchRegion(width_mm=12.0, height_mm=80.0),
            policy(),
        )

    assert exc_info.value.code == "invalid_patch_size"
    assert exc_info.value.feature_id == "PATCH_MAIN_0001"


def test_same_seed_generates_identical_layout() -> None:
    feature_specs = [
        {"type": "HOLE", "role": "BOLT", "radius_mm": 4.0},
        {"type": "SLOT", "role": "MOUNT", "width_mm": 6.0, "length_mm": 20.0},
        {"type": "CUTOUT", "role": "PASSAGE", "width_mm": 12.0, "height_mm": 10.0},
    ]

    first = sample_feature_layout(patch=patch(), policy=policy(), feature_specs=feature_specs, seed=1234)
    second = sample_feature_layout(patch=patch(), policy=policy(), feature_specs=feature_specs, seed=1234)

    assert [candidate.model_dump(mode="json") for candidate in first] == [
        candidate.model_dump(mode="json") for candidate in second
    ]
    assert [candidate.feature_id for candidate in first] == [
        "HOLE_BOLT_0001",
        "SLOT_MOUNT_0001",
        "CUTOUT_PASSAGE_0001",
    ]


def test_sampling_exhaustion_raises_structured_error() -> None:
    with pytest.raises(FeaturePlacementError) as exc_info:
        sample_feature_layout(
            patch=PatchRegion(width_mm=20.0, height_mm=20.0),
            policy=policy(max_attempts=5),
            feature_specs=[{"type": "HOLE", "role": "BOLT", "radius_mm": 9.0}],
            seed=7,
        )

    assert exc_info.value.code == "placement_exhausted"
    assert exc_info.value.feature_id == "HOLE_BOLT_0001"


def test_generated_candidates_convert_to_flat_panel_feature_specs() -> None:
    pytest.importorskip("cadquery")
    candidates = sample_feature_layout(
        patch=patch(),
        policy=policy(),
        feature_specs=[
            {"type": "HOLE", "role": "BOLT", "radius_mm": 4.0},
            {"type": "CUTOUT", "role": "PASSAGE", "width_mm": 12.0, "height_mm": 10.0},
        ],
        seed=9,
    )

    flat_specs = to_flat_panel_feature_specs(candidates)
    generated = build_flat_panel_part(
        FlatPanelSpec(
            sample_id="sample_000203",
            part_name="SMT_SM_FLAT_PANEL_T120_P000203",
            width_mm=120.0,
            height_mm=80.0,
            thickness_mm=1.2,
            features=flat_specs,
        )
    )

    assert len(generated.feature_truth.features) == 2
    assert generated.feature_truth.features[0].feature_id == "HOLE_BOLT_0001"
