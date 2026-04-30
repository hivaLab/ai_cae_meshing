from __future__ import annotations

from pathlib import Path

import torch

from cae_mesh_common.graph.hetero_graph import load_graph
from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.graph.brep_graph_builder import build_brep_graph
from cae_dataset_factory.graph.pyg_exporter import export_graph


def test_graph_builder_saves_and_loads(tmp_path: Path):
    assembly = AssemblyGrammar(123).generate(0)
    graph = build_brep_graph(assembly)
    path = export_graph(graph, tmp_path / "graph.pt")
    loaded = load_graph(path)
    brep_json = load_graph(tmp_path / "brep_graph.json")
    assembly_json = load_graph(tmp_path / "assembly_graph.json")
    payload = torch.load(path, map_location="cpu", weights_only=False)

    assert path.exists()
    assert (tmp_path / "brep_graph.json").exists()
    assert (tmp_path / "assembly_graph.json").exists()
    assert payload["format"] == "cae_hetero_graph_v1"
    assert set(payload["node_features"]) == {"part", "face", "edge", "contact_candidate", "connection"}
    assert payload["node_features"]["part"].ndim == 2
    assert payload["node_features"]["face"].shape[0] == 72
    assert payload["node_features"]["edge"].shape[0] == 144
    assert payload["edge_index"]["face__incident_to__edge"].shape[0] == 2
    assert payload["edge_index"]["face__shares_edge__face"].shape[1] > 0
    assert loaded.node_sets["part"]
    assert loaded.node_sets["face"]
    assert loaded.node_sets["edge"]
    assert loaded.node_sets["contact_candidate"]
    assert loaded.node_sets["connection"]
    assert loaded.edge_sets["part__has_face__face"]
    assert loaded.edge_sets["face__incident_to__edge"]
    assert loaded.edge_sets["part__near__part"]
    assert brep_json.node_sets["face"]
    assert set(assembly_json.node_sets) == {"part", "contact_candidate", "connection"}
    assert "face" not in assembly_json.node_sets


def test_graph_builder_rejects_missing_brep_topology():
    assembly = AssemblyGrammar(123).generate(0)
    assembly["parts"][0]["face_signatures"] = []
    try:
        build_brep_graph(assembly)
    except ValueError as exc:
        assert "missing B-Rep box faces" in str(exc)
    else:
        raise AssertionError("missing B-Rep topology should fail explicitly")
