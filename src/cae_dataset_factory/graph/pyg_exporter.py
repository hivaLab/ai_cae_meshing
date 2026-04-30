from __future__ import annotations

from pathlib import Path

from cae_mesh_common.graph.hetero_graph import HeteroGraph, save_graph


def export_graph(graph: HeteroGraph, output_path: Path | str) -> Path:
    output_path = save_graph(graph, output_path)
    graph_dir = output_path.parent
    save_graph(graph, graph_dir / "brep_graph.json")
    save_graph(_assembly_view(graph), graph_dir / "assembly_graph.json")
    return output_path


def _assembly_view(graph: HeteroGraph) -> HeteroGraph:
    assembly_node_sets = {
        key: graph.node_sets.get(key, [])
        for key in ["part", "contact_candidate", "connection"]
    }
    assembly_node_features = {
        key: graph.node_features.get(key, [])
        for key in assembly_node_sets
    }
    assembly_feature_names = {
        key: graph.node_feature_names.get(key, [])
        for key in assembly_node_sets
    }
    assembly_types = set(assembly_node_sets)
    assembly_edge_sets = {}
    for key, edges in graph.edge_sets.items():
        source_type, _, target_type = key.split("__")
        if source_type in assembly_types and target_type in assembly_types:
            assembly_edge_sets[key] = edges
    return HeteroGraph(
        sample_id=graph.sample_id,
        node_sets=assembly_node_sets,
        edge_sets=assembly_edge_sets,
        node_features=assembly_node_features,
        node_feature_names=assembly_feature_names,
        graph_features=graph.graph_features,
        metadata={**graph.metadata, "graph_view": "assembly"},
    )
