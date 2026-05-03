from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.domain import (
    BendTruth,
    CutoutTruth,
    EntitySignaturesDocument,
    FeatureEntitySignature,
    FeatureTruthDocument,
    FlangeTruth,
    HoleTruth,
    MeshPolicy,
    PartClass,
    PartParams,
    SlotTruth,
)
from cad_dataset_factory.cdf.labels.manifest_writer import (
    FeatureClearance,
    ManifestBuildError,
    build_amg_manifest,
    write_amg_manifest,
)

ROOT = Path(__file__).resolve().parents[1]

FEATURE_POLICY = {
    "allow_small_feature_suppression": True,
    "retained_hole_min_divisions": 12,
    "bolt_hole_min_divisions": 24,
    "slot_end_min_divisions": 12,
    "min_flange_elements_across_width": 2,
    "min_bend_rows": 2,
    "max_bend_rows": 6,
}


def mesh_policy() -> MeshPolicy:
    return MeshPolicy(
        h0_mm=4.0,
        h_min_mm=1.2,
        h_max_mm=7.2,
        growth_rate_max=1.35,
    )


def part_params() -> PartParams:
    return PartParams(
        part_name="SMT_SM_FLAT_PANEL_T120_P000001",
        part_class=PartClass.SM_FLAT_PANEL,
        thickness_mm=1.2,
        width_mm=160.0,
        height_mm=100.0,
    )


def feature_truth() -> FeatureTruthDocument:
    return FeatureTruthDocument(
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
        ],
    )


def entity_signatures(*, omit: str | None = None) -> EntitySignaturesDocument:
    signatures = {
        "HOLE_BOLT_0001": {
            "geom_type": "circular_inner_loop",
            "center_mm": [80.0, 50.0, 0.0],
            "axis": [0.0, 0.0, 1.0],
            "radius_mm": 4.0,
        },
        "SLOT_MOUNT_0001": {
            "geom_type": "slot_inner_loop",
            "center_mm": [110.0, 50.0, 0.0],
            "width_mm": 8.0,
            "length_mm": 32.0,
        },
        "CUTOUT_PASSAGE_0001": {
            "geom_type": "cutout_inner_loop",
            "center_mm": [100.0, 60.0, 0.0],
            "width_mm": 32.0,
            "height_mm": 20.0,
        },
        "BEND_STRUCTURAL_0001": {
            "geom_type": "bend_patch",
            "inner_radius_mm": 2.4,
            "angle_deg": 90.0,
        },
        "FLANGE_STRUCTURAL_0001": {
            "geom_type": "flange_patch",
            "width_mm": 24.0,
            "free_edge_id": "EDGE_FLANGE_FREE_0001",
        },
    }
    roles = {
        "HOLE_BOLT_0001": "BOLT",
        "SLOT_MOUNT_0001": "MOUNT",
        "CUTOUT_PASSAGE_0001": "PASSAGE",
        "BEND_STRUCTURAL_0001": "STRUCTURAL",
        "FLANGE_STRUCTURAL_0001": "STRUCTURAL",
    }
    return EntitySignaturesDocument(
        sample_id="sample_000001",
        part_name="SMT_SM_FLAT_PANEL_T120_P000001",
        features=[
            FeatureEntitySignature(
                feature_id=feature_id,
                type=feature_id.split("_", 1)[0],
                role=roles[feature_id],
                signature=signature,
            )
            for feature_id, signature in signatures.items()
            if feature_id != omit
        ],
    )


def feature_clearances() -> dict[str, FeatureClearance]:
    return {
        "HOLE_BOLT_0001": FeatureClearance(
            clearance_to_boundary_mm=50.0,
            clearance_to_nearest_feature_mm=50.0,
        )
    }


def build_valid_manifest() -> dict:
    return build_amg_manifest(
        feature_truth=feature_truth(),
        entity_signatures=entity_signatures(),
        mesh_policy=mesh_policy(),
        feature_policy=FEATURE_POLICY,
        midsurface_area_mm2=16000.0,
        feature_clearances=feature_clearances(),
    )


def test_build_flat_panel_manifest_validates_schema() -> None:
    manifest = build_valid_manifest()
    schema = json.loads((ROOT / "contracts" / "AMG_MANIFEST_SM_V1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)

    assert manifest["schema_version"] == "AMG_MANIFEST_SM_V1"
    assert manifest["status"] == "VALID"
    assert manifest["cad_file"] == "cad/input.step"
    assert manifest["unit"] == "mm"


def test_manifest_features_have_geometry_signature_and_controls() -> None:
    manifest = build_valid_manifest()
    assert len(manifest["features"]) == 5
    for feature in manifest["features"]:
        assert feature["geometry_signature"]
        assert feature["controls"]


def test_bolt_hole_uses_washer_when_clearance_allows() -> None:
    manifest = build_valid_manifest()
    hole = next(feature for feature in manifest["features"] if feature["feature_id"] == "HOLE_BOLT_0001")
    assert hole["action"] == "KEEP_WITH_WASHER"
    assert hole["controls"]["washer_rings"] == 2


def test_missing_entity_signature_raises() -> None:
    with pytest.raises(ManifestBuildError) as exc_info:
        build_amg_manifest(
            feature_truth=feature_truth(),
            entity_signatures=entity_signatures(omit="SLOT_MOUNT_0001"),
            mesh_policy=mesh_policy(),
            feature_policy=FEATURE_POLICY,
            midsurface_area_mm2=16000.0,
            feature_clearances=feature_clearances(),
        )
    assert exc_info.value.code == "missing_entity_signature"
    assert exc_info.value.feature_id == "SLOT_MOUNT_0001"


def test_missing_bolt_mount_clearance_raises() -> None:
    with pytest.raises(ManifestBuildError) as exc_info:
        build_amg_manifest(
            feature_truth=feature_truth(),
            entity_signatures=entity_signatures(),
            mesh_policy=mesh_policy(),
            feature_policy=FEATURE_POLICY,
            midsurface_area_mm2=16000.0,
        )
    assert exc_info.value.code == "missing_feature_clearance"
    assert exc_info.value.feature_id == "HOLE_BOLT_0001"


def test_missing_midsurface_area_for_cutout_raises() -> None:
    with pytest.raises(ManifestBuildError) as exc_info:
        build_amg_manifest(
            feature_truth=feature_truth(),
            entity_signatures=entity_signatures(),
            mesh_policy=mesh_policy(),
            feature_policy=FEATURE_POLICY,
            feature_clearances=feature_clearances(),
        )
    assert exc_info.value.code == "missing_midsurface_area"
    assert exc_info.value.feature_id == "CUTOUT_PASSAGE_0001"


def test_write_amg_manifest_to_workspace_local_temp() -> None:
    manifest = build_valid_manifest()
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_manifest_writer" / "labels" / "amg_manifest.json"
    write_amg_manifest(path, manifest)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == "AMG_MANIFEST_SM_V1"
    assert loaded["features"][0]["geometry_signature"]
