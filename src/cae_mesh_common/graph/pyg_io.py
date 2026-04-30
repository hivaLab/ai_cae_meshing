from __future__ import annotations

from pathlib import Path

from .hetero_graph import HeteroGraph, load_graph, save_graph


def save_hetero_graph(graph: HeteroGraph, path: Path | str) -> Path:
    return save_graph(graph, path)


def load_hetero_graph(path: Path | str) -> HeteroGraph:
    return load_graph(path)
