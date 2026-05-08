"""BRepNet-style B-rep face/edge segmentation models for AMG v2."""

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
    coedge_next: torch.Tensor
    coedge_prev: torch.Tensor
    coedge_mate: torch.Tensor


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


def _graph_arrays_and_adjacency(sample: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = _sample_graph(sample)
    if hasattr(graph, "arrays"):
        return graph.arrays, getattr(graph, "adjacency", {})
    if isinstance(graph, dict):
        return graph["arrays"], graph.get("adjacency", {})
    raise SegmentationModelError("malformed_sample_graph", "sample does not expose graph arrays")


def _dense_coedge_relation(
    adjacency: dict[str, Any],
    relation: str,
    *,
    face_count: int,
    edge_count: int,
    coedge_count: int,
) -> torch.Tensor:
    coedge_offset = 1 + face_count + edge_count
    dense = torch.arange(coedge_count, dtype=torch.long)
    rows = np.asarray(adjacency.get(relation, np.empty((0, 2), dtype=np.int64)), dtype=np.int64)
    if rows.ndim != 2 or rows.shape[1] != 2:
        raise SegmentationModelError("malformed_coedge_topology", f"{relation} must be an Nx2 integer array")
    for source, target in rows.tolist():
        source_index = int(source) - coedge_offset
        target_index = int(target) - coedge_offset
        if 0 <= source_index < coedge_count and 0 <= target_index < coedge_count:
            dense[source_index] = target_index
    return dense


def _validate_winged_edge_topology(next_index: torch.Tensor, prev_index: torch.Tensor, mate_index: torch.Tensor) -> None:
    count = int(next_index.numel())
    if count == 0:
        return
    arange = torch.arange(count, dtype=torch.long)
    for name, relation in (("next", next_index), ("prev", prev_index), ("mate", mate_index)):
        if torch.any(relation < 0) or torch.any(relation >= count):
            raise SegmentationModelError("malformed_coedge_topology", f"coedge {name} relation contains out-of-bounds indices")
    if torch.any(prev_index[next_index] != arange) or torch.any(next_index[prev_index] != arange):
        raise SegmentationModelError("malformed_coedge_topology", "coedge next/prev relations must be reciprocal")
    if torch.any(mate_index[mate_index] != arange):
        raise SegmentationModelError("malformed_coedge_topology", "coedge mate relation must be reciprocal")


def build_entity_graph_tensors(sample: Any) -> EntityGraphTensors:
    arrays, adjacency = _graph_arrays_and_adjacency(sample)
    part = np.asarray(arrays.get("part_features", np.empty((0, 0))), dtype=np.float32)
    face = torch.as_tensor(np.asarray(arrays["face_features"], dtype=np.float32))
    edge = torch.as_tensor(np.asarray(arrays["edge_features"], dtype=np.float32))
    coedge = torch.as_tensor(np.asarray(arrays["coedge_features"], dtype=np.float32))
    if face.ndim != 2 or edge.ndim != 2 or coedge.ndim != 2:
        raise SegmentationModelError("malformed_entity_tensors", "face, edge, and coedge features must be 2D")
    if part.ndim == 2 and part.shape[0] == 1 and part.shape[1] > 0:
        part_row = part[0].astype(np.float32)
        face = torch.as_tensor(np.concatenate([face.numpy(), np.repeat(part_row.reshape(1, -1), face.shape[0], axis=0)], axis=1), dtype=torch.float32)
        edge = torch.as_tensor(np.concatenate([edge.numpy(), np.repeat(part_row.reshape(1, -1), edge.shape[0], axis=0)], axis=1), dtype=torch.float32)
        coedge = torch.as_tensor(np.concatenate([coedge.numpy(), np.repeat(part_row.reshape(1, -1), coedge.shape[0], axis=0)], axis=1), dtype=torch.float32)
    if coedge.shape[1] < 2:
        raise SegmentationModelError("malformed_coedge_features", "coedge features require parent face and edge columns")
    next_index = _dense_coedge_relation(adjacency, "COEDGE_NEXT", face_count=face.shape[0], edge_count=edge.shape[0], coedge_count=coedge.shape[0])
    prev_index = _dense_coedge_relation(adjacency, "COEDGE_PREV", face_count=face.shape[0], edge_count=edge.shape[0], coedge_count=coedge.shape[0])
    mate_index = _dense_coedge_relation(adjacency, "COEDGE_MATE", face_count=face.shape[0], edge_count=edge.shape[0], coedge_count=coedge.shape[0])
    _validate_winged_edge_topology(next_index, prev_index, mate_index)
    return EntityGraphTensors(
        face_features=face,
        edge_features=edge,
        coedge_features=coedge,
        coedge_next=next_index,
        coedge_prev=prev_index,
        coedge_mate=mate_index,
    )


def build_segmentation_targets(sample: Any) -> SegmentationTargets:
    graph = sample.graph
    face_count = graph.arrays["face_features"].shape[0]
    edge_count = graph.arrays["edge_features"].shape[0]
    face_targets = torch.full((face_count,), FACE_SEGMENTATION_CLASSES.index("OTHER"), dtype=torch.long)
    edge_targets = torch.full((edge_count,), EDGE_SEGMENTATION_CLASSES.index("OTHER"), dtype=torch.long)
    face_index_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["faces"]}
    edge_index_by_sig = {record["signature_id"]: int(record["index"]) for record in graph.entity_signatures["edges"]}
    for item in sample.labels.face_segmentation["labels"]:
        label = item["semantic_label"]
        if label not in FACE_SEGMENTATION_CLASSES:
            raise SegmentationModelError("unsupported_face_semantic_label", f"unsupported face semantic label: {label}")
        if item["face_signature_id"] in face_index_by_sig:
            face_targets[face_index_by_sig[item["face_signature_id"]]] = FACE_SEGMENTATION_CLASSES.index(label)
    for item in sample.labels.edge_segmentation["labels"]:
        label = item["semantic_label"]
        if label not in EDGE_SEGMENTATION_CLASSES:
            raise SegmentationModelError("unsupported_edge_semantic_label", f"unsupported edge semantic label: {label}")
        if item["edge_signature_id"] in edge_index_by_sig:
            edge_targets[edge_index_by_sig[item["edge_signature_id"]]] = EDGE_SEGMENTATION_CLASSES.index(label)
    return SegmentationTargets(face_labels=face_targets, edge_labels=edge_targets)


def _pool_max(values: torch.Tensor, indices: torch.Tensor, count: int) -> torch.Tensor:
    if count <= 0:
        return values.new_zeros((0, values.shape[1]))
    pooled = values.new_zeros((count, values.shape[1]))
    for index in range(count):
        mask = indices == index
        if bool(mask.any()):
            pooled[index] = values[mask].max(dim=0).values
    return pooled


class BRepNetBlock(nn.Module):
    """Winged-edge coedge kernel block inspired by Lambourne et al.'s BRepNet."""

    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        # self, next, prev, mate, mate-next, mate-prev, face, mate-face, edge, next-edge, prev-edge, mate-edge
        self.coedge_update = nn.Sequential(nn.Linear(hidden_dim * 12, hidden_dim * 2), nn.ReLU(), nn.Linear(hidden_dim * 2, hidden_dim))
        self.face_update = nn.Sequential(nn.Linear(hidden_dim * 2, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim))
        self.edge_update = nn.Sequential(nn.Linear(hidden_dim * 2, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim))
        self.coedge_norm = nn.LayerNorm(hidden_dim)
        self.face_norm = nn.LayerNorm(hidden_dim)
        self.edge_norm = nn.LayerNorm(hidden_dim)

    def forward(
        self,
        face_hidden: torch.Tensor,
        edge_hidden: torch.Tensor,
        coedge_hidden: torch.Tensor,
        face_indices: torch.Tensor,
        edge_indices: torch.Tensor,
        next_index: torch.Tensor,
        prev_index: torch.Tensor,
        mate_index: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mate_next = next_index[mate_index]
        mate_prev = prev_index[mate_index]
        kernel = torch.cat(
            [
                coedge_hidden,
                coedge_hidden[next_index],
                coedge_hidden[prev_index],
                coedge_hidden[mate_index],
                coedge_hidden[mate_next],
                coedge_hidden[mate_prev],
                face_hidden[face_indices],
                face_hidden[face_indices[mate_index]],
                edge_hidden[edge_indices],
                edge_hidden[edge_indices[next_index]],
                edge_hidden[edge_indices[prev_index]],
                edge_hidden[edge_indices[mate_index]],
            ],
            dim=-1,
        )
        coedge_delta = self.coedge_update(kernel)
        coedge_hidden = self.coedge_norm(coedge_hidden + coedge_delta)
        face_context = _pool_max(coedge_delta, face_indices, face_hidden.shape[0])
        edge_context = _pool_max(coedge_delta, edge_indices, edge_hidden.shape[0])
        face_hidden = self.face_norm(face_hidden + self.face_update(torch.cat([face_hidden, face_context], dim=-1)))
        edge_hidden = self.edge_norm(edge_hidden + self.edge_update(torch.cat([edge_hidden, edge_context], dim=-1)))
        return face_hidden, edge_hidden, coedge_hidden


class BRepNetSegmentationModel(nn.Module):
    """BRepNet-style segmentation network using coedge next/prev/mate walks."""

    model_type = "brepnet"

    def __init__(self, face_feature_dim: int, edge_feature_dim: int, coedge_feature_dim: int, hidden_dim: int = 96, num_layers: int = 3) -> None:
        super().__init__()
        self.face_encoder = nn.Sequential(nn.Linear(face_feature_dim, hidden_dim), nn.ReLU())
        self.edge_encoder = nn.Sequential(nn.Linear(edge_feature_dim, hidden_dim), nn.ReLU())
        self.coedge_encoder = nn.Sequential(nn.Linear(coedge_feature_dim, hidden_dim), nn.ReLU())
        self.blocks = nn.ModuleList(BRepNetBlock(hidden_dim) for _ in range(num_layers))
        self.face_head = nn.Linear(hidden_dim, len(FACE_SEGMENTATION_CLASSES))
        self.edge_head = nn.Linear(hidden_dim, len(EDGE_SEGMENTATION_CLASSES))
        self.face_geometry_head = nn.Sequential(nn.Linear(face_feature_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, len(FACE_SEGMENTATION_CLASSES)))
        self.edge_geometry_head = nn.Sequential(nn.Linear(edge_feature_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, len(EDGE_SEGMENTATION_CLASSES)))
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.coedge_feature_dim = coedge_feature_dim

    def forward(self, tensors: EntityGraphTensors) -> SegmentationOutput:
        face_hidden = self.face_encoder(tensors.face_features)
        edge_hidden = self.edge_encoder(tensors.edge_features)
        coedge_hidden = self.coedge_encoder(tensors.coedge_features)
        device = face_hidden.device
        coedge = tensors.coedge_features.to(device=device)
        face_indices = coedge[:, 0].round().to(dtype=torch.long)
        edge_indices = coedge[:, 1].round().to(dtype=torch.long)
        next_index = tensors.coedge_next.to(device=device)
        prev_index = tensors.coedge_prev.to(device=device)
        mate_index = tensors.coedge_mate.to(device=device)
        if torch.any(face_indices < 0) or torch.any(face_indices >= face_hidden.shape[0]):
            raise SegmentationModelError("invalid_coedge_face_index", "coedge parent face index is out of bounds")
        if torch.any(edge_indices < 0) or torch.any(edge_indices >= edge_hidden.shape[0]):
            raise SegmentationModelError("invalid_coedge_edge_index", "coedge parent edge index is out of bounds")
        for block in self.blocks:
            face_hidden, edge_hidden, coedge_hidden = block(face_hidden, edge_hidden, coedge_hidden, face_indices, edge_indices, next_index, prev_index, mate_index)
        return SegmentationOutput(
            face_logits=self.face_head(face_hidden) + self.face_geometry_head(tensors.face_features),
            edge_logits=self.edge_head(edge_hidden) + self.edge_geometry_head(tensors.edge_features),
        )


def _model_from_checkpoint(checkpoint: dict[str, Any]) -> nn.Module:
    model_type = str(checkpoint.get("model_type", ""))
    required = ("face_feature_dim", "edge_feature_dim", "hidden_dim")
    if any(key not in checkpoint for key in required):
        raise SegmentationModelError("malformed_segmentation_checkpoint", "segmentation checkpoint is missing model metadata")
    coedge_dim = int(checkpoint.get("coedge_feature_dim", 3))
    if model_type != "brepnet":
        raise SegmentationModelError("unsupported_segmentation_model_type", f"segmentation checkpoints must be brepnet, got: {model_type or '<missing>'}")
    return BRepNetSegmentationModel(
        int(checkpoint["face_feature_dim"]),
        int(checkpoint["edge_feature_dim"]),
        coedge_dim,
        hidden_dim=int(checkpoint["hidden_dim"]),
        num_layers=int(checkpoint.get("num_layers", 3)),
    )


def load_segmentation_model(checkpoint_path: str | Path) -> nn.Module:
    path = Path(checkpoint_path)
    if not path.is_file():
        raise SegmentationModelError("missing_segmentation_checkpoint", f"segmentation checkpoint does not exist: {path}")
    checkpoint = torch.load(path, map_location="cpu")
    if not isinstance(checkpoint, dict) or "model_state" not in checkpoint:
        raise SegmentationModelError("malformed_segmentation_checkpoint", "segmentation checkpoint is missing model metadata")
    model = _model_from_checkpoint(checkpoint)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model


def predict_entity_segmentation_probabilities(sample: Any, model: nn.Module) -> tuple[np.ndarray, np.ndarray]:
    tensors = build_entity_graph_tensors(sample)
    face_dim = int(model.face_encoder[0].in_features)
    edge_dim = int(model.edge_encoder[0].in_features)
    if tensors.face_features.shape[1] != face_dim or tensors.edge_features.shape[1] != edge_dim:
        raise SegmentationModelError("segmentation_input_dimension_mismatch", "sample graph feature dimensions do not match segmentation checkpoint")
    with torch.no_grad():
        output = model(tensors)
        face_probs = torch.softmax(output.face_logits, dim=-1).cpu().numpy()
        edge_probs = torch.softmax(output.edge_logits, dim=-1).cpu().numpy()
    return face_probs.astype(np.float32), edge_probs.astype(np.float32)
