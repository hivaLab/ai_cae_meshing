"""Extract a structural AMG B-rep graph from STEP files."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = "AMG_BREP_GRAPH_SM_V1"
NODE_TYPES = ["PART", "FACE", "EDGE", "COEDGE", "VERTEX", "FEATURE_CANDIDATE"]
EDGE_TYPES = [
    "PART_HAS_FACE",
    "FACE_HAS_COEDGE",
    "COEDGE_HAS_EDGE",
    "EDGE_HAS_VERTEX",
    "COEDGE_NEXT",
    "COEDGE_PREV",
    "COEDGE_MATE",
    "FACE_ADJACENT_FACE",
    "FEATURE_CONTAINS_FACE",
    "FEATURE_CONTAINS_EDGE",
]
FEATURE_CANDIDATE_COLUMNS = [
    "feature_type_id",
    "role_id",
    "size_1_over_Lref",
    "size_2_over_Lref",
    "radius_over_Lref",
    "width_over_Lref",
    "length_over_Lref",
    "center_x_over_Lref",
    "center_y_over_Lref",
    "center_z_over_Lref",
    "distance_to_outer_boundary_over_Lref",
    "distance_to_nearest_feature_over_Lref",
    "clearance_ratio",
    "expected_action_mask",
]

PART_FEATURE_COLUMNS = ["num_faces", "num_edges", "num_vertices", "num_coedges", "bbox_x", "bbox_y", "bbox_z"]
FACE_FEATURE_COLUMNS = ["area", "bbox_x", "bbox_y", "bbox_z", "center_x", "center_y", "center_z", "normal_x", "normal_y", "normal_z", "num_edges", "num_wires"]
EDGE_FEATURE_COLUMNS = ["curve_type_id", "length", "bbox_x", "bbox_y", "bbox_z", "center_x", "center_y", "center_z", "num_vertices"]
COEDGE_FEATURE_COLUMNS = ["parent_face_index", "parent_edge_index", "wire_index"]
VERTEX_FEATURE_COLUMNS = ["x", "y", "z"]

_CURVE_TYPE_IDS = {"LINE": 1, "CIRCLE": 2, "ARC": 3, "ELLIPSE": 4, "BSPLINE": 5}


class BrepGraphBuildError(ValueError):
    """Raised when a B-rep graph cannot be extracted or written safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class BrepGraph:
    graph_schema: dict[str, Any]
    arrays: dict[str, np.ndarray]
    adjacency: dict[str, np.ndarray]


def _load_cadquery() -> Any:
    try:
        import cadquery as cq
    except ModuleNotFoundError as exc:
        raise BrepGraphBuildError(
            "cadquery_unavailable",
            "CadQuery is required for STEP B-rep graph extraction; install the cad optional dependency",
        ) from exc
    return cq


def graph_schema_document() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "node_types": NODE_TYPES,
        "edge_types": EDGE_TYPES,
        "feature_candidate_columns": FEATURE_CANDIDATE_COLUMNS,
    }


def _vector_tuple(vector: Any) -> tuple[float, float, float]:
    return (float(vector.x), float(vector.y), float(vector.z))


def _bbox_tuple(shape: Any) -> tuple[float, float, float]:
    bbox = shape.BoundingBox()
    return (float(bbox.xlen), float(bbox.ylen), float(bbox.zlen))


def _shape_center(shape: Any) -> tuple[float, float, float]:
    try:
        return _vector_tuple(shape.Center())
    except Exception:
        return (0.0, 0.0, 0.0)


def _face_normal(face: Any) -> tuple[float, float, float]:
    try:
        return _vector_tuple(face.normalAt())
    except Exception:
        return (0.0, 0.0, 0.0)


def _edge_curve_type_id(edge: Any) -> int:
    try:
        return _CURVE_TYPE_IDS.get(str(edge.geomType()).upper(), 0)
    except Exception:
        return 0


def _array(rows: list[list[float]], width: int, *, dtype: Any = np.float64) -> np.ndarray:
    if rows:
        return np.asarray(rows, dtype=dtype)
    return np.empty((0, width), dtype=dtype)


def _adjacency(rows: list[tuple[int, int]]) -> np.ndarray:
    if rows:
        return np.asarray(rows, dtype=np.int64)
    return np.empty((0, 2), dtype=np.int64)


def _import_step(path: str | Path) -> Any:
    cq = _load_cadquery()
    step_path = Path(path)
    if not step_path.is_file():
        raise BrepGraphBuildError("step_not_found", f"STEP file does not exist: {step_path}")
    try:
        return cq.importers.importStep(str(step_path)).val()
    except Exception as exc:
        raise BrepGraphBuildError("step_import_failed", f"failed to import STEP file: {step_path}") from exc


def extract_brep_graph(step_path: str | Path) -> BrepGraph:
    """Extract a structural AMG_BREP_GRAPH_SM_V1 graph from a STEP file."""

    shape = _import_step(step_path)
    faces = list(shape.Faces())
    edges = list(shape.Edges())
    vertices = list(shape.Vertices())
    if not faces or not edges or not vertices:
        raise BrepGraphBuildError("empty_brep_topology", "STEP topology must contain faces, edges, and vertices")

    face_offset = 1
    edge_offset = face_offset + len(faces)
    coedge_offset = edge_offset + len(edges)
    edge_index_by_hash = {edge.hashCode(): index for index, edge in enumerate(edges)}
    vertex_index_by_hash = {vertex.hashCode(): index for index, vertex in enumerate(vertices)}

    coedge_rows: list[list[float]] = []
    coedge_edge_indices: list[int] = []
    coedge_face_indices: list[int] = []
    wire_cycles: list[list[int]] = []
    coedges_by_edge: dict[int, list[int]] = {}

    adj_part_has_face: list[tuple[int, int]] = []
    adj_face_has_coedge: list[tuple[int, int]] = []
    adj_coedge_has_edge: list[tuple[int, int]] = []
    adj_edge_has_vertex: list[tuple[int, int]] = []
    adj_next: list[tuple[int, int]] = []
    adj_prev: list[tuple[int, int]] = []
    adj_mate: list[tuple[int, int]] = []
    adj_face_adjacent: set[tuple[int, int]] = set()

    for face_index, face in enumerate(faces):
        face_node = face_offset + face_index
        adj_part_has_face.append((0, face_node))
        for wire_index, wire in enumerate(face.Wires()):
            cycle: list[int] = []
            for wire_edge in wire.Edges():
                edge_index = edge_index_by_hash[wire_edge.hashCode()]
                coedge_index = len(coedge_rows)
                coedge_node = coedge_offset + coedge_index
                edge_node = edge_offset + edge_index
                coedge_rows.append([float(face_index), float(edge_index), float(wire_index)])
                coedge_edge_indices.append(edge_index)
                coedge_face_indices.append(face_index)
                coedges_by_edge.setdefault(edge_index, []).append(coedge_index)
                cycle.append(coedge_index)
                adj_face_has_coedge.append((face_node, coedge_node))
                adj_coedge_has_edge.append((coedge_node, edge_node))
            if cycle:
                wire_cycles.append(cycle)

    vertex_offset = coedge_offset + len(coedge_rows)
    feature_offset = vertex_offset + len(vertices)
    _ = feature_offset

    for edge_index, edge in enumerate(edges):
        edge_node = edge_offset + edge_index
        for vertex in edge.Vertices():
            vertex_index = vertex_index_by_hash[vertex.hashCode()]
            adj_edge_has_vertex.append((edge_node, vertex_offset + vertex_index))

    for cycle in wire_cycles:
        count = len(cycle)
        for index, coedge_index in enumerate(cycle):
            current = coedge_offset + coedge_index
            next_node = coedge_offset + cycle[(index + 1) % count]
            prev_node = coedge_offset + cycle[(index - 1) % count]
            adj_next.append((current, next_node))
            adj_prev.append((current, prev_node))

    for coedge_indices in coedges_by_edge.values():
        if len(coedge_indices) < 2:
            continue
        for index, coedge_index in enumerate(coedge_indices):
            mate_index = coedge_indices[(index + 1) % len(coedge_indices)]
            if mate_index == coedge_index:
                continue
            adj_mate.append((coedge_offset + coedge_index, coedge_offset + mate_index))
        face_indices = sorted({coedge_face_indices[index] for index in coedge_indices})
        for left in face_indices:
            for right in face_indices:
                if left != right:
                    adj_face_adjacent.add((face_offset + left, face_offset + right))

    bbox = shape.BoundingBox()
    part_features = np.asarray(
        [[float(len(faces)), float(len(edges)), float(len(vertices)), float(len(coedge_rows)), float(bbox.xlen), float(bbox.ylen), float(bbox.zlen)]],
        dtype=np.float64,
    )
    face_features = _array(
        [
            [
                float(face.Area()),
                *_bbox_tuple(face),
                *_shape_center(face),
                *_face_normal(face),
                float(len(face.Edges())),
                float(len(face.Wires())),
            ]
            for face in faces
        ],
        len(FACE_FEATURE_COLUMNS),
    )
    edge_features = _array(
        [
            [
                float(_edge_curve_type_id(edge)),
                float(edge.Length()),
                *_bbox_tuple(edge),
                *_shape_center(edge),
                float(len(edge.Vertices())),
            ]
            for edge in edges
        ],
        len(EDGE_FEATURE_COLUMNS),
    )
    vertex_features = _array([list(_shape_center(vertex)) for vertex in vertices], len(VERTEX_FEATURE_COLUMNS))
    coedge_features = _array(coedge_rows, len(COEDGE_FEATURE_COLUMNS))
    feature_candidate_features = np.empty((0, len(FEATURE_CANDIDATE_COLUMNS)), dtype=np.float64)
    node_type_ids = np.concatenate(
        [
            np.full(1, NODE_TYPES.index("PART"), dtype=np.int64),
            np.full(len(faces), NODE_TYPES.index("FACE"), dtype=np.int64),
            np.full(len(edges), NODE_TYPES.index("EDGE"), dtype=np.int64),
            np.full(len(coedge_rows), NODE_TYPES.index("COEDGE"), dtype=np.int64),
            np.full(len(vertices), NODE_TYPES.index("VERTEX"), dtype=np.int64),
        ]
    )

    adjacency = {
        "PART_HAS_FACE": _adjacency(adj_part_has_face),
        "FACE_HAS_COEDGE": _adjacency(adj_face_has_coedge),
        "COEDGE_HAS_EDGE": _adjacency(adj_coedge_has_edge),
        "EDGE_HAS_VERTEX": _adjacency(adj_edge_has_vertex),
        "COEDGE_NEXT": _adjacency(adj_next),
        "COEDGE_PREV": _adjacency(adj_prev),
        "COEDGE_MATE": _adjacency(adj_mate),
        "FACE_ADJACENT_FACE": _adjacency(sorted(adj_face_adjacent)),
        "FEATURE_CONTAINS_FACE": _adjacency([]),
        "FEATURE_CONTAINS_EDGE": _adjacency([]),
    }
    arrays = {
        "node_type_ids": node_type_ids,
        "part_features": part_features,
        "face_features": face_features,
        "edge_features": edge_features,
        "coedge_features": coedge_features,
        "vertex_features": vertex_features,
        "feature_candidate_features": feature_candidate_features,
        "coedge_next": adjacency["COEDGE_NEXT"],
        "coedge_prev": adjacency["COEDGE_PREV"],
        "coedge_mate": adjacency["COEDGE_MATE"],
    }
    graph = BrepGraph(graph_schema=graph_schema_document(), arrays=arrays, adjacency=adjacency)
    validate_brep_graph_structure(graph)
    return graph


def validate_brep_graph_structure(graph: BrepGraph) -> None:
    """Validate structural array and coedge invariants for a B-rep graph."""

    for key in ("node_type_ids", "part_features", "face_features", "edge_features", "coedge_features", "vertex_features", "feature_candidate_features"):
        if key not in graph.arrays:
            raise BrepGraphBuildError("missing_graph_array", f"missing array {key}")
    for edge_type in EDGE_TYPES:
        if edge_type not in graph.adjacency:
            raise BrepGraphBuildError("missing_adjacency_array", f"missing adjacency for {edge_type}")
        adjacency = graph.adjacency[edge_type]
        if adjacency.ndim != 2 or adjacency.shape[1] != 2 or not np.issubdtype(adjacency.dtype, np.integer):
            raise BrepGraphBuildError("invalid_adjacency_array", f"{edge_type} must be an integer Nx2 array")

    next_pairs = {tuple(pair) for pair in graph.adjacency["COEDGE_NEXT"].tolist()}
    prev_pairs = {tuple(pair) for pair in graph.adjacency["COEDGE_PREV"].tolist()}
    for source, target in next_pairs:
        if (target, source) not in prev_pairs:
            raise BrepGraphBuildError("invalid_coedge_cycle", "COEDGE_NEXT and COEDGE_PREV must be reciprocal")

    mate_pairs = {tuple(pair) for pair in graph.adjacency["COEDGE_MATE"].tolist()}
    for source, target in mate_pairs:
        if (target, source) not in mate_pairs:
            raise BrepGraphBuildError("invalid_coedge_mate", "COEDGE_MATE pairs must be reciprocal")


def write_graph_schema(path: str | Path, graph: BrepGraph | None = None) -> None:
    schema = graph.graph_schema if graph is not None else graph_schema_document()
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_brep_graph(path: str | Path, graph: BrepGraph) -> None:
    validate_brep_graph_structure(graph)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(graph.arrays)
    payload.update({f"adj_{edge_type}": adjacency for edge_type, adjacency in graph.adjacency.items()})
    np.savez(output_path, **payload)
