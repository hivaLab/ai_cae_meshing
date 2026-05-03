from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cad_dataset_factory.cdf.labels.aux_label_writer import (
    AuxLabelBuildError,
    build_aux_labels,
    build_edge_labels,
    build_face_labels,
    build_feature_labels,
    write_aux_labels,
)
from test_cdf_manifest_writer import build_valid_manifest, mesh_policy

ROOT = Path(__file__).resolve().parents[1]


def _manifest_feature_ids(manifest: dict) -> list[str]:
    return [feature["feature_id"] for feature in manifest["features"]]


def test_feature_labels_match_manifest_feature_ids_one_to_one() -> None:
    manifest = build_valid_manifest()
    labels = build_feature_labels("sample_000001", manifest)

    assert labels["schema"] == "CDF_FEATURE_LABELS_SM_V1"
    assert labels["sample_id"] == "sample_000001"
    assert [label["feature_id"] for label in labels["labels"]] == _manifest_feature_ids(manifest)
    assert all("geometry_signature" not in label for label in labels["labels"])


def test_edge_labels_reference_only_manifest_feature_ids() -> None:
    manifest = build_valid_manifest()
    labels = build_edge_labels("sample_000001", manifest)
    manifest_ids = set(_manifest_feature_ids(manifest))

    assert labels["schema"] == "CDF_EDGE_LABELS_SM_V1"
    assert {label["feature_id"] for label in labels["labels"]}.issubset(manifest_ids)
    assert len(labels["labels"]) == len(manifest_ids)
    for label in labels["labels"]:
        assert label["edge_signature_id"] == f"EDGE_SIG_{label['feature_id']}_BOUNDARY"


def test_face_labels_default_to_empty_labels() -> None:
    labels = build_face_labels("sample_000001", mesh_policy())

    assert labels == {
        "schema": "CDF_FACE_LABELS_SM_V1",
        "sample_id": "sample_000001",
        "labels": [],
    }


def test_manifest_controls_flatten_into_feature_labels() -> None:
    labels = build_feature_labels("sample_000001", build_valid_manifest())
    by_id = {label["feature_id"]: label for label in labels["labels"]}

    washer_hole = by_id["HOLE_BOLT_0001"]
    assert washer_hole["action"] == "KEEP_WITH_WASHER"
    assert washer_hole["edge_target_length_mm"] > 0
    assert washer_hole["circumferential_divisions"] >= 24
    assert washer_hole["washer_rings"] == 2
    assert washer_hole["washer_outer_radius_mm"] > 0

    slot = by_id["SLOT_MOUNT_0001"]
    assert slot["edge_target_length_mm"] > 0
    assert slot["end_arc_divisions"] >= 12
    assert slot["straight_edge_divisions"] >= 2

    cutout = by_id["CUTOUT_PASSAGE_0001"]
    assert cutout["edge_target_length_mm"] > 0
    assert cutout["perimeter_growth_rate"] > 1

    bend = by_id["BEND_STRUCTURAL_0001"]
    assert bend["bend_rows"] >= 2
    assert bend["bend_target_length_mm"] > 0

    flange = by_id["FLANGE_STRUCTURAL_0001"]
    assert flange["flange_target_length_mm"] > 0
    assert flange["min_elements_across_width"] >= 2


def test_suppress_feature_disables_edge_preservation_and_capture() -> None:
    manifest = copy.deepcopy(build_valid_manifest())
    feature = manifest["features"][0]
    feature["action"] = "SUPPRESS"
    feature["controls"] = {"suppression_rule": "small_relief_or_drain"}

    labels = build_edge_labels("sample_000001", manifest)
    suppress_label = next(label for label in labels["labels"] if label["feature_id"] == feature["feature_id"])

    assert suppress_label["preserve_edge"] is False
    assert suppress_label["boundary_capture"] is False
    assert "target_length_mm" not in suppress_label
    assert "number_of_divisions" not in suppress_label


def test_build_aux_labels_and_write_aux_labels_to_workspace_local_temp() -> None:
    aux_labels = build_aux_labels("sample_000001", build_valid_manifest(), mesh_policy())
    labels_dir = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_aux_label_writer" / "labels"

    write_aux_labels(labels_dir, aux_labels)

    for filename, schema in {
        "face_labels.json": "CDF_FACE_LABELS_SM_V1",
        "edge_labels.json": "CDF_EDGE_LABELS_SM_V1",
        "feature_labels.json": "CDF_FEATURE_LABELS_SM_V1",
    }.items():
        written = json.loads((labels_dir / filename).read_text(encoding="utf-8"))
        assert written["schema"] == schema
        assert written["sample_id"] == "sample_000001"


def test_non_valid_manifest_raises_aux_label_build_error() -> None:
    manifest = build_valid_manifest()
    manifest["status"] = "OUT_OF_SCOPE"

    with pytest.raises(AuxLabelBuildError) as exc_info:
        build_feature_labels("sample_000001", manifest)
    assert exc_info.value.code == "invalid_manifest_status"


def test_duplicate_feature_id_raises_aux_label_build_error() -> None:
    manifest = build_valid_manifest()
    manifest["features"].append(copy.deepcopy(manifest["features"][0]))

    with pytest.raises(AuxLabelBuildError) as exc_info:
        build_edge_labels("sample_000001", manifest)
    assert exc_info.value.code == "duplicate_feature_id"
    assert exc_info.value.feature_id == "HOLE_BOLT_0001"


def test_non_scalar_control_raises_aux_label_build_error() -> None:
    manifest = build_valid_manifest()
    manifest["features"][0]["controls"]["bad_nested_control"] = {"not": "flat"}

    with pytest.raises(AuxLabelBuildError) as exc_info:
        build_feature_labels("sample_000001", manifest)
    assert exc_info.value.code == "non_scalar_control"
    assert exc_info.value.feature_id == "HOLE_BOLT_0001"
