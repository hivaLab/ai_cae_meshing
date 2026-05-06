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


def _one_hot(index: int, width: int) -> np.ndarray:
    out = np.zeros((width,), dtype=np.float32)
    if 0 <= index < width:
        out[index] = 1.0
    return out


def _sample_graph(sample: Any) -> Any:
    return sample.graph if hasattr(sample, "graph") else sample


def _label_map(labels: list[dict[str, Any]], key: str) -> dict[str, str]:
    return {str(item[key]): str(item["semantic_label"]) for item in labels}


def build_size_field_graph_tensors(
    sample: Any,
    *,
    face_segmentation_probabilities: np.ndarray | None = None,
    edge_segmentation_probabilities: np.ndarray | None = None,
    part_probabilities: np.ndarray | None = None,
    use_label_segmentation: bool = True,
) -> SizeFieldGraphTensors:
    """Build segmentation-aware model inputs without adding target columns to the graph."""

    graph = _sample_graph(sample)
    arrays = graph.arrays if hasattr(graph, "arrays") else graph["arrays"]
    face_features = np.asarray(arrays["face_features"], dtype=np.float32)
    edge_features = np.asarray(arrays["edge_features"], dtype=np.float32)
    coedge_features = np.asarray(arrays["coedge_features"], dtype=np.float32)
    if face_features.ndim != 2 or edge_features.ndim != 2 or coedge_features.ndim != 2:
        raise SizeFieldModelError("malformed_graph_arrays", "face, edge, and coedge arrays must be 2D")

    face_count = face_features.shape[0]
    edge_count = edge_features.shape[0]
    face_probs = np.zeros((face_count, len(FACE_SEGMENTATION_CLASSES)), dtype=np.float32)
    edge_probs = np.zeros((edge_count, len(EDGE_SEGMENTATION_CLASSES)), dtype=np.float32)
    part_probs = np.zeros((len(PART_CLASS_ORDER),), dtype=np.float32)

    if face_segmentation_probabilities is not None:
        face_probs = np.asarray(face_segmentation_probabilities, dtype=np.float32)
    elif use_label_segmentation and hasattr(sample, "labels"):
        face_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["faces"]}
        for item in sample.labels.face_segmentation["labels"]:
            index = face_by_sig.get(item["face_signature_id"])
            if index is not None and item["semantic_label"] in FACE_SEGMENTATION_CLASSES:
                face_probs[index] = _one_hot(FACE_SEGMENTATION_CLASSES.index(item["semantic_label"]), len(FACE_SEGMENTATION_CLASSES))

    if edge_segmentation_probabilities is not None:
        edge_probs = np.asarray(edge_segmentation_probabilities, dtype=np.float32)
    elif use_label_segmentation and hasattr(sample, "labels"):
        edge_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["edges"]}
        for item in sample.labels.edge_segmentation["labels"]:
            index = edge_by_sig.get(item["edge_signature_id"])
            if index is not None and item["semantic_label"] in EDGE_SEGMENTATION_CLASSES:
                edge_probs[index] = _one_hot(EDGE_SEGMENTATION_CLASSES.index(item["semantic_label"]), len(EDGE_SEGMENTATION_CLASSES))

    if part_probabilities is not None:
        part_probs = np.asarray(part_probabilities, dtype=np.float32)
    elif use_label_segmentation and hasattr(sample, "labels"):
        part_class = str(sample.labels.part_class["part_class"])
        if part_class in PART_CLASS_ORDER:
            part_probs = _one_hot(PART_CLASS_ORDER.index(part_class), len(PART_CLASS_ORDER))

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


def build_size_field_targets(sample: Any) -> SizeFieldTargets:
    graph = sample.graph
    edge_count = graph.arrays["edge_features"].shape[0]
    face_count = graph.arrays["face_features"].shape[0]
    edge_values = torch.zeros((edge_count,), dtype=torch.float32)
    edge_mask = torch.zeros((edge_count,), dtype=torch.bool)
    face_values = torch.zeros((face_count,), dtype=torch.float32)
    face_mask = torch.zeros((face_count,), dtype=torch.bool)
    edge_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["edges"]}
    face_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["faces"]}
    for item in sample.labels.mesh_size_field["edge_sizes"]:
        index = edge_by_sig.get(item["edge_signature_id"])
        if index is not None:
            edge_values[index] = math.log(float(item["target_size_mm"]))
            edge_mask[index] = True
    for item in sample.labels.mesh_size_field.get("face_sizes", []):
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


def project_edge_sizes(sample: Any, edge_log_h: torch.Tensor, *, h_min_mm: float, h_max_mm: float, growth_rate: float, iterations: int = 8) -> np.ndarray:
    if h_min_mm <= 0 or h_max_mm < h_min_mm or growth_rate < 1.0:
        raise SizeFieldModelError("invalid_mesh_policy", "requires 0 < h_min <= h_max and growth_rate >= 1")
    sizes = np.exp(edge_log_h.detach().cpu().numpy().astype(np.float64))
    sizes = np.clip(sizes, h_min_mm, h_max_mm)
    neighbors = _edge_neighbors(sample)
    for _ in range(iterations):
        changed = False
        for left, right in neighbors:
            if left >= len(sizes) or right >= len(sizes):
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
) -> dict[str, Any]:
    edge_sizes = project_edge_sizes(sample, output.edge_log_h, h_min_mm=h_min_mm, h_max_mm=h_max_mm, growth_rate=growth_rate)
    face_sizes = project_face_sizes(output.face_log_h, h_min_mm=h_min_mm, h_max_mm=h_max_mm) if include_face_sizes else np.empty((0,), dtype=np.float64)
    graph = _sample_graph(sample)
    edge_records = []
    for record in graph.entity_signatures["edges"]:
        index = int(record["index"])
        edge_records.append(
            {
                "edge_signature_id": record["signature_id"],
                "target_size_mm": float(edge_sizes[index]),
                "confidence": float(max(0.0, min(1.0, 1.0 / (1.0 + float(output.edge_uncertainty[index].detach().cpu()))))),
                "source": "direct_brep_size_field_gnn",
            }
        )
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
        "edge_sizes": edge_records,
        "face_sizes": face_records,
    }


def write_size_field_document(path: str | Path, document: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
