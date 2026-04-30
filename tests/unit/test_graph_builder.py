from __future__ import annotations

from pathlib import Path

from cae_mesh_common.graph.hetero_graph import load_graph
from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.graph.brep_graph_builder import build_brep_graph
from cae_dataset_factory.graph.pyg_exporter import export_graph


def test_graph_builder_saves_and_loads(tmp_path: Path):
    assembly = AssemblyGrammar(123).generate(0)
    graph = build_brep_graph(assembly)
    path = export_graph(graph, tmp_path / "graph.pt")
    loaded = load_graph(path)
    assert loaded.node_sets["part"]
    assert loaded.node_sets["face"]
    assert loaded.edge_sets["part_to_face"]
