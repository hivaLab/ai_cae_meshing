"""Deterministic feature candidate detection for CDF B-rep graphs."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cad_dataset_factory.cdf.brep.graph_extractor import (
    EDGE_TYPES,
    FEATURE_CANDIDATE_COLUMNS,
    NODE_TYPES,
    BrepGraph,
    extract_brep_graph,
    validate_brep_graph_structure,
)

FEATURE_TYPE_IDS = {"HOLE": 1, "SLOT": 2, "CUTOUT": 3, "BEND": 4, "FLANGE": 5}
ROLE_IDS = {"UNKNOWN": 0, "STRUCTURAL": 7}
ACTION_MASKS = {
    "HOLE": 0b00111,
    "SLOT": 0b00101,
    "CUTOUT": 0b00101,
    "BEND": 0b01000,
    "FLANGE": 0b10000,
}

_LINE = 1
_CIRCLE = 2
_ARC = 3
_ROUND_TYPES = {_CIRCLE, _ARC}


class FeatureCandidateDetectionError(ValueError):
    """Raised when feature candidate detection cannot proceed safely."""

    def __init__(self, code: str, message: str, candidate_id: str | None = None) -> None:
        self.code = code
        self.candidate_id = candidate_id
        prefix = code if candidate_id is None else f"{code} [{candidate_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class DetectedFeatureCandidate:
    candidate_id: str
    type: str
    role: str
    geometry_signature: str
    center_mm: tuple[float, float, float]
    size_1_mm: float
    size_2_mm: float
    radius_mm: float | None = None
    width_mm: float | None = None
    length_mm: float | None = None
    distance_to_outer_boundary_mm: float = 0.0
    distance_to_nearest_feature_mm: float = 0.0
    clearance_ratio: float = 0.0
    face_node_ids: tuple[int, ...] = ()
    edge_node_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class _GraphOffsets:
    face_offset: int
    edge_offset: int
    coedge_offset: int
    vertex_offset: int
    feature_offset: int


@dataclass
class _CandidateDraft:
    type: str
    role: str
    geometry_signature: str
    center_mm: tuple[float, float, float]
    size_1_mm: float
    size_2_mm: float
    radius_mm: float | None = None
    width_mm: float | None = None
    length_mm: float | None = None
    distance_to_outer_boundary_mm: float = 0.0
    face_node_ids: set[int] | None = None
    edge_node_ids: set[int] | None = None


def _offsets(graph: BrepGraph) -> _GraphOffsets:
    face_count = graph.arrays["face_features"].shape[0]
    edge_count = graph.arrays["edge_features"].shape[0]
    coedge_count = graph.arrays["coedge_features"].shape[0]
    vertex_count = graph.arrays["vertex_features"].shape[0]
    face_offset = 1
    edge_offset = face_offset + face_count
    coedge_offset = edge_offset + edge_count
    vertex_offset = coedge_offset + coedge_count
    feature_offset = vertex_offset + vertex_count
    return _GraphOffsets(face_offset, edge_offset, coedge_offset, vertex_offset, feature_offset)


def _require_graph_arrays(graph: BrepGraph) -> None:
    try:
        validate_brep_graph_structure(graph)
    except Exception as exc:
        raise FeatureCandidateDetectionError("malformed_graph", str(exc)) from exc
    for key in ("part_features", "face_features", "edge_features", "coedge_features"):
        if key not in graph.arrays:
            raise FeatureCandidateDetectionError("malformed_graph", f"missing {key}")
    if graph.arrays["part_features"].shape != (1, 7):
        raise FeatureCandidateDetectionError("malformed_graph", "part_features must have shape (1, 7)")


def _node_id_for_face(offsets: _GraphOffsets, face_index: int) -> int:
    return offsets.face_offset + face_index


def _node_id_for_edge(offsets: _GraphOffsets, edge_index: int) -> int:
    return offsets.edge_offset + edge_index


def _face_index_from_node(offsets: _GraphOffsets, graph: BrepGraph, face_node_id: int) -> int:
    face_index = face_node_id - offsets.face_offset
    if face_index < 0 or face_index >= graph.arrays["face_features"].shape[0]:
        raise FeatureCandidateDetectionError("malformed_graph", "face adjacency references an invalid face node")
    return face_index


def _edge_bounds(edge_rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    centers = edge_rows[:, 5:8]
    half_extents = edge_rows[:, 2:5] / 2.0
    mins = np.min(centers - half_extents, axis=0)
    maxs = np.max(centers + half_extents, axis=0)
    dims = maxs - mins
    center = (mins + maxs) / 2.0
    return mins, maxs, dims, center


def _planar_axes(dims: np.ndarray) -> tuple[int, int]:
    axes = sorted(range(3), key=lambda axis: float(dims[axis]), reverse=True)
    return (axes[0], axes[1])


def _loop_signature(feature_type: str, center: np.ndarray, dims: np.ndarray, axes: tuple[int, int]) -> str:
    size_1, size_2 = sorted((float(dims[axes[0]]), float(dims[axes[1]])), reverse=True)
    c1 = round(float(center[axes[0]]), 3)
    c2 = round(float(center[axes[1]]), 3)
    return f"{feature_type}:{c1:.3f}:{c2:.3f}:{size_1:.3f}:{size_2:.3f}"


def _boundary_distance(center: np.ndarray, dims: np.ndarray, axes: tuple[int, int], part_bbox: np.ndarray) -> float:
    distances: list[float] = []
    for axis in axes:
        half = float(dims[axis]) / 2.0
        distances.append(max(0.0, float(center[axis]) - half))
        distances.append(max(0.0, float(part_bbox[axis]) - float(center[axis]) - half))
    return min(distances) if distances else 0.0


def _draft_from_loop(
    *,
    graph: BrepGraph,
    offsets: _GraphOffsets,
    face_index: int,
    edge_indices: tuple[int, ...],
    part_bbox: np.ndarray,
) -> _CandidateDraft | None:
    edge_rows = graph.arrays["edge_features"][list(edge_indices)]
    curve_types = [int(value) for value in edge_rows[:, 0].tolist()]
    line_count = sum(1 for curve_type in curve_types if curve_type == _LINE)
    round_count = sum(1 for curve_type in curve_types if curve_type in _ROUND_TYPES)
    mins, maxs, dims, center = _edge_bounds(edge_rows)
    _ = mins, maxs
    axes = _planar_axes(dims)
    size_1, size_2 = sorted((float(dims[axes[0]]), float(dims[axes[1]])), reverse=True)
    if size_1 <= 0.0 or size_2 <= 0.0:
        return None

    feature_type: str | None = None
    radius_mm: float | None = None
    width_mm: float | None = None
    length_mm: float | None = None
    aspect = size_1 / size_2 if size_2 else math.inf

    if round_count >= 1 and line_count == 0 and aspect <= 1.15:
        feature_type = "HOLE"
        radius_mm = (size_1 + size_2) / 4.0
        width_mm = 2.0 * radius_mm
        length_mm = 2.0 * radius_mm
        size_1 = 2.0 * radius_mm
        size_2 = 2.0 * radius_mm
    elif line_count == 2 and round_count == 2 and aspect > 1.2:
        feature_type = "SLOT"
        width_mm = size_2
        length_mm = size_1
        radius_mm = width_mm / 2.0
    elif line_count >= 4 and round_count == 0:
        feature_type = "CUTOUT"
        width_mm = size_1
        length_mm = size_2

    if feature_type is None:
        return None

    edge_node_ids = {_node_id_for_edge(offsets, edge_index) for edge_index in edge_indices}
    return _CandidateDraft(
        type=feature_type,
        role="UNKNOWN",
        geometry_signature=_loop_signature(feature_type, center, dims, axes),
        center_mm=(float(center[0]), float(center[1]), float(center[2])),
        size_1_mm=size_1,
        size_2_mm=size_2,
        radius_mm=radius_mm,
        width_mm=width_mm,
        length_mm=length_mm,
        distance_to_outer_boundary_mm=_boundary_distance(center, dims, axes, part_bbox),
        face_node_ids={_node_id_for_face(offsets, face_index)},
        edge_node_ids=edge_node_ids,
    )


def _merge_draft(target: dict[str, _CandidateDraft], draft: _CandidateDraft) -> None:
    existing = target.get(draft.geometry_signature)
    if existing is None:
        target[draft.geometry_signature] = draft
        return
    if existing.face_node_ids is None:
        existing.face_node_ids = set()
    if existing.edge_node_ids is None:
        existing.edge_node_ids = set()
    existing.face_node_ids.update(draft.face_node_ids or set())
    existing.edge_node_ids.update(draft.edge_node_ids or set())


def _detect_inner_loop_candidates(graph: BrepGraph, offsets: _GraphOffsets) -> list[DetectedFeatureCandidate]:
    part_bbox = graph.arrays["part_features"][0, 4:7]
    coedge_rows = graph.arrays["coedge_features"]
    by_face_wire: dict[tuple[int, int], list[int]] = {}
    for row in coedge_rows:
        face_index = int(row[0])
        edge_index = int(row[1])
        wire_index = int(row[2])
        if wire_index <= 0:
            continue
        by_face_wire.setdefault((face_index, wire_index), []).append(edge_index)

    drafts: dict[str, _CandidateDraft] = {}
    for (face_index, _wire_index), edge_indices in sorted(by_face_wire.items()):
        draft = _draft_from_loop(
            graph=graph,
            offsets=offsets,
            face_index=face_index,
            edge_indices=tuple(edge_indices),
            part_bbox=part_bbox,
        )
        if draft is not None:
            _merge_draft(drafts, draft)
    return _finalize_drafts(drafts.values())


def _face_edge_indices(graph: BrepGraph) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for row in graph.arrays["coedge_features"]:
        result.setdefault(int(row[0]), set()).add(int(row[1]))
    return result


def _normal_angle_degrees(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = float(np.dot(left, right) / (left_norm * right_norm))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _estimated_thickness(face_rows: np.ndarray) -> float:
    positive_dims = [
        float(value)
        for value in face_rows[:, 1:4].reshape(-1).tolist()
        if float(value) > 1e-6
    ]
    return min(positive_dims) if positive_dims else 0.0


def _sheet_width(face_row: np.ndarray) -> float:
    positive_dims = sorted((float(value) for value in face_row[1:4].tolist() if float(value) > 1e-6), reverse=True)
    if len(positive_dims) < 2:
        return 0.0
    return positive_dims[1]


def _is_long_extruded_face(face_row: np.ndarray, part_bbox: np.ndarray, thickness_mm: float) -> bool:
    min_width = max(4.0 * thickness_mm, 0.05 * max(float(part_bbox[1]), float(part_bbox[2]), 1.0))
    return float(face_row[1]) >= 0.5 * float(part_bbox[0]) and _sheet_width(face_row) >= min_width and float(face_row[0]) > 0.0


def _bend_area_score(draft: _CandidateDraft, face_rows: np.ndarray, offsets: _GraphOffsets) -> float:
    return sum(float(face_rows[face_node_id - offsets.face_offset, 0]) for face_node_id in draft.face_node_ids or set())


def _dedupe_bend_drafts(
    drafts: list[_CandidateDraft],
    *,
    face_rows: np.ndarray,
    offsets: _GraphOffsets,
    thickness_mm: float,
) -> list[_CandidateDraft]:
    if not drafts:
        return []
    clustered: list[list[_CandidateDraft]] = []
    for draft in sorted(drafts, key=lambda item: item.geometry_signature):
        center = np.asarray(draft.center_mm, dtype=np.float64)
        for cluster in clustered:
            reference = np.asarray(cluster[0].center_mm, dtype=np.float64)
            same_shape = math.isclose(draft.size_1_mm, cluster[0].size_1_mm, rel_tol=0.02, abs_tol=0.5) and math.isclose(
                draft.size_2_mm,
                cluster[0].size_2_mm,
                rel_tol=0.02,
                abs_tol=0.5,
            )
            if same_shape and float(np.linalg.norm(center - reference)) <= max(2.0 * thickness_mm, 0.5):
                cluster.append(draft)
                break
        else:
            clustered.append([draft])

    return [
        max(cluster, key=lambda draft: (_bend_area_score(draft, face_rows, offsets), draft.geometry_signature))
        for cluster in clustered
    ]


def _detect_bend_and_flange_candidates(graph: BrepGraph, offsets: _GraphOffsets) -> list[DetectedFeatureCandidate]:
    part_bbox = graph.arrays["part_features"][0, 4:7]
    face_rows = graph.arrays["face_features"]
    edge_rows = graph.arrays["edge_features"]
    face_edges = _face_edge_indices(graph)
    thickness_mm = _estimated_thickness(face_rows)
    bend_drafts: list[_CandidateDraft] = []
    seen_pairs: set[tuple[int, int]] = set()

    for left_node, right_node in graph.adjacency["FACE_ADJACENT_FACE"].tolist():
        left_face = _face_index_from_node(offsets, graph, int(left_node))
        right_face = _face_index_from_node(offsets, graph, int(right_node))
        pair = tuple(sorted((left_face, right_face)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        left_row = face_rows[left_face]
        right_row = face_rows[right_face]
        if not (_is_long_extruded_face(left_row, part_bbox, thickness_mm) and _is_long_extruded_face(right_row, part_bbox, thickness_mm)):
            continue
        angle = _normal_angle_degrees(left_row[7:10], right_row[7:10])
        if angle < 45.0 or angle > 120.0:
            continue
        shared_edges = sorted(face_edges.get(left_face, set()) & face_edges.get(right_face, set()))
        if not shared_edges:
            continue
        shared_lengths = [float(edge_rows[edge_index, 1]) for edge_index in shared_edges]
        if max(shared_lengths) < 0.5 * max(float(part_bbox[0]), 1.0):
            continue
        center = (left_row[4:7] + right_row[4:7]) / 2.0
        edge_node_ids = {_node_id_for_edge(offsets, edge_index) for edge_index in shared_edges}
        face_node_ids = {_node_id_for_face(offsets, left_face), _node_id_for_face(offsets, right_face)}
        signature = f"BEND:{min(pair)}:{max(pair)}:{round(max(shared_lengths), 3):.3f}:{round(angle, 3):.3f}"
        bend_drafts.append(
            _CandidateDraft(
                type="BEND",
                role="STRUCTURAL",
                geometry_signature=signature,
                center_mm=(float(center[0]), float(center[1]), float(center[2])),
                size_1_mm=max(shared_lengths),
                size_2_mm=angle,
                length_mm=max(shared_lengths),
                face_node_ids=face_node_ids,
                edge_node_ids=edge_node_ids,
            )
        )

    bend_drafts = _dedupe_bend_drafts(
        bend_drafts,
        face_rows=face_rows,
        offsets=offsets,
        thickness_mm=thickness_mm,
    )
    flange_drafts: dict[int, _CandidateDraft] = {}
    for bend in bend_drafts:
        face_nodes = sorted(bend.face_node_ids or set())
        if not face_nodes:
            continue
        candidate_face_node = min(
            face_nodes,
            key=lambda node_id: (float(face_rows[_face_index_from_node(offsets, graph, node_id), 0]), node_id),
        )
        if candidate_face_node in flange_drafts:
            continue
        face_index = _face_index_from_node(offsets, graph, candidate_face_node)
        face_row = face_rows[face_index]
        dims = sorted((float(face_row[1]), float(face_row[2]), float(face_row[3])), reverse=True)
        length_mm = dims[0]
        width_mm = dims[1] if len(dims) > 1 else 0.0
        signature = f"FLANGE:{candidate_face_node}:{round(length_mm, 3):.3f}:{round(width_mm, 3):.3f}"
        flange_drafts[candidate_face_node] = _CandidateDraft(
            type="FLANGE",
            role="STRUCTURAL",
            geometry_signature=signature,
            center_mm=(float(face_row[4]), float(face_row[5]), float(face_row[6])),
            size_1_mm=length_mm,
            size_2_mm=width_mm,
            width_mm=width_mm,
            length_mm=length_mm,
            face_node_ids={candidate_face_node},
            edge_node_ids={_node_id_for_edge(offsets, edge_index) for edge_index in face_edges.get(face_index, set())},
        )

    return _finalize_drafts([*bend_drafts, *flange_drafts.values()])


def _finalize_drafts(drafts: Any) -> list[DetectedFeatureCandidate]:
    ordered = sorted(
        drafts,
        key=lambda draft: (
            FEATURE_TYPE_IDS[draft.type],
            round(draft.center_mm[0], 6),
            round(draft.center_mm[1], 6),
            round(draft.center_mm[2], 6),
            draft.geometry_signature,
        ),
    )
    counters = {feature_type: 0 for feature_type in FEATURE_TYPE_IDS}
    result: list[DetectedFeatureCandidate] = []
    for draft in ordered:
        counters[draft.type] += 1
        candidate_id = f"DETECTED_{draft.type}_{counters[draft.type]:04d}"
        result.append(
            DetectedFeatureCandidate(
                candidate_id=candidate_id,
                type=draft.type,
                role=draft.role,
                geometry_signature=draft.geometry_signature,
                center_mm=draft.center_mm,
                size_1_mm=draft.size_1_mm,
                size_2_mm=draft.size_2_mm,
                radius_mm=draft.radius_mm,
                width_mm=draft.width_mm,
                length_mm=draft.length_mm,
                distance_to_outer_boundary_mm=draft.distance_to_outer_boundary_mm,
                face_node_ids=tuple(sorted(draft.face_node_ids or set())),
                edge_node_ids=tuple(sorted(draft.edge_node_ids or set())),
            )
        )
    return result


def detect_feature_candidates(graph: BrepGraph) -> list[DetectedFeatureCandidate]:
    """Detect deterministic feature candidates from a structural B-rep graph."""

    _require_graph_arrays(graph)
    offsets = _offsets(graph)
    loop_candidates = _detect_inner_loop_candidates(graph, offsets)
    if loop_candidates:
        return loop_candidates
    return _detect_bend_and_flange_candidates(graph, offsets)


def _candidate_row(candidate: DetectedFeatureCandidate, lref: float) -> list[float]:
    feature_type_id = FEATURE_TYPE_IDS.get(candidate.type)
    if feature_type_id is None:
        raise FeatureCandidateDetectionError("unsupported_feature_type", "candidate type is not canonical", candidate.candidate_id)
    if candidate.role not in ROLE_IDS:
        raise FeatureCandidateDetectionError("unsupported_feature_role", "candidate role is not supported", candidate.candidate_id)
    if candidate.size_1_mm <= 0.0:
        raise FeatureCandidateDetectionError("invalid_candidate_size", "candidate size_1_mm must be positive", candidate.candidate_id)
    return [
        float(feature_type_id),
        float(ROLE_IDS[candidate.role]),
        candidate.size_1_mm / lref,
        max(candidate.size_2_mm, 0.0) / lref,
        (candidate.radius_mm or 0.0) / lref,
        (candidate.width_mm or 0.0) / lref,
        (candidate.length_mm or 0.0) / lref,
        candidate.center_mm[0] / lref,
        candidate.center_mm[1] / lref,
        candidate.center_mm[2] / lref,
        max(candidate.distance_to_outer_boundary_mm, 0.0) / lref,
        max(candidate.distance_to_nearest_feature_mm, 0.0) / lref,
        max(candidate.clearance_ratio, 0.0),
        float(ACTION_MASKS[candidate.type]),
    ]


def _string_array(values: list[str]) -> np.ndarray:
    width = max([1, *[len(value) for value in values]])
    return np.asarray(values, dtype=f"<U{width}")


def _candidate_metadata(candidate: DetectedFeatureCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "type": candidate.type,
        "role": candidate.role,
        "geometry_signature": candidate.geometry_signature,
        "center_mm": list(candidate.center_mm),
        "size_1_mm": candidate.size_1_mm,
        "size_2_mm": candidate.size_2_mm,
        "radius_mm": candidate.radius_mm,
        "width_mm": candidate.width_mm,
        "length_mm": candidate.length_mm,
        "face_node_ids": list(candidate.face_node_ids),
        "edge_node_ids": list(candidate.edge_node_ids),
    }


def attach_feature_candidates(graph: BrepGraph, candidates: list[DetectedFeatureCandidate]) -> BrepGraph:
    """Return a graph copy with FEATURE_CANDIDATE rows and containment edges attached."""

    _require_graph_arrays(graph)
    if graph.arrays["feature_candidate_features"].shape[0] != 0:
        raise FeatureCandidateDetectionError("feature_candidates_already_attached", "graph already has feature candidates")
    seen_ids: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_id in seen_ids:
            raise FeatureCandidateDetectionError("duplicate_candidate_id", "candidate ids must be unique", candidate.candidate_id)
        seen_ids.add(candidate.candidate_id)

    part_bbox = graph.arrays["part_features"][0, 4:7]
    lref = float(np.max(part_bbox))
    if lref <= 0.0:
        raise FeatureCandidateDetectionError("invalid_reference_length", "part bounding box must be positive")

    offsets = _offsets(graph)
    base_node_count = int(graph.arrays["node_type_ids"].shape[0])
    feature_type_id = NODE_TYPES.index("FEATURE_CANDIDATE")
    rows = [_candidate_row(candidate, lref) for candidate in candidates]
    candidate_nodes = [base_node_count + index for index, _candidate in enumerate(candidates)]

    face_count = graph.arrays["face_features"].shape[0]
    edge_count = graph.arrays["edge_features"].shape[0]
    face_min = offsets.face_offset
    face_max = offsets.face_offset + face_count
    edge_min = offsets.edge_offset
    edge_max = offsets.edge_offset + edge_count
    contains_face: list[tuple[int, int]] = []
    contains_edge: list[tuple[int, int]] = []
    for candidate_node, candidate in zip(candidate_nodes, candidates, strict=True):
        for face_node_id in candidate.face_node_ids:
            if face_node_id < face_min or face_node_id >= face_max:
                raise FeatureCandidateDetectionError("invalid_candidate_face", "candidate references an invalid face", candidate.candidate_id)
            contains_face.append((candidate_node, face_node_id))
        for edge_node_id in candidate.edge_node_ids:
            if edge_node_id < edge_min or edge_node_id >= edge_max:
                raise FeatureCandidateDetectionError("invalid_candidate_edge", "candidate references an invalid edge", candidate.candidate_id)
            contains_edge.append((candidate_node, edge_node_id))

    arrays = {key: np.array(value, copy=True) for key, value in graph.arrays.items()}
    arrays["node_type_ids"] = np.concatenate(
        [
            arrays["node_type_ids"],
            np.full(len(candidates), feature_type_id, dtype=np.int64),
        ]
    )
    arrays["feature_candidate_features"] = (
        np.asarray(rows, dtype=np.float64)
        if rows
        else np.empty((0, len(FEATURE_CANDIDATE_COLUMNS)), dtype=np.float64)
    )
    arrays["feature_candidate_ids"] = _string_array([candidate.candidate_id for candidate in candidates])
    metadata = tuple(_candidate_metadata(candidate) for candidate in candidates)
    arrays["feature_candidate_metadata_json"] = _string_array(
        [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in metadata]
    )

    adjacency = {edge_type: np.array(graph.adjacency[edge_type], copy=True) for edge_type in EDGE_TYPES}
    adjacency["FEATURE_CONTAINS_FACE"] = (
        np.asarray(sorted(set(contains_face)), dtype=np.int64) if contains_face else np.empty((0, 2), dtype=np.int64)
    )
    adjacency["FEATURE_CONTAINS_EDGE"] = (
        np.asarray(sorted(set(contains_edge)), dtype=np.int64) if contains_edge else np.empty((0, 2), dtype=np.int64)
    )

    attached = BrepGraph(
        graph_schema=dict(graph.graph_schema),
        arrays=arrays,
        adjacency=adjacency,
        candidate_metadata=metadata,
    )
    validate_brep_graph_structure(attached)
    return attached


def extract_brep_graph_with_candidates(step_path: str | Path) -> BrepGraph:
    """Extract a B-rep graph and attach deterministic feature candidates."""

    graph = extract_brep_graph(step_path)
    return attach_feature_candidates(graph, detect_feature_candidates(graph))
