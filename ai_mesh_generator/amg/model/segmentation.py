"""B-rep face/edge segmentation model for AMG v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

FACE_SEGMENTATION_CLASSES = (
    "BASE_PANEL",
    "FLANGE",
    "BEND",
    "HOLE_WALL",
    "SLOT_WALL",
    "CUTOUT_WALL",
    "SIDE_WALL",
    "OTHER",
)
EDGE_SEGMENTATION_CLASSES = (
    "OUTER_BOUNDARY",
    "HOLE_BOUNDARY",
    "SLOT_BOUNDARY",
    "CUTOUT_BOUNDARY",
    "BEND_EDGE",
    "FREE_EDGE",
    "INTERNAL",
    "OTHER",
)


class SegmentationModelError(ValueError):
    """Raised when B-rep segmentation tensors are malformed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class EntityGraphTensors:
    face_features: torch.Tensor
    edge_features: torch.Tensor
    coedge_features: torch.Tensor


@dataclass(frozen=True)
class SegmentationTargets:
    face_labels: torch.Tensor
    edge_labels: torch.Tensor


@dataclass(frozen=True)
class SegmentationOutput:
    face_logits: torch.Tensor
    edge_logits: torch.Tensor


def _sample_graph(sample: Any) -> Any:
    if hasattr(sample, "graph"):
        return sample.graph
    return sample


def build_entity_graph_tensors(sample: Any) -> EntityGraphTensors:
    graph = _sample_graph(sample)
    arrays = graph.arrays if hasattr(graph, "arrays") else graph["arrays"]
    face = torch.as_tensor(np.asarray(arrays["face_features"], dtype=np.float32))
    edge = torch.as_tensor(np.asarray(arrays["edge_features"], dtype=np.float32))
    coedge = torch.as_tensor(np.asarray(arrays["coedge_features"], dtype=np.float32))
    if face.ndim != 2 or edge.ndim != 2 or coedge.ndim != 2:
        raise SegmentationModelError("malformed_entity_tensors", "face, edge, and coedge features must be 2D")
    if coedge.shape[1] < 2:
        raise SegmentationModelError("malformed_coedge_features", "coedge features require parent face and edge columns")
    return EntityGraphTensors(face_features=face, edge_features=edge, coedge_features=coedge)


def build_segmentation_targets(sample: Any) -> SegmentationTargets:
    graph = sample.graph
    face_count = graph.arrays["face_features"].shape[0]
    edge_count = graph.arrays["edge_features"].shape[0]
    face_targets = torch.full((face_count,), FACE_SEGMENTATION_CLASSES.index("OTHER"), dtype=torch.long)
    edge_targets = torch.full((edge_count,), EDGE_SEGMENTATION_CLASSES.index("OTHER"), dtype=torch.long)
    face_index_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["faces"]}
    edge_index_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["edges"]}
    for item in sample.labels.face_segmentation["labels"]:
        if item["face_signature_id"] in face_index_by_sig:
            face_targets[face_index_by_sig[item["face_signature_id"]]] = FACE_SEGMENTATION_CLASSES.index(item["semantic_label"])
    for item in sample.labels.edge_segmentation["labels"]:
        if item["edge_signature_id"] in edge_index_by_sig:
            edge_targets[edge_index_by_sig[item["edge_signature_id"]]] = EDGE_SEGMENTATION_CLASSES.index(item["semantic_label"])
    return SegmentationTargets(face_labels=face_targets, edge_labels=edge_targets)


class BrepSegmentationModel(nn.Module):
    """Small coedge-aware segmentation network.

    It is intentionally compact, but it uses coedge parent face/edge incidence to pass
    information between face and edge streams.
    """

    def __init__(self, face_feature_dim: int, edge_feature_dim: int, hidden_dim: int = 64) -> None:
        super().__init__()
        self.face_encoder = nn.Sequential(nn.Linear(face_feature_dim, hidden_dim), nn.ReLU())
        self.edge_encoder = nn.Sequential(nn.Linear(edge_feature_dim, hidden_dim), nn.ReLU())
        self.face_head = nn.Linear(hidden_dim * 2, len(FACE_SEGMENTATION_CLASSES))
        self.edge_head = nn.Linear(hidden_dim * 2, len(EDGE_SEGMENTATION_CLASSES))

    def forward(self, tensors: EntityGraphTensors) -> SegmentationOutput:
        face_hidden = self.face_encoder(tensors.face_features)
        edge_hidden = self.edge_encoder(tensors.edge_features)
        device = face_hidden.device
        coedge = tensors.coedge_features.to(device=device)
        face_indices = coedge[:, 0].round().to(dtype=torch.long)
        edge_indices = coedge[:, 1].round().to(dtype=torch.long)
        if torch.any(face_indices < 0) or torch.any(face_indices >= face_hidden.shape[0]):
            raise SegmentationModelError("invalid_coedge_face_index", "coedge parent face index is out of bounds")
        if torch.any(edge_indices < 0) or torch.any(edge_indices >= edge_hidden.shape[0]):
            raise SegmentationModelError("invalid_coedge_edge_index", "coedge parent edge index is out of bounds")

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

        return SegmentationOutput(
            face_logits=self.face_head(torch.cat([face_hidden, face_edge_context], dim=-1)),
            edge_logits=self.edge_head(torch.cat([edge_hidden, edge_face_context], dim=-1)),
        )


def load_segmentation_model(checkpoint_path: str | Path) -> BrepSegmentationModel:
    path = Path(checkpoint_path)
    if not path.is_file():
        raise SegmentationModelError("missing_segmentation_checkpoint", f"segmentation checkpoint does not exist: {path}")
    checkpoint = torch.load(path, map_location="cpu")
    required = ("model_state", "face_feature_dim", "edge_feature_dim", "hidden_dim")
    if not isinstance(checkpoint, dict) or any(key not in checkpoint for key in required):
        raise SegmentationModelError("malformed_segmentation_checkpoint", "segmentation checkpoint is missing model metadata")
    model = BrepSegmentationModel(
        int(checkpoint["face_feature_dim"]),
        int(checkpoint["edge_feature_dim"]),
        hidden_dim=int(checkpoint["hidden_dim"]),
    )
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model


def predict_entity_segmentation_probabilities(sample: Any, model: BrepSegmentationModel) -> tuple[np.ndarray, np.ndarray]:
    tensors = build_entity_graph_tensors(sample)
    face_dim = model.face_encoder[0].in_features
    edge_dim = model.edge_encoder[0].in_features
    if tensors.face_features.shape[1] != face_dim or tensors.edge_features.shape[1] != edge_dim:
        raise SegmentationModelError("segmentation_input_dimension_mismatch", "sample graph feature dimensions do not match segmentation checkpoint")
    with torch.no_grad():
        output = model(tensors)
        face_probs = torch.softmax(output.face_logits, dim=-1).cpu().numpy()
        edge_probs = torch.softmax(output.edge_logits, dim=-1).cpu().numpy()
    return face_probs.astype(np.float32), edge_probs.astype(np.float32)
