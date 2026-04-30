from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch


@dataclass
class HeteroGraph:
    sample_id: str
    node_sets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    edge_sets: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    node_features: dict[str, list[list[float]]] = field(default_factory=dict)
    node_feature_names: dict[str, list[str]] = field(default_factory=dict)
    graph_features: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "node_sets": self.node_sets,
            "edge_sets": {key: [list(edge) for edge in edges] for key, edges in self.edge_sets.items()},
            "node_features": self.node_features,
            "node_feature_names": self.node_feature_names,
            "graph_features": self.graph_features,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HeteroGraph":
        return cls(
            sample_id=payload["sample_id"],
            node_sets=payload.get("node_sets", {}),
            edge_sets={key: [tuple(edge) for edge in edges] for key, edges in payload.get("edge_sets", {}).items()},
            node_features=payload.get("node_features", {}),
            node_feature_names=payload.get("node_feature_names", {}),
            graph_features=payload.get("graph_features", {}),
            metadata=payload.get("metadata", {}),
        )

    def to_torch_dict(self) -> dict[str, Any]:
        return {
            "format": "cae_hetero_graph_v1",
            "sample_id": self.sample_id,
            "node_sets": self.node_sets,
            "node_feature_names": self.node_feature_names,
            "node_features": {
                node_type: _node_feature_tensor(values, self.node_feature_names.get(node_type, []))
                for node_type, values in self.node_features.items()
            },
            "edge_index": {
                edge_type: _edge_index_tensor(edges)
                for edge_type, edges in self.edge_sets.items()
            },
            "graph_features": {
                key: float(value)
                for key, value in self.graph_features.items()
            },
            "metadata": self.metadata,
        }

    @classmethod
    def from_torch_dict(cls, payload: dict[str, Any]) -> "HeteroGraph":
        if payload.get("format") != "cae_hetero_graph_v1":
            raise ValueError(f"unsupported graph artifact format: {payload.get('format')}")
        edge_sets: dict[str, list[tuple[int, int]]] = {}
        for edge_type, edge_index in payload.get("edge_index", {}).items():
            tensor = torch.as_tensor(edge_index, dtype=torch.long)
            if tensor.numel() == 0:
                edge_sets[edge_type] = []
            else:
                if tensor.ndim != 2 or tensor.shape[0] != 2:
                    raise ValueError(f"edge_index for {edge_type} must have shape [2, num_edges]")
                edge_sets[edge_type] = [tuple(map(int, edge)) for edge in tensor.t().tolist()]
        return cls(
            sample_id=str(payload["sample_id"]),
            node_sets=payload.get("node_sets", {}),
            edge_sets=edge_sets,
            node_features={
                node_type: torch.as_tensor(values, dtype=torch.float32).tolist()
                for node_type, values in payload.get("node_features", {}).items()
            },
            node_feature_names=payload.get("node_feature_names", {}),
            graph_features={
                key: float(value)
                for key, value in payload.get("graph_features", {}).items()
            },
            metadata=payload.get("metadata", {}),
        )


def save_graph(graph: HeteroGraph, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".pt":
        torch.save(graph.to_torch_dict(), path)
    else:
        path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_graph(path: Path | str) -> HeteroGraph:
    path = Path(path)
    if path.suffix == ".pt":
        payload = torch.load(path, map_location="cpu", weights_only=False)
        if not isinstance(payload, dict):
            raise ValueError(f"graph artifact must contain a dict payload: {path}")
        return HeteroGraph.from_torch_dict(payload)
    return HeteroGraph.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _edge_index_tensor(edges: list[tuple[int, int]]) -> torch.Tensor:
    if not edges:
        return torch.empty((2, 0), dtype=torch.long)
    return torch.as_tensor(edges, dtype=torch.long).t().contiguous()


def _node_feature_tensor(values: list[list[float]], feature_names: list[str]) -> torch.Tensor:
    if not values:
        return torch.empty((0, len(feature_names)), dtype=torch.float32)
    return torch.as_tensor(values, dtype=torch.float32)
