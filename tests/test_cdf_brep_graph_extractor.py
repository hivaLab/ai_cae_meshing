from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf import brep
from cad_dataset_factory.cdf.brep import (
    BrepGraphBuildError,
    extract_brep_graph,
    validate_brep_graph_structure,
    write_brep_graph,
    write_graph_schema,
)
from cad_dataset_factory.cdf.cadgen import FlatPanelFeatureSpec, FlatPanelSpec, build_flat_panel_part, write_flat_panel_outputs

ROOT = Path(__file__).resolve().parents[1]


def _write_smoke_step() -> Path:
    pytest.importorskip("cadquery")
    sample_root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_brep_graph_extractor" / "samples" / "sample_000301"
    generated = build_flat_panel_part(
        FlatPanelSpec(
            sample_id="sample_000301",
            part_name="SMT_SM_FLAT_PANEL_T120_P000301",
            width_mm=100.0,
            height_mm=64.0,
            thickness_mm=1.2,
            features=[
                FlatPanelFeatureSpec(
                    feature_id="HOLE_BOLT_0001",
                    type="HOLE",
                    role="BOLT",
                    center_uv_mm=(40.0, 32.0),
                    radius_mm=5.0,
                )
            ],
        )
    )
    paths = write_flat_panel_outputs(sample_root, generated)
    return Path(paths["input_step"])


def test_extract_brep_graph_returns_nonempty_topology() -> None:
    graph = extract_brep_graph(_write_smoke_step())

    assert graph.arrays["part_features"].shape == (1, 7)
    assert graph.arrays["face_features"].shape[0] > 0
    assert graph.arrays["edge_features"].shape[0] > 0
    assert graph.arrays["vertex_features"].shape[0] > 0
    assert graph.arrays["coedge_features"].shape[0] > 0
    assert graph.arrays["feature_candidate_features"].shape[1] == len(graph.graph_schema["feature_candidate_columns"])


def test_write_graph_schema_validates_contract_and_has_no_target_leakage() -> None:
    graph = extract_brep_graph(_write_smoke_step())
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_brep_graph_extractor" / "graph" / "graph_schema.json"

    write_graph_schema(path, graph)

    written = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "AMG_BREP_GRAPH_SM_V1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(written)
    serialized = json.dumps(written)
    for forbidden in ("target_action_id", "target_edge_length_mm", "circumferential_divisions", "washer_rings", "bend_rows"):
        assert forbidden not in serialized


def test_write_brep_graph_creates_required_npz_arrays() -> None:
    graph = extract_brep_graph(_write_smoke_step())
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_brep_graph_extractor" / "graph" / "brep_graph.npz"

    write_brep_graph(path, graph)

    assert path.is_file()
    with np.load(path) as loaded:
        for key in (
            "node_type_ids",
            "part_features",
            "face_features",
            "edge_features",
            "coedge_features",
            "vertex_features",
            "feature_candidate_features",
            "adj_PART_HAS_FACE",
            "adj_FACE_HAS_COEDGE",
            "adj_COEDGE_HAS_EDGE",
            "adj_EDGE_HAS_VERTEX",
            "coedge_next",
            "coedge_prev",
            "coedge_mate",
        ):
            assert key in loaded.files
        assert loaded["node_type_ids"].dtype.kind in {"i", "u"}
        assert loaded["adj_FACE_HAS_COEDGE"].shape[1] == 2
        assert loaded["adj_FACE_HAS_COEDGE"].dtype.kind in {"i", "u"}


def test_coedge_next_prev_and_mate_are_structurally_consistent() -> None:
    graph = extract_brep_graph(_write_smoke_step())

    validate_brep_graph_structure(graph)
    next_pairs = {tuple(pair) for pair in graph.adjacency["COEDGE_NEXT"].tolist()}
    prev_pairs = {tuple(pair) for pair in graph.adjacency["COEDGE_PREV"].tolist()}
    assert next_pairs
    for source, target in next_pairs:
        assert (target, source) in prev_pairs

    mate_pairs = {tuple(pair) for pair in graph.adjacency["COEDGE_MATE"].tolist()}
    for source, target in mate_pairs:
        assert (target, source) in mate_pairs


def test_cadquery_unavailable_raises_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_cadquery() -> None:
        raise BrepGraphBuildError("cadquery_unavailable", "missing")

    monkeypatch.setattr(brep.graph_extractor, "_load_cadquery", missing_cadquery)

    with pytest.raises(BrepGraphBuildError) as exc_info:
        extract_brep_graph(ROOT / "does_not_matter.step")
    assert exc_info.value.code == "cadquery_unavailable"


def test_missing_step_raises_structured_error() -> None:
    with pytest.raises(BrepGraphBuildError) as exc_info:
        extract_brep_graph(ROOT / "runs" / "pytest_tmp_local" / "missing.step")
    assert exc_info.value.code == "step_not_found"
