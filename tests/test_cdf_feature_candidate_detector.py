from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.brep import (
    DetectedFeatureCandidate,
    FeatureCandidateDetectionError,
    attach_feature_candidates,
    detect_feature_candidates,
    extract_brep_graph,
    extract_brep_graph_with_candidates,
    write_brep_graph,
    write_graph_schema,
)
from cad_dataset_factory.cdf.cadgen import (
    BentPartSpec,
    FlatPanelFeatureSpec,
    FlatPanelSpec,
    build_bent_part,
    build_flat_panel_part,
    write_bent_part_outputs,
    write_flat_panel_outputs,
)
from cad_dataset_factory.cdf.domain import PartClass

ROOT = Path(__file__).resolve().parents[1]


def _flat_panel_step() -> Path:
    pytest.importorskip("cadquery")
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_feature_candidate_detector" / "samples" / "sample_000302"
    generated = build_flat_panel_part(
        FlatPanelSpec(
            sample_id="sample_000302",
            part_name="SMT_SM_FLAT_PANEL_T120_P000302",
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
    paths = write_flat_panel_outputs(sample_root, generated)
    return Path(paths["input_step"])


def _bent_part_step() -> Path:
    pytest.importorskip("cadquery")
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_feature_candidate_detector" / "samples" / "sample_000303"
    generated = build_bent_part(
        BentPartSpec(
            sample_id="sample_000303",
            part_name="SMT_SM_L_BRACKET_T120_P000303",
            part_class=PartClass.SM_L_BRACKET,
            length_mm=80.0,
            web_width_mm=36.0,
            flange_width_mm=24.0,
            thickness_mm=1.2,
            inner_radius_mm=1.2,
        )
    )
    paths = write_bent_part_outputs(sample_root, generated)
    return Path(paths["input_step"])


def _metadata_by_id(graph) -> dict[str, dict]:
    return {item["candidate_id"]: item for item in graph.candidate_metadata}


def test_flat_panel_candidate_detection_finds_hole_slot_and_cutout() -> None:
    graph = extract_brep_graph_with_candidates(_flat_panel_step())
    metadata = list(graph.candidate_metadata)
    types = {item["type"] for item in metadata}

    assert {"HOLE", "SLOT", "CUTOUT"} <= types
    assert "BEND" not in types
    assert "FLANGE" not in types
    assert graph.arrays["feature_candidate_features"].shape[0] == len(metadata)
    assert graph.arrays["feature_candidate_ids"].shape[0] == len(metadata)


def test_candidate_ids_and_signatures_are_deterministic() -> None:
    first = extract_brep_graph_with_candidates(_flat_panel_step())
    second = extract_brep_graph_with_candidates(_flat_panel_step())

    first_pairs = [(item["candidate_id"], item["geometry_signature"]) for item in first.candidate_metadata]
    second_pairs = [(item["candidate_id"], item["geometry_signature"]) for item in second.candidate_metadata]
    assert first_pairs == second_pairs


def test_candidate_adjacency_arrays_are_integer_pairs() -> None:
    graph = extract_brep_graph_with_candidates(_flat_panel_step())

    for edge_type in ("FEATURE_CONTAINS_FACE", "FEATURE_CONTAINS_EDGE"):
        adjacency = graph.adjacency[edge_type]
        assert adjacency.ndim == 2
        assert adjacency.shape[1] == 2
        assert adjacency.dtype.kind in {"i", "u"}
        assert adjacency.shape[0] > 0


def test_bent_part_detection_finds_bend_and_flange_candidates() -> None:
    graph = extract_brep_graph_with_candidates(_bent_part_step())
    types = {item["type"] for item in graph.candidate_metadata}

    assert "BEND" in types
    assert "FLANGE" in types


def test_write_brep_graph_includes_candidate_arrays() -> None:
    graph = extract_brep_graph_with_candidates(_flat_panel_step())
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_feature_candidate_detector" / "graph" / "brep_graph.npz"

    write_brep_graph(path, graph)

    with np.load(path) as loaded:
        assert "feature_candidate_features" in loaded.files
        assert "feature_candidate_ids" in loaded.files
        assert "feature_candidate_metadata_json" in loaded.files
        assert "adj_FEATURE_CONTAINS_FACE" in loaded.files
        assert "adj_FEATURE_CONTAINS_EDGE" in loaded.files
        assert loaded["feature_candidate_features"].shape[0] == len(graph.candidate_metadata)
        assert loaded["feature_candidate_ids"].shape[0] == len(graph.candidate_metadata)


def test_graph_schema_remains_contract_valid_and_target_leakage_free() -> None:
    graph = extract_brep_graph_with_candidates(_flat_panel_step())
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_feature_candidate_detector" / "graph" / "graph_schema.json"

    write_graph_schema(path, graph)

    written = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "AMG_BREP_GRAPH_SM_V1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(written)
    serialized = json.dumps(written)
    for forbidden in ("target_action_id", "target_edge_length_mm", "circumferential_divisions", "washer_rings", "bend_rows"):
        assert forbidden not in serialized


def test_invalid_candidate_attachment_raises_structured_error() -> None:
    graph = extract_brep_graph(_flat_panel_step())
    bad_candidate = DetectedFeatureCandidate(
        candidate_id="DETECTED_HOLE_0001",
        type="HOLE",
        role="UNKNOWN",
        geometry_signature="bad",
        center_mm=(0.0, 0.0, 0.0),
        size_1_mm=1.0,
        size_2_mm=1.0,
        face_node_ids=(999_999,),
    )

    with pytest.raises(FeatureCandidateDetectionError) as exc_info:
        attach_feature_candidates(graph, [bad_candidate])
    assert exc_info.value.code == "invalid_candidate_face"


def test_malformed_graph_raises_structured_error() -> None:
    graph = extract_brep_graph(_flat_panel_step())
    malformed = graph.__class__(
        graph_schema=graph.graph_schema,
        arrays={key: value for key, value in graph.arrays.items() if key != "edge_features"},
        adjacency=graph.adjacency,
    )

    with pytest.raises(FeatureCandidateDetectionError) as exc_info:
        detect_feature_candidates(malformed)
    assert exc_info.value.code == "malformed_graph"
