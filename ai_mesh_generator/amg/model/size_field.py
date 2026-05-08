"""Segmentation-aware direct B-rep size-field model for AMG v2."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from ai_mesh_generator.amg.model.part_classifier import PART_CLASS_ORDER
from ai_mesh_generator.amg.model.segmentation import EDGE_SEGMENTATION_CLASSES, FACE_SEGMENTATION_CLASSES


class SizeFieldModelError(ValueError):
    """Raised when a direct size-field model input or projection is malformed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SizeFieldGraphTensors:
    face_inputs: torch.Tensor
    edge_inputs: torch.Tensor
    coedge_features: torch.Tensor


@dataclass(frozen=True)
class SizeFieldTargets:
    edge_log_h: torch.Tensor
    edge_mask: torch.Tensor
    face_log_h: torch.Tensor
    face_mask: torch.Tensor


@dataclass(frozen=True)
class SizeFieldOutput:
    edge_log_h: torch.Tensor
    face_log_h: torch.Tensor
    edge_uncertainty: torch.Tensor
    face_uncertainty: torch.Tensor


def _sample_graph(sample: Any) -> Any:
    return sample.graph if hasattr(sample, "graph") else sample


def _label_map(labels: list[dict[str, Any]], key: str) -> dict[str, str]:
    return {str(item[key]): str(item["semantic_label"]) for item in labels}


def _edge_semantic_map(sample: Any) -> dict[str, str]:
    if not hasattr(sample, "labels"):
        return {}
    return _label_map(list(sample.labels.edge_segmentation.get("labels", [])), "edge_signature_id")


def _face_semantic_map(sample: Any) -> dict[str, str]:
    if not hasattr(sample, "labels"):
        return {}
    return _label_map(list(sample.labels.face_segmentation.get("labels", [])), "face_signature_id")


def _edge_fingerprints(sample: Any) -> dict[str, dict[str, Any]]:
    graph = _sample_graph(sample)
    return {
        str(record["signature_id"]): dict(record.get("fingerprint", {}))
        for record in graph.entity_signatures.get("edges", [])
        if isinstance(record, dict)
    }


def build_size_field_graph_tensors(
    sample: Any,
    *,
    face_segmentation_probabilities: np.ndarray,
    edge_segmentation_probabilities: np.ndarray,
    part_probabilities: np.ndarray,
) -> SizeFieldGraphTensors:
    """Build size-field inputs from AI part and segmentation probabilities.

    Label one-hot shortcuts are intentionally not supported here: primary size-field
    training and inference must see the same model-predicted context.
    """

    graph = _sample_graph(sample)
    arrays = graph.arrays if hasattr(graph, "arrays") else graph["arrays"]
    face_features = np.asarray(arrays["face_features"], dtype=np.float32)
    edge_features = np.asarray(arrays["edge_features"], dtype=np.float32)
    coedge_features = np.asarray(arrays["coedge_features"], dtype=np.float32)
    if face_features.ndim != 2 or edge_features.ndim != 2 or coedge_features.ndim != 2:
        raise SizeFieldModelError("malformed_graph_arrays", "face, edge, and coedge arrays must be 2D")

    face_count = face_features.shape[0]
    edge_count = edge_features.shape[0]
    face_probs = np.asarray(face_segmentation_probabilities, dtype=np.float32)
    edge_probs = np.asarray(edge_segmentation_probabilities, dtype=np.float32)
    part_probs = np.asarray(part_probabilities, dtype=np.float32)

    if face_probs.shape != (face_count, len(FACE_SEGMENTATION_CLASSES)):
        raise SizeFieldModelError("malformed_face_segmentation_probabilities", "face segmentation probabilities have the wrong shape")
    if edge_probs.shape != (edge_count, len(EDGE_SEGMENTATION_CLASSES)):
        raise SizeFieldModelError("malformed_edge_segmentation_probabilities", "edge segmentation probabilities have the wrong shape")
    if part_probs.shape != (len(PART_CLASS_ORDER),):
        raise SizeFieldModelError("malformed_part_probabilities", "part probabilities have the wrong shape")

    face_part = np.repeat(part_probs.reshape(1, -1), face_count, axis=0)
    edge_part = np.repeat(part_probs.reshape(1, -1), edge_count, axis=0)
    return SizeFieldGraphTensors(
        face_inputs=torch.as_tensor(np.concatenate([face_features, face_probs, face_part], axis=1), dtype=torch.float32),
        edge_inputs=torch.as_tensor(np.concatenate([edge_features, edge_probs, edge_part], axis=1), dtype=torch.float32),
        coedge_features=torch.as_tensor(coedge_features, dtype=torch.float32),
    )


def _global_mesh_policy(sample: Any) -> dict[str, Any]:
    mesh = sample.labels.mesh_size_field.get("global_mesh", {}) if hasattr(sample, "labels") else {}
    if not isinstance(mesh, dict):
        raise SizeFieldModelError("missing_global_mesh_policy", "mesh size labels require a global mesh policy")
    return mesh


def _quality_candidate_score(
    row: dict[str, Any],
    global_mesh: dict[str, Any],
    global_summary: dict[str, Any],
    *,
    semantic_label: str | None = None,
    edge_fingerprint: dict[str, Any] | None = None,
) -> float:
    h_min = float(global_mesh.get("h_min_mm", 0.5))
    h0 = float(global_mesh.get("h0_mm", 3.0))
    h_max = float(global_mesh.get("h_max_mm", max(h0, h_min)))
    target = float(row["candidate_target_size_mm"])
    score = 0.0
    if not row.get("metric_available"):
        score += 1_000.0
    if row.get("hard_fail"):
        score += 200.0
    elif row.get("near_fail"):
        score += 40.0
    boundary_error = row.get("measured_boundary_size_error")
    if boundary_error is None:
        score += 2.0
    else:
        boundary = float(boundary_error)
        score += boundary
        score += 20.0 * max(0.0, boundary - 0.50)
        score += 4.0 * max(0.0, boundary - 0.20)
    semantic = semantic_label or str(row.get("semantic_label") or "OTHER")
    edge_fingerprint = edge_fingerprint or {}
    length = float(edge_fingerprint.get("length_mm", 0.0) or 0.0)
    curve_type = int(edge_fingerprint.get("curve_type_id", 0) or 0)
    if semantic in {"HOLE_BOUNDARY", "SLOT_BOUNDARY", "CUTOUT_BOUNDARY"}:
        if semantic == "HOLE_BOUNDARY" and curve_type in {2, 3} and length > 0:
            divisions = length / max(target, 1.0e-9)
            score += 20.0 * max(0.0, 24.0 - divisions) / 24.0
            score += 6.0 * max(0.0, divisions - 48.0) / 48.0
        else:
            score += 8.0 * max(0.0, 0.8 - target) / 0.8
            score += 4.0 * max(0.0, target - 1.5) / max(1.5, 1.0e-9)
    elif semantic in {"OUTER_BOUNDARY", "FREE_EDGE"}:
        if target < h0:
            score += 6.0 * (h0 - target) / max(h0 - h_min, 1.0e-9)
    elif semantic == "BEND_EDGE":
        bbox = edge_fingerprint.get("bbox_mm") if isinstance(edge_fingerprint.get("bbox_mm"), list) else []
        thickness_like = max([abs(float(value)) for value in bbox], default=h_min)
        lower = max(h_min, min(0.5 * h0, max(thickness_like, h_min)))
        if target < lower:
            score += 5.0 * (lower - target) / max(lower - h_min, 1.0e-9)
    elif semantic in {"INTERNAL", "OTHER"}:
        score += 10.0
    if target <= h_min * 1.001:
        score += 3.0
    mesh_stats = global_summary.get("mesh_stats", {}) if isinstance(global_summary, dict) else {}
    shell_count = mesh_stats.get("shell_element_count") if isinstance(mesh_stats, dict) else None
    if isinstance(shell_count, (int, float)) and shell_count > 0:
        score += min(8.0, float(shell_count) / 50_000.0)
    bdf_bytes = mesh_stats.get("bdf_bytes") if isinstance(mesh_stats, dict) else None
    if isinstance(bdf_bytes, (int, float)) and bdf_bytes > 0:
        score += min(4.0, float(bdf_bytes) / 10_000_000.0)
    if target > h_max:
        score += 100.0 * (target - h_max) / max(h_max, 1.0e-9)
    return score


def _quality_preferred_targets(sample: Any) -> tuple[dict[str, float], dict[str, float]]:
    if not hasattr(sample, "labels") or not sample.labels.quality_evaluations:
        raise SizeFieldModelError("missing_quality_evidence", "quality-aware size-field training requires entity quality evaluations")
    global_mesh = _global_mesh_policy(sample)
    edge_semantics = _edge_semantic_map(sample)
    face_semantics = _face_semantic_map(sample)
    edge_fingerprints = _edge_fingerprints(sample)
    edge_candidates: dict[str, tuple[float, float]] = {}
    face_candidates: dict[str, tuple[float, float]] = {}
    for document in sample.labels.quality_evaluations:
        summary = document.get("global_quality_summary", {})
        for row in document.get("entity_quality", []):
            if not isinstance(row, dict):
                continue
            if not row.get("metric_available"):
                continue
            signature_id = str(row.get("entity_signature_id", ""))
            if not signature_id or "candidate_target_size_mm" not in row:
                continue
            score = _quality_candidate_score(
                row,
                global_mesh,
                summary if isinstance(summary, dict) else {},
                semantic_label=edge_semantics.get(signature_id) or face_semantics.get(signature_id) or row.get("semantic_label"),
                edge_fingerprint=edge_fingerprints.get(signature_id),
            )
            target = float(row["candidate_target_size_mm"])
            candidates = edge_candidates if row.get("entity_type") == "EDGE" else face_candidates if row.get("entity_type") == "FACE" else None
            if candidates is None:
                continue
            if signature_id not in candidates or score < candidates[signature_id][0]:
                candidates[signature_id] = (score, target)
    return (
        {signature_id: target for signature_id, (_score, target) in edge_candidates.items()},
        {signature_id: target for signature_id, (_score, target) in face_candidates.items()},
    )


def build_size_field_targets(sample: Any, *, prefer_quality_evidence: bool = False) -> SizeFieldTargets:
    graph = sample.graph
    edge_count = graph.arrays["edge_features"].shape[0]
    face_count = graph.arrays["face_features"].shape[0]
    edge_values = torch.zeros((edge_count,), dtype=torch.float32)
    edge_mask = torch.zeros((edge_count,), dtype=torch.bool)
    face_values = torch.zeros((face_count,), dtype=torch.float32)
    face_mask = torch.zeros((face_count,), dtype=torch.bool)
    edge_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["edges"]}
    face_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["faces"]}
    if prefer_quality_evidence:
        edge_targets, face_targets = _quality_preferred_targets(sample)
        if not edge_targets:
            raise SizeFieldModelError("missing_quality_edge_targets", "quality evidence contains no edge size targets")
        edge_items = [{"edge_signature_id": signature_id, "target_size_mm": target} for signature_id, target in edge_targets.items()]
        face_items = [{"face_signature_id": signature_id, "target_size_mm": target} for signature_id, target in face_targets.items()]
    else:
        edge_items = sample.labels.mesh_size_field["edge_sizes"]
        face_items = sample.labels.mesh_size_field.get("face_sizes", [])
    for item in edge_items:
        index = edge_by_sig.get(item["edge_signature_id"])
        if index is not None:
            edge_values[index] = math.log(float(item["target_size_mm"]))
            edge_mask[index] = True
    for item in face_items:
        index = face_by_sig.get(item["face_signature_id"])
        if index is not None:
            face_values[index] = math.log(float(item["target_size_mm"]))
            face_mask[index] = True
    if not torch.any(edge_mask):
        raise SizeFieldModelError("missing_edge_size_targets", "direct size-field training requires at least one edge target")
    return SizeFieldTargets(edge_log_h=edge_values, edge_mask=edge_mask, face_log_h=face_values, face_mask=face_mask)


class BrepSizeFieldModel(nn.Module):
    """Compact coedge-aware GNN-style regressor for per-edge/per-face size fields."""

    def __init__(self, face_input_dim: int, edge_input_dim: int, hidden_dim: int = 64) -> None:
        super().__init__()
        self.face_encoder = nn.Sequential(nn.Linear(face_input_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim), nn.ReLU())
        self.edge_encoder = nn.Sequential(nn.Linear(edge_input_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim), nn.ReLU())
        self.edge_head = nn.Linear(hidden_dim * 2, 1)
        self.face_head = nn.Linear(hidden_dim * 2, 1)
        self.edge_uncertainty_head = nn.Sequential(nn.Linear(hidden_dim * 2, 1), nn.Softplus())
        self.face_uncertainty_head = nn.Sequential(nn.Linear(hidden_dim * 2, 1), nn.Softplus())

    def forward(self, tensors: SizeFieldGraphTensors) -> SizeFieldOutput:
        face_hidden = self.face_encoder(tensors.face_inputs)
        edge_hidden = self.edge_encoder(tensors.edge_inputs)
        device = face_hidden.device
        coedge = tensors.coedge_features.to(device=device)
        if coedge.ndim != 2 or coedge.shape[1] < 2:
            raise SizeFieldModelError("malformed_coedge_features", "coedge features require parent face and edge columns")
        face_indices = coedge[:, 0].round().to(dtype=torch.long)
        edge_indices = coedge[:, 1].round().to(dtype=torch.long)
        if torch.any(face_indices < 0) or torch.any(face_indices >= face_hidden.shape[0]):
            raise SizeFieldModelError("invalid_coedge_face_index", "coedge parent face index is out of bounds")
        if torch.any(edge_indices < 0) or torch.any(edge_indices >= edge_hidden.shape[0]):
            raise SizeFieldModelError("invalid_coedge_edge_index", "coedge parent edge index is out of bounds")

        face_edge_context = torch.zeros_like(face_hidden)
        face_counts = torch.zeros((face_hidden.shape[0], 1), dtype=face_hidden.dtype, device=device)
        face_edge_context.index_add_(0, face_indices, edge_hidden[edge_indices])
        face_counts.index_add_(0, face_indices, torch.ones((face_indices.shape[0], 1), dtype=face_hidden.dtype, device=device))
        face_edge_context = face_edge_context / face_counts.clamp_min(1.0)

        edge_face_context = torch.zeros_like(edge_hidden)
        edge_counts = torch.zeros((edge_hidden.shape[0], 1), dtype=edge_hidden.dtype, device=device)
        edge_face_context.index_add_(0, edge_indices, face_hidden[face_indices])
        edge_counts.index_add_(0, edge_indices, torch.ones((edge_indices.shape[0], 1), dtype=edge_hidden.dtype, device=device))
        edge_face_context = edge_face_context / edge_counts.clamp_min(1.0)

        edge_state = torch.cat([edge_hidden, edge_face_context], dim=-1)
        face_state = torch.cat([face_hidden, face_edge_context], dim=-1)
        return SizeFieldOutput(
            edge_log_h=self.edge_head(edge_state).squeeze(-1),
            face_log_h=self.face_head(face_state).squeeze(-1),
            edge_uncertainty=self.edge_uncertainty_head(edge_state).squeeze(-1),
            face_uncertainty=self.face_uncertainty_head(face_state).squeeze(-1),
        )


def _edge_neighbors(sample: Any) -> list[tuple[int, int]]:
    graph = _sample_graph(sample)
    arrays = graph.arrays if hasattr(graph, "arrays") else graph["arrays"]
    rows = np.asarray(arrays["coedge_features"])
    by_face: dict[int, set[int]] = {}
    for row in rows:
        face = int(round(float(row[0])))
        edge = int(round(float(row[1])))
        by_face.setdefault(face, set()).add(edge)
    pairs: set[tuple[int, int]] = set()
    for edges in by_face.values():
        sorted_edges = sorted(edges)
        for left_index, left in enumerate(sorted_edges):
            for right in sorted_edges[left_index + 1 :]:
                pairs.add((left, right))
    return sorted(pairs)


def project_edge_sizes(
    sample: Any,
    edge_log_h: torch.Tensor,
    *,
    h_min_mm: float,
    h_max_mm: float,
    growth_rate: float,
    iterations: int = 8,
    control_mask: np.ndarray | None = None,
) -> np.ndarray:
    if h_min_mm <= 0 or h_max_mm < h_min_mm or growth_rate < 1.0:
        raise SizeFieldModelError("invalid_mesh_policy", "requires 0 < h_min <= h_max and growth_rate >= 1")
    sizes = np.exp(edge_log_h.detach().cpu().numpy().astype(np.float64))
    sizes = np.clip(sizes, h_min_mm, h_max_mm)
    if control_mask is not None:
        control_mask = np.asarray(control_mask, dtype=bool)
        if control_mask.shape != sizes.shape:
            raise SizeFieldModelError("malformed_edge_control_mask", "edge control mask must match edge size rows")
    neighbors = _edge_neighbors(sample)
    for _ in range(iterations):
        changed = False
        for left, right in neighbors:
            if left >= len(sizes) or right >= len(sizes):
                continue
            if control_mask is not None and (not bool(control_mask[left]) or not bool(control_mask[right])):
                continue
            small = min(sizes[left], sizes[right])
            limit = min(h_max_mm, small * growth_rate)
            if sizes[left] > limit:
                sizes[left] = limit
                changed = True
            if sizes[right] > limit:
                sizes[right] = limit
                changed = True
        if not changed:
            break
    return np.clip(sizes, h_min_mm, h_max_mm)


def project_face_sizes(face_log_h: torch.Tensor, *, h_min_mm: float, h_max_mm: float) -> np.ndarray:
    if h_min_mm <= 0 or h_max_mm < h_min_mm:
        raise SizeFieldModelError("invalid_mesh_policy", "requires 0 < h_min <= h_max")
    sizes = np.exp(face_log_h.detach().cpu().numpy().astype(np.float64))
    return np.clip(sizes, h_min_mm, h_max_mm)


def _is_geometry_size_control_edge(record: dict[str, Any]) -> bool:
    fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
    bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else None
    if bbox is not None and len(bbox) == 3:
        bbox_x, bbox_y, bbox_z = (abs(float(value)) for value in bbox)
        if bbox_x < 1.0e-6 and bbox_y < 1.0e-6 and bbox_z > 1.0e-6:
            return False
    return True


def _edge_xy_bounds(edge_records: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for record in edge_records:
        fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
        center = fingerprint.get("center_mm") if isinstance(fingerprint.get("center_mm"), list) else None
        if center is not None and len(center) >= 2:
            xs.append(float(center[0]))
            ys.append(float(center[1]))
        points = fingerprint.get("vertex_points_mm") if isinstance(fingerprint.get("vertex_points_mm"), list) else []
        for point in points:
            if isinstance(point, list) and len(point) >= 2:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
    if not xs or not ys:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _is_global_far_field_straight_edge(record: dict[str, Any], bounds: tuple[float, float, float, float] | None, *, h0_mm: float) -> bool:
    if bounds is None:
        return False
    fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
    if int(fingerprint.get("curve_type_id", 0) or 0) != 1:
        return False
    length = float(fingerprint.get("length_mm", 0.0) or 0.0)
    if length <= max(30.0, 6.0 * h0_mm):
        return False
    bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else None
    if bbox is not None and len(bbox) >= 3 and abs(float(bbox[2])) > 1.0e-6:
        return False
    center = fingerprint.get("center_mm") if isinstance(fingerprint.get("center_mm"), list) else None
    if center is None or len(center) < 2:
        return False
    x_min, x_max, y_min, y_max = bounds
    x, y = float(center[0]), float(center[1])
    tolerance = max(1.0e-6, 1.0e-5 * max(abs(x_max - x_min), abs(y_max - y_min), 1.0))
    return abs(x - x_min) <= tolerance or abs(x - x_max) <= tolerance or abs(y - y_min) <= tolerance or abs(y - y_max) <= tolerance


def _curve_local_control_mask(edge_records: list[dict[str, Any]]) -> np.ndarray:
    groups: dict[tuple[float, float, float, float, float], list[tuple[int, float]]] = {}
    for record in edge_records:
        fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
        if int(fingerprint.get("curve_type_id", 0) or 0) not in {2, 3}:
            continue
        center = fingerprint.get("center_mm") if isinstance(fingerprint.get("center_mm"), list) else None
        bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else None
        if center is None or len(center) < 3 or bbox is None or len(bbox) < 2:
            continue
        key = (
            round(float(center[0]), 5),
            round(float(center[1]), 5),
            round(float(fingerprint.get("length_mm", 0.0) or 0.0), 5),
            round(abs(float(bbox[0])), 5),
            round(abs(float(bbox[1])), 5),
        )
        groups.setdefault(key, []).append((int(record["index"]), float(center[2])))

    allowed = np.zeros((len(edge_records),), dtype=bool)
    for record in edge_records:
        fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
        if int(fingerprint.get("curve_type_id", 0) or 0) not in {2, 3}:
            continue
        center = fingerprint.get("center_mm") if isinstance(fingerprint.get("center_mm"), list) else None
        bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else None
        if center is None or len(center) < 3 or bbox is None or len(bbox) < 2:
            continue
        key = (
            round(float(center[0]), 5),
            round(float(center[1]), 5),
            round(float(fingerprint.get("length_mm", 0.0) or 0.0), 5),
            round(abs(float(bbox[0])), 5),
            round(abs(float(bbox[1])), 5),
        )
        siblings = groups.get(key, [])
        has_measurable_boundary_sibling = any(abs(z) > 1.0e-6 for _index, z in siblings)
        index = int(record["index"])
        allowed[index] = abs(float(center[2])) > 1.0e-6 or not has_measurable_boundary_sibling
    return allowed


def _is_curve_edge(record: dict[str, Any]) -> bool:
    fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
    return int(fingerprint.get("curve_type_id", 0) or 0) in {2, 3}


def _semantic_size_control_mask(edge_segmentation_probabilities: np.ndarray | None) -> np.ndarray | None:
    if edge_segmentation_probabilities is None:
        return None
    probabilities = np.asarray(edge_segmentation_probabilities, dtype=np.float32)
    labels = probabilities.argmax(axis=1)
    excluded = {
        EDGE_SEGMENTATION_CLASSES.index("OUTER_BOUNDARY"),
        EDGE_SEGMENTATION_CLASSES.index("FREE_EDGE"),
        EDGE_SEGMENTATION_CLASSES.index("INTERNAL"),
        EDGE_SEGMENTATION_CLASSES.index("OTHER"),
    }
    return np.asarray([int(label) not in excluded for label in labels], dtype=bool)


def _semantic_labels(edge_segmentation_probabilities: np.ndarray | None, edge_count: int) -> list[str | None]:
    if edge_segmentation_probabilities is None:
        return [None] * edge_count
    probabilities = np.asarray(edge_segmentation_probabilities, dtype=np.float32)
    labels = probabilities.argmax(axis=1)
    return [EDGE_SEGMENTATION_CLASSES[int(label)] if index < len(labels) else None for index, label in enumerate(labels)]


def _project_semantic_edge_size(value: float, record: dict[str, Any], semantic: str | None, *, h_min_mm: float, h0_mm: float, h_max_mm: float) -> float:
    if semantic is None:
        return value
    fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
    length = float(fingerprint.get("length_mm", 0.0) or 0.0)
    curve_type = int(fingerprint.get("curve_type_id", 0) or 0)
    bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else []
    bbox_x = abs(float(bbox[0])) if len(bbox) > 0 else 0.0
    bbox_y = abs(float(bbox[1])) if len(bbox) > 1 else 0.0
    roundish_curve = max(bbox_x, bbox_y) > 0.0 and abs(bbox_x - bbox_y) <= 0.25 * max(bbox_x, bbox_y)
    if curve_type in {2, 3} and length > 0 and (semantic == "HOLE_BOUNDARY" or roundish_curve):
        preferred = max(h_min_mm, min(1.5, length / 32.0))
        lower = max(h_min_mm, length / 48.0)
        upper = max(lower, min(1.5, length / 24.0))
        return max(lower, min(upper, preferred if value > upper else value))
    if semantic in {"SLOT_BOUNDARY", "CUTOUT_BOUNDARY"}:
        if length > max(30.0, 6.0 * h0_mm):
            return max(min(h0_mm, h_max_mm), min(h_max_mm, value))
        return max(0.8, min(1.5, value))
    if semantic in {"OUTER_BOUNDARY", "FREE_EDGE"}:
        return max(min(h0_mm, h_max_mm), min(h_max_mm, value))
    if semantic == "BEND_EDGE":
        bbox = fingerprint.get("bbox_mm") if isinstance(fingerprint.get("bbox_mm"), list) else []
        thickness_like = max([abs(float(item)) for item in bbox], default=h_min_mm)
        lower = max(h_min_mm, min(0.5 * h0_mm, max(thickness_like, h_min_mm)))
        return max(lower, min(h_max_mm, value))
    return value


def build_size_field_document(
    sample: Any,
    output: SizeFieldOutput,
    *,
    h0_mm: float,
    h_min_mm: float,
    h_max_mm: float,
    growth_rate: float,
    quality_profile: str = "AMG_QA_SHELL_V2",
    include_face_sizes: bool = False,
    edge_segmentation_probabilities: np.ndarray | None = None,
) -> dict[str, Any]:
    semantic_mask = _semantic_size_control_mask(edge_segmentation_probabilities)
    graph = _sample_graph(sample)
    edge_records = list(graph.entity_signatures["edges"])
    xy_bounds = _edge_xy_bounds(edge_records)
    curve_control_mask = _curve_local_control_mask(edge_records)
    geometry_mask = np.asarray(
        [
            _is_geometry_size_control_edge(record)
            and not _is_global_far_field_straight_edge(record, xy_bounds, h0_mm=h0_mm)
            and (not _is_curve_edge(record) or bool(curve_control_mask[int(record["index"])]))
            for record in edge_records
        ],
        dtype=bool,
    )
    curve_local_mask = curve_control_mask
    semantic_or_geometry_mask = curve_local_mask if semantic_mask is None else np.logical_or(semantic_mask, curve_local_mask)
    control_mask = np.logical_and(geometry_mask, semantic_or_geometry_mask)
    edge_sizes = project_edge_sizes(
        sample,
        output.edge_log_h,
        h_min_mm=h_min_mm,
        h_max_mm=h_max_mm,
        growth_rate=growth_rate,
        control_mask=control_mask,
    )
    semantic_labels = _semantic_labels(edge_segmentation_probabilities, len(edge_sizes))
    for record in edge_records:
        index = int(record["index"])
        if index < len(edge_sizes):
            edge_sizes[index] = _project_semantic_edge_size(
                float(edge_sizes[index]),
                record,
                semantic_labels[index] if index < len(semantic_labels) else None,
                h_min_mm=h_min_mm,
                h0_mm=h0_mm,
                h_max_mm=h_max_mm,
            )
    face_sizes = project_face_sizes(output.face_log_h, h_min_mm=h_min_mm, h_max_mm=h_max_mm) if include_face_sizes else np.empty((0,), dtype=np.float64)
    edge_output_records = []
    for record in edge_records:
        index = int(record["index"])
        if index >= len(control_mask) or not bool(control_mask[index]):
            continue
        edge_output_records.append(
            {
                "edge_signature_id": record["signature_id"],
                "target_size_mm": float(edge_sizes[index]),
                "confidence": float(max(0.0, min(1.0, 1.0 / (1.0 + float(output.edge_uncertainty[index].detach().cpu()))))),
                "source": "direct_brep_size_field_gnn",
            }
        )
    if not edge_output_records:
        raise SizeFieldModelError("empty_predicted_edge_size_field", "predicted size field has no controllable edge sizes")
    face_records = []
    if include_face_sizes:
        for record in graph.entity_signatures["faces"]:
            index = int(record["index"])
            face_records.append(
                {
                    "face_signature_id": record["signature_id"],
                    "target_size_mm": float(face_sizes[index]),
                    "confidence": float(max(0.0, min(1.0, 1.0 / (1.0 + float(output.face_uncertainty[index].detach().cpu()))))),
                    "source": "direct_brep_size_field_gnn",
                }
            )
    return {
        "schema_version": "AMG_SIZE_FIELD_SM_V2",
        "sample_id": sample.sample_id if hasattr(sample, "sample_id") else "unknown_sample",
        "cad_file": "cad/input.step",
        "unit": "mm",
        "global_mesh": {
            "h0_mm": float(h0_mm),
            "h_min_mm": float(h_min_mm),
            "h_max_mm": float(h_max_mm),
            "growth_rate": float(growth_rate),
            "quality_profile": quality_profile,
        },
        "edge_sizes": edge_output_records,
        "face_sizes": face_records,
    }


def write_size_field_document(path: str | Path, document: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
