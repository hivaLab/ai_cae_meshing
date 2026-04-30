from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HeteroGraph:
    sample_id: str
    node_sets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    edge_sets: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    graph_features: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "node_sets": self.node_sets,
            "edge_sets": {key: [list(edge) for edge in edges] for key, edges in self.edge_sets.items()},
            "graph_features": self.graph_features,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HeteroGraph":
        return cls(
            sample_id=payload["sample_id"],
            node_sets=payload.get("node_sets", {}),
            edge_sets={key: [tuple(edge) for edge in edges] for key, edges in payload.get("edge_sets", {}).items()},
            graph_features=payload.get("graph_features", {}),
        )


def save_graph(graph: HeteroGraph, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_graph(path: Path | str) -> HeteroGraph:
    return HeteroGraph.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
