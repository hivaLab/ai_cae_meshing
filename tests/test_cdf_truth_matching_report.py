from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dataset_factory.cdf.brep import DetectedFeatureCandidate, attach_feature_candidates, extract_brep_graph, extract_brep_graph_with_candidates
from cad_dataset_factory.cdf.cadgen import (
    BentPartSpec,
    FlatPanelFeatureSpec,
    FlatPanelSpec,
    build_bent_part,
    build_flat_panel_part,
    write_bent_part_outputs,
    write_flat_panel_outputs,
)
from cad_dataset_factory.cdf.dataset import build_sample_acceptance, write_sample_directory
from cad_dataset_factory.cdf.domain import FeatureTruthDocument, HoleTruth, PartClass, PartParams
from cad_dataset_factory.cdf.labels import build_aux_labels
from cad_dataset_factory.cdf.truth import (
    FeatureMatchingError,
    build_feature_matching_report,
    match_feature_truth_to_candidates,
    write_feature_matching_report,
)
from test_cdf_manifest_writer import build_valid_manifest, entity_signatures, feature_truth, mesh_policy

ROOT = Path(__file__).resolve().parents[1]


def _flat_panel_generated():
    pytest.importorskip("cadquery")
    return build_flat_panel_part(
        FlatPanelSpec(
            sample_id="sample_000303",
            part_name="SMT_SM_FLAT_PANEL_T120_P000303",
            width_mm=140.0,
            height_mm=90.0,
            thickness_mm=1.2,
            features=[
                FlatPanelFeatureSpec(
                    feature_id="HOLE_BOLT_0001",
                    type="HOLE",
                    role="BOLT",
                    center_uv_mm=(30.0, 45.0),
                    radius_mm=5.0,
                ),
                FlatPanelFeatureSpec(
                    feature_id="SLOT_MOUNT_0001",
                    type="SLOT",
                    role="MOUNT",
                    center_uv_mm=(70.0, 45.0),
                    length_mm=22.0,
                    width_mm=8.0,
                ),
                FlatPanelFeatureSpec(
                    feature_id="CUTOUT_PASSAGE_0001",
                    type="CUTOUT",
                    role="PASSAGE",
                    center_uv_mm=(110.0, 45.0),
                    width_mm=16.0,
                    height_mm=12.0,
                ),
            ],
        )
    )


def _flat_panel_graph_and_truth():
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_truth_matching_report" / "samples" / "sample_000303"
    generated = _flat_panel_generated()
    paths = write_flat_panel_outputs(sample_root, generated)
    return extract_brep_graph_with_candidates(paths["input_step"]), generated.feature_truth


def _bent_part_graph_and_truth():
    pytest.importorskip("cadquery")
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_truth_matching_report" / "samples" / "sample_000304"
    generated = build_bent_part(
        BentPartSpec(
            sample_id="sample_000304",
            part_name="SMT_SM_L_BRACKET_T120_P000304",
            part_class=PartClass.SM_L_BRACKET,
            length_mm=80.0,
            web_width_mm=36.0,
            flange_width_mm=24.0,
            thickness_mm=1.2,
            inner_radius_mm=1.2,
        )
    )
    paths = write_bent_part_outputs(sample_root, generated)
    return extract_brep_graph_with_candidates(paths["input_step"]), generated.feature_truth


def test_flat_panel_truth_matching_report_has_full_recall_and_no_false_matches() -> None:
    graph, truth = _flat_panel_graph_and_truth()

    report = build_feature_matching_report(truth.sample_id, truth, graph)

    assert report["schema"] == "CDF_FEATURE_MATCHING_REPORT_SM_V1"
    assert report["accepted"] is True
    assert report["truth_feature_count"] == 3
    assert report["detected_feature_count"] == 3
    assert report["unmatched_truth_features"] == []
    assert report["unmatched_detected_features"] == []
    assert report["false_match_count"] == 0
    assert {match["type"] for match in report["matches"]} == {"HOLE", "SLOT", "CUTOUT"}
    assert all(bucket["recall"] == 1.0 for bucket in report["recall_by_type"].values())


def test_bent_part_truth_matching_report_has_full_recall_and_no_false_matches() -> None:
    graph, truth = _bent_part_graph_and_truth()

    report = build_feature_matching_report(truth.sample_id, truth, graph)

    assert report["accepted"] is True
    assert report["truth_feature_count"] == 2
    assert report["detected_feature_count"] == 2
    assert report["unmatched_truth_features"] == []
    assert report["unmatched_detected_features"] == []
    assert report["false_match_count"] == 0
    assert {match["type"] for match in report["matches"]} == {"BEND", "FLANGE"}


def test_write_feature_matching_report_writes_json_document() -> None:
    graph, truth = _flat_panel_graph_and_truth()
    report = build_feature_matching_report(truth.sample_id, truth, graph)
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_truth_matching_report" / "reports" / "feature_matching_report.json"

    write_feature_matching_report(path, report)

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == report


def test_write_sample_directory_can_include_feature_matching_report() -> None:
    manifest = build_valid_manifest()
    aux_labels = build_aux_labels("sample_000001", manifest, mesh_policy())
    report = {
        "schema": "CDF_FEATURE_MATCHING_REPORT_SM_V1",
        "sample_id": "sample_000001",
        "accepted": True,
        "truth_feature_count": 0,
        "detected_feature_count": 0,
        "unmatched_truth_features": [],
        "unmatched_detected_features": [],
        "matches": [],
        "recall_by_type": {},
        "false_match_count": 0,
    }
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_truth_matching_report" / "samples" / "sample_000001"

    write_sample_directory(
        sample_root,
        feature_truth=feature_truth(),
        entity_signatures=entity_signatures(),
        manifest=manifest,
        aux_labels=aux_labels,
        acceptance=build_sample_acceptance(
            "sample_000001",
            {
                "geometry_validation": True,
                "feature_matching": True,
                "manifest_schema": True,
                "ansa_oracle": True,
            },
        ),
        reports={"feature_matching_report": report},
    )

    assert (sample_root / "reports" / "feature_matching_report.json").is_file()


def test_missing_candidate_metadata_raises_feature_matching_error() -> None:
    pytest.importorskip("cadquery")
    generated = _flat_panel_generated()
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_truth_matching_report" / "samples" / "missing_candidates"
    paths = write_flat_panel_outputs(sample_root, generated)
    graph = extract_brep_graph(paths["input_step"])

    with pytest.raises(FeatureMatchingError) as exc_info:
        build_feature_matching_report(generated.feature_truth.sample_id, generated.feature_truth, graph)
    assert exc_info.value.code == "missing_candidates"


def test_sample_id_mismatch_raises_feature_matching_error() -> None:
    graph, truth = _flat_panel_graph_and_truth()

    with pytest.raises(FeatureMatchingError) as exc_info:
        build_feature_matching_report("sample_wrong", truth, graph)
    assert exc_info.value.code == "sample_id_mismatch"


def test_duplicate_candidate_assignment_raises_feature_matching_error() -> None:
    graph, truth = _flat_panel_graph_and_truth()
    first = truth.features[0]
    duplicate_truth = FeatureTruthDocument(
        sample_id=truth.sample_id,
        part=PartParams(
            part_name=truth.part.part_name,
            part_class=truth.part.part_class,
            thickness_mm=truth.part.thickness_mm,
            width_mm=truth.part.width_mm,
            height_mm=truth.part.height_mm,
        ),
        features=[
            first,
            HoleTruth(
                feature_id="HOLE_BOLT_DUPLICATE",
                role=first.role,
                created_by=first.created_by,
                center_uv_mm=first.center_uv_mm,
                center_mm=first.center_mm,
                axis=first.axis,
                radius_mm=first.radius_mm,
                patch_id=first.patch_id,
                axis_source=first.axis_source,
            ),
        ],
    )

    with pytest.raises(FeatureMatchingError) as exc_info:
        match_feature_truth_to_candidates(duplicate_truth, graph)
    assert exc_info.value.code == "duplicate_candidate_assignment"


def test_malformed_candidate_metadata_raises_feature_matching_error() -> None:
    graph, truth = _flat_panel_graph_and_truth()
    malformed_graph = graph.__class__(
        graph_schema=graph.graph_schema,
        arrays=graph.arrays,
        adjacency=graph.adjacency,
        candidate_metadata=(
            {
                "candidate_id": "DETECTED_BAD_0001",
                "type": "NOT_A_FEATURE",
            },
        ),
    )

    with pytest.raises(FeatureMatchingError) as exc_info:
        build_feature_matching_report(truth.sample_id, truth, malformed_graph)
    assert exc_info.value.code == "malformed_candidates"
