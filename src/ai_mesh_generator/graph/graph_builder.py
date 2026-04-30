from __future__ import annotations

from pathlib import Path

from cae_mesh_common.graph.hetero_graph import HeteroGraph, save_graph
from cae_dataset_factory.graph.brep_graph_builder import build_brep_graph


def build_amg_graph(assembly: dict) -> HeteroGraph:
    return build_brep_graph(assembly)


def build_and_save_graph(assembly: dict, output_dir: Path | str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return save_graph(build_amg_graph(assembly), output_dir / "input_graph.pt")
