"""Entity-native B-rep graph contract for AMG v2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cad_dataset_factory.cdf.brep.graph_extractor import (
    COEDGE_FEATURE_COLUMNS,
    EDGE_FEATURE_COLUMNS,
    FACE_FEATURE_COLUMNS,
    PART_FEATURE_COLUMNS,
    VERTEX_FEATURE_COLUMNS,
    BrepGraph,
    BrepGraphBuildError,
    extract_brep_graph,
    validate_brep_graph_structure,
)

SCHEMA_VERSION = "AMG_BREP_ENTITY_GRAPH_SM_V2"
NODE_TYPES = ["PART", "FACE", "EDGE", "COEDGE", "VERTEX"]
EDGE_TYPES = [
    "PART_HAS_FACE",
    "FACE_HAS_COEDGE",
    "COEDGE_HAS_EDGE",
    "EDGE_HAS_VERTEX",
    "COEDGE_NEXT",
    "COEDGE_PREV",
    "COEDGE_MATE",
    "FACE_ADJACENT_FACE",
]


@dataclass(frozen=True)
class EntityBrepGraph:
    graph_schema: dict[str, Any]
    arrays: dict[str, np.ndarray]
    adjacency: dict[str, np.ndarray]
    entity_signatures: dict[str, list[dict[str, Any]]]


def entity_graph_schema_document() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "node_types": NODE_TYPES,
        "edge_types": EDGE_TYPES,
        "part_feature_columns": PART_FEATURE_COLUMNS,
        "face_feature_columns": FACE_FEATURE_COLUMNS,
        "edge_feature_columns": EDGE_FEATURE_COLUMNS,
        "coedge_feature_columns": COEDGE_FEATURE_COLUMNS,
        "vertex_feature_columns": VERTEX_FEATURE_COLUMNS,
    }


def _hash_row(row: np.ndarray) -> str:
    rounded = np.round(np.asarray(row, dtype=np.float64), decimals=6)
    digest = hashlib.sha1(rounded.tobytes()).hexdigest()
    return digest[:10].upper()


def _signature_records(prefix: str, rows: np.ndarray) -> list[dict[str, Any]]:
    return [
        {
            "index": int(index),
            "signature_id": f"{prefix}_SIG_{index + 1:06d}_{_hash_row(row)}",
        }
        for index, row in enumerate(rows)
    ]


def from_legacy_brep_graph(graph: BrepGraph) -> EntityBrepGraph:
    """Convert the existing structural graph into the entity-native v2 graph."""

    validate_brep_graph_structure(graph)
    arrays = {
        key: np.array(graph.arrays[key], copy=True)
        for key in ("node_type_ids", "part_features", "face_features", "edge_features", "coedge_features", "vertex_features")
    }
    adjacency = {edge_type: np.array(graph.adjacency[edge_type], copy=True) for edge_type in EDGE_TYPES}
    entity = EntityBrepGraph(
        graph_schema=entity_graph_schema_document(),
        arrays=arrays,
        adjacency=adjacency,
        entity_signatures={
            "faces": _signature_records("FACE", arrays["face_features"]),
            "edges": _signature_records("EDGE", arrays["edge_features"]),
        },
    )
    validate_entity_brep_graph_structure(entity)
    return entity


def extract_entity_brep_graph(step_path: str | Path) -> EntityBrepGraph:
    return from_legacy_brep_graph(extract_brep_graph(step_path))


def validate_entity_brep_graph_structure(graph: EntityBrepGraph) -> None:
    schema = graph.graph_schema
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise BrepGraphBuildError("invalid_entity_graph_schema", f"schema_version must be {SCHEMA_VERSION}")
    for key in ("part_features", "face_features", "edge_features", "coedge_features", "vertex_features"):
        if key not in graph.arrays:
            raise BrepGraphBuildError("missing_graph_array", f"missing array {key}")
        if graph.arrays[key].ndim != 2:
            raise BrepGraphBuildError("invalid_graph_array", f"{key} must be a 2D array")
    if graph.arrays["part_features"].shape[0] != 1:
        raise BrepGraphBuildError("invalid_part_features", "part_features must have exactly one row")
    for edge_type in EDGE_TYPES:
        if edge_type not in graph.adjacency:
            raise BrepGraphBuildError("missing_adjacency_array", f"missing adjacency for {edge_type}")
        adjacency = graph.adjacency[edge_type]
        if adjacency.ndim != 2 or adjacency.shape[1] != 2 or not np.issubdtype(adjacency.dtype, np.integer):
            raise BrepGraphBuildError("invalid_adjacency_array", f"{edge_type} must be an integer Nx2 array")
    if len(graph.entity_signatures.get("faces", [])) != graph.arrays["face_features"].shape[0]:
        raise BrepGraphBuildError("invalid_face_signatures", "face signature count must match face rows")
    if len(graph.entity_signatures.get("edges", [])) != graph.arrays["edge_features"].shape[0]:
        raise BrepGraphBuildError("invalid_edge_signatures", "edge signature count must match edge rows")


def write_entity_graph_schema(path: str | Path, graph: EntityBrepGraph | None = None) -> None:
    schema = graph.graph_schema if graph is not None else entity_graph_schema_document()
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_entity_signatures(path: str | Path, graph: EntityBrepGraph) -> None:
    validate_entity_brep_graph_structure(graph)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph.entity_signatures, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_entity_brep_graph(path: str | Path, graph: EntityBrepGraph) -> None:
    validate_entity_brep_graph_structure(graph)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(graph.arrays)
    payload.update({f"adj_{edge_type}": adjacency for edge_type, adjacency in graph.adjacency.items()})
    np.savez(output_path, **payload)
