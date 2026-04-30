from __future__ import annotations

from pathlib import Path

from cae_mesh_common.graph.hetero_graph import HeteroGraph, save_graph


def export_graph(graph: HeteroGraph, output_path: Path | str) -> Path:
    return save_graph(graph, output_path)
