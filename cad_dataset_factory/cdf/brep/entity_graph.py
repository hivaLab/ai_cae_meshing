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

SCHEMA_VERSION = "AMG_BREP_ENTITY_GRAPH_SM_V3"
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


def _stable_hash(document: dict[str, Any]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:12].upper()


def _round_float(value: Any, digits: int = 6) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _round_tuple(values: np.ndarray | list[Any] | tuple[Any, ...], digits: int = 6) -> list[float]:
    return [_round_float(value, digits) for value in list(values)]


def _node_offsets(arrays: dict[str, np.ndarray]) -> dict[str, int]:
    face_offset = 1
    edge_offset = face_offset + int(arrays["face_features"].shape[0])
    coedge_offset = edge_offset + int(arrays["edge_features"].shape[0])
    vertex_offset = coedge_offset + int(arrays["coedge_features"].shape[0])
    return {"face": face_offset, "edge": edge_offset, "coedge": coedge_offset, "vertex": vertex_offset}


def _edge_vertex_indices(edge_index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> list[int]:
    offsets = _node_offsets(arrays)
    edge_node = offsets["edge"] + edge_index
    vertices = [
        int(target - offsets["vertex"])
        for source, target in adjacency["EDGE_HAS_VERTEX"].tolist()
        if int(source) == edge_node and 0 <= int(target - offsets["vertex"]) < arrays["vertex_features"].shape[0]
    ]
    return sorted(set(vertices))


def _edge_coedge_indices(edge_index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> list[int]:
    offsets = _node_offsets(arrays)
    edge_node = offsets["edge"] + edge_index
    coedges = [
        int(source - offsets["coedge"])
        for source, target in adjacency["COEDGE_HAS_EDGE"].tolist()
        if int(target) == edge_node and 0 <= int(source - offsets["coedge"]) < arrays["coedge_features"].shape[0]
    ]
    return sorted(set(coedges))


def _edge_adjacent_faces(edge_index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> list[int]:
    coedges = _edge_coedge_indices(edge_index, arrays, adjacency)
    faces = [int(round(float(arrays["coedge_features"][coedge, 0]))) for coedge in coedges]
    return sorted(set(face for face in faces if 0 <= face < arrays["face_features"].shape[0]))


def _face_edge_indices(face_index: int, arrays: dict[str, np.ndarray]) -> list[int]:
    rows = arrays["coedge_features"]
    return sorted(
        set(
            int(round(float(row[1])))
            for row in rows
            if int(round(float(row[0]))) == face_index and 0 <= int(round(float(row[1]))) < arrays["edge_features"].shape[0]
        )
    )


def _face_adjacent_faces(face_index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> list[int]:
    offsets = _node_offsets(arrays)
    face_node = offsets["face"] + face_index
    adjacent = [
        int(target - offsets["face"])
        for source, target in adjacency["FACE_ADJACENT_FACE"].tolist()
        if int(source) == face_node and 0 <= int(target - offsets["face"]) < arrays["face_features"].shape[0]
    ]
    return sorted(set(adjacent))


def _loop_role(edge_index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> str:
    coedges = _edge_coedge_indices(edge_index, arrays, adjacency)
    faces = _edge_adjacent_faces(edge_index, arrays, adjacency)
    if len(coedges) <= 1 or len(faces) <= 1:
        return "FREE_OR_OUTER_BOUNDARY"
    return "SHARED_FACE_BOUNDARY"


def _edge_fingerprint(index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> dict[str, Any]:
    row = arrays["edge_features"][index]
    vertices = _edge_vertex_indices(index, arrays, adjacency)
    vertex_points = [_round_tuple(arrays["vertex_features"][vertex]) for vertex in vertices]
    return {
        "entity_type": "EDGE",
        "curve_type_id": int(round(float(row[0]))),
        "length_mm": _round_float(row[1]),
        "bbox_mm": _round_tuple(row[2:5]),
        "center_mm": _round_tuple(row[5:8]),
        "vertex_points_mm": vertex_points,
        "adjacent_face_indices": _edge_adjacent_faces(index, arrays, adjacency),
        "coedge_count": len(_edge_coedge_indices(index, arrays, adjacency)),
        "loop_role": _loop_role(index, arrays, adjacency),
    }


def _face_fingerprint(index: int, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> dict[str, Any]:
    row = arrays["face_features"][index]
    edge_indices = _face_edge_indices(index, arrays)
    edge_rows = arrays["edge_features"]
    adjacent_edge_descriptors = [
        {
            "edge_index": int(edge_index),
            "curve_type_id": int(round(float(edge_rows[edge_index, 0]))),
            "length_mm": _round_float(edge_rows[edge_index, 1]),
            "center_mm": _round_tuple(edge_rows[edge_index, 5:8]),
        }
        for edge_index in edge_indices
    ]
    return {
        "entity_type": "FACE",
        "area_mm2": _round_float(row[0]),
        "bbox_mm": _round_tuple(row[1:4]),
        "center_mm": _round_tuple(row[4:7]),
        "normal": _round_tuple(row[7:10]),
        "edge_indices": edge_indices,
        "loop_count": int(round(float(row[11]))) if row.shape[0] > 11 else 0,
        "adjacent_face_indices": _face_adjacent_faces(index, arrays, adjacency),
        "adjacent_edge_descriptors": adjacent_edge_descriptors,
    }


def _signature_records(prefix: str, arrays: dict[str, np.ndarray], adjacency: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rows = arrays["edge_features"] if prefix == "EDGE" else arrays["face_features"]
    records: list[dict[str, Any]] = []
    for index in range(rows.shape[0]):
        fingerprint = _edge_fingerprint(index, arrays, adjacency) if prefix == "EDGE" else _face_fingerprint(index, arrays, adjacency)
        fingerprint_hash = _stable_hash(fingerprint)
        records.append(
            {
                "index": int(index),
                "signature_id": f"{prefix}_SIG_{index + 1:06d}_{fingerprint_hash}",
                "entity_type": prefix,
                "fingerprint": fingerprint,
            }
        )
    return records


def from_structural_brep_graph(graph: BrepGraph) -> EntityBrepGraph:
    """Convert the structural graph extractor output into the entity-native v2 graph."""

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
            "faces": _signature_records("FACE", arrays, adjacency),
            "edges": _signature_records("EDGE", arrays, adjacency),
        },
    )
    validate_entity_brep_graph_structure(entity)
    return entity


def extract_entity_brep_graph(step_path: str | Path) -> EntityBrepGraph:
    return from_structural_brep_graph(extract_brep_graph(step_path))


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
    for collection, required_type in (("faces", "FACE"), ("edges", "EDGE")):
        for record in graph.entity_signatures.get(collection, []):
            if "signature_id" not in record or "fingerprint" not in record:
                raise BrepGraphBuildError("invalid_entity_signature", f"{collection} records require signature_id and fingerprint")
            if record.get("entity_type") != required_type:
                raise BrepGraphBuildError("invalid_entity_signature", f"{collection} record entity_type must be {required_type}")


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
