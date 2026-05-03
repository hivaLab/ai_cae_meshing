from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from cad_dataset_factory.cdf.domain import (
    BendControl,
    CutoutControl,
    BendTruth,
    CutoutTruth,
    EntitySignaturesDocument,
    FeatureEntitySignature,
    FeatureTruthDocument,
    FlangeControl,
    FlangeTruth,
    HoleRefinedControl,
    HoleTruth,
    HoleWasherControl,
    ManifestAction,
    ManifestFeatureRecord,
    MeshPolicy,
    PartClass,
    PartParams,
    SlotControl,
    SlotTruth,
    SuppressionControl,
)


def part_params() -> PartParams:
    return PartParams(
        part_name="SMT_SM_FLAT_PANEL_T120_P000001",
        part_class=PartClass.SM_FLAT_PANEL,
        thickness_mm=1.2,
        width_mm=160.0,
        height_mm=100.0,
        corner_radius_mm=0.0,
    )


def test_feature_truth_document_serializes_with_schema_version() -> None:
    document = FeatureTruthDocument(
        sample_id="sample_000001",
        part=part_params(),
        features=[
            HoleTruth(
                feature_id="HOLE_BOLT_0001",
                role="BOLT",
                created_by="cadgen.circular_cut",
                center_uv_mm=(80.0, 50.0),
                radius_mm=4.0,
                patch_id="PATCH_MAIN_0001",
                axis_source="patch_normal",
            )
        ],
    )

    data = document.model_dump(mode="json")
    json.dumps(data)
    assert data["schema_version"] == "CDF_FEATURE_TRUTH_SM_V1"
    assert data["part"]["part_class"] == "SM_FLAT_PANEL"
    assert data["features"][0]["type"] == "HOLE"


def test_entity_signatures_document_serializes_with_schema_version() -> None:
    document = EntitySignaturesDocument(
        sample_id="sample_000001",
        part_name="SMT_SM_FLAT_PANEL_T120_P000001",
        features=[
            FeatureEntitySignature(
                feature_id="HOLE_BOLT_0001",
                type="HOLE",
                role="BOLT",
                signature={
                    "geom_type": "circular_inner_loop",
                    "center_mm": [80.0, 50.0, 0.0],
                    "axis": [0.0, 0.0, 1.0],
                    "radius_mm": 4.0,
                },
            )
        ],
    )

    data = document.to_json_dict()
    json.dumps(data)
    assert data["schema_version"] == "CDF_ENTITY_SIGNATURES_SM_V1"
    assert data["features"][0]["type"] == "HOLE"


def test_invalid_enum_values_raise_validation_errors() -> None:
    with pytest.raises(ValidationError):
        PartParams(
            part_name="bad",
            part_class="CASTING",
            thickness_mm=1.2,
        )

    with pytest.raises(ValidationError):
        FeatureEntitySignature(
            feature_id="HOLE_BAD_0001",
            type="HOLE",
            role="FASTENER",
            signature={},
        )


def test_all_feature_truth_types_validate() -> None:
    features = [
        HoleTruth(
            feature_id="HOLE_BOLT_0001",
            role="BOLT",
            created_by="cadgen.circular_cut",
            center_uv_mm=(80.0, 50.0),
            radius_mm=4.0,
            patch_id="PATCH_MAIN_0001",
        ),
        SlotTruth(
            feature_id="SLOT_MOUNT_0001",
            role="MOUNT",
            created_by="cadgen.slot_cut",
            center_uv_mm=(110.0, 50.0),
            width_mm=8.0,
            length_mm=32.0,
            patch_id="PATCH_MAIN_0001",
        ),
        CutoutTruth(
            feature_id="CUTOUT_PASSAGE_0001",
            role="PASSAGE",
            created_by="cadgen.cutout",
            center_uv_mm=(100.0, 60.0),
            width_mm=32.0,
            height_mm=20.0,
            patch_id="PATCH_MAIN_0001",
        ),
        BendTruth(
            feature_id="BEND_STRUCTURAL_0001",
            role="STRUCTURAL",
            created_by="cadgen.bend",
            inner_radius_mm=2.4,
            angle_deg=90.0,
            thickness_mm=1.2,
            adjacent_patch_ids=("PATCH_MAIN_0001", "PATCH_FLANGE_0001"),
        ),
        FlangeTruth(
            feature_id="FLANGE_STRUCTURAL_0001",
            role="STRUCTURAL",
            created_by="cadgen.flange",
            width_mm=24.0,
            free_edge_id="EDGE_FLANGE_FREE_0001",
            bend_id="BEND_STRUCTURAL_0001",
        ),
    ]

    document = FeatureTruthDocument(sample_id="sample_000001", part=part_params(), features=features)
    assert [feature["type"] for feature in document.model_dump(mode="json")["features"]] == [
        "HOLE",
        "SLOT",
        "CUTOUT",
        "BEND",
        "FLANGE",
    ]


def test_mesh_policy_rejects_invalid_numeric_bounds() -> None:
    with pytest.raises(ValidationError):
        MeshPolicy(h0_mm=0.0, h_min_mm=1.0, h_max_mm=2.0, growth_rate_max=1.3)

    with pytest.raises(ValidationError):
        MeshPolicy(h0_mm=4.0, h_min_mm=5.0, h_max_mm=2.0, growth_rate_max=1.3)


def test_manifest_control_records_serialize_with_canonical_actions() -> None:
    records = [
        ManifestFeatureRecord(
            feature_id="HOLE_BOLT_0001",
            type="HOLE",
            role="BOLT",
            action=ManifestAction.KEEP_WITH_WASHER,
            controls=HoleWasherControl(
                edge_target_length_mm=1.2,
                circumferential_divisions=24,
                radial_growth_rate=1.25,
                washer_rings=2,
                washer_outer_radius_mm=9.0,
            ),
        ),
        ManifestFeatureRecord(
            feature_id="HOLE_UNKNOWN_0002",
            type="HOLE",
            role="UNKNOWN",
            action="KEEP_REFINED",
            controls=HoleRefinedControl(
                edge_target_length_mm=1.2,
                circumferential_divisions=12,
                radial_growth_rate=1.25,
            ),
        ),
        ManifestFeatureRecord(
            feature_id="SLOT_MOUNT_0001",
            type="SLOT",
            role="MOUNT",
            action="KEEP_REFINED",
            controls=SlotControl(
                edge_target_length_mm=1.4,
                end_arc_divisions=12,
                straight_edge_divisions=8,
                growth_rate=1.25,
            ),
        ),
        ManifestFeatureRecord(
            feature_id="CUTOUT_PASSAGE_0001",
            type="CUTOUT",
            role="PASSAGE",
            action="KEEP_REFINED",
            controls=CutoutControl(edge_target_length_mm=2.0, perimeter_growth_rate=1.25),
        ),
        ManifestFeatureRecord(
            feature_id="HOLE_RELIEF_0002",
            type="HOLE",
            role="RELIEF",
            action="SUPPRESS",
            controls=SuppressionControl(suppression_rule="small_relief_or_drain"),
        ),
        ManifestFeatureRecord(
            feature_id="BEND_STRUCTURAL_0001",
            type="BEND",
            role="STRUCTURAL",
            action="KEEP_WITH_BEND_ROWS",
            controls=BendControl(bend_rows=3, bend_target_length_mm=1.8, growth_rate=1.25),
        ),
        ManifestFeatureRecord(
            feature_id="FLANGE_STRUCTURAL_0001",
            type="FLANGE",
            role="STRUCTURAL",
            action="KEEP_WITH_FLANGE_SIZE",
            controls=FlangeControl(flange_target_length_mm=4.0, min_elements_across_width=2),
        ),
    ]

    data = [record.model_dump(mode="json") for record in records]
    json.dumps(data)
    assert data[0]["action"] == "KEEP_WITH_WASHER"
    assert data[1]["action"] == "KEEP_REFINED"
    assert data[4]["action"] == "SUPPRESS"
    assert data[5]["controls"]["bend_rows"] == 3
