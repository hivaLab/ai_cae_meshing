"""PyTorch skeleton for AMG B-rep graph manifest prediction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from torch import nn

from ai_mesh_generator.amg.model.projector import ACTION_BITS, SUPPRESS_ACTION_INDEX, AmgModelError

PART_CLASSES = (
    "SM_FLAT_PANEL",
    "SM_SINGLE_FLANGE",
    "SM_L_BRACKET",
    "SM_U_CHANNEL",
    "SM_HAT_CHANNEL",
)
FEATURE_TYPES = ("HOLE", "SLOT", "CUTOUT", "BEND", "FLANGE")
FEATURE_CANDIDATE_COLUMN_COUNT = 14
FEATURE_TYPE_ID_COLUMN = 0
EXPECTED_ACTION_MASK_COLUMN = 13
ROLE_ID_COLUMN = 1
UNKNOWN_ROLE_ID = 0
FEATURE_TYPE_PRIOR_LOGIT = 20.0


@dataclass(frozen=True)
class GraphBatch:
    part_features: torch.Tensor
    feature_candidate_features: torch.Tensor
    feature_batch_indices: torch.Tensor
    action_mask: torch.Tensor
    model_input_paths: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class ModelDimensions:
    part_feature_dim: int
    candidate_feature_dim: int = FEATURE_CANDIDATE_COLUMN_COUNT
    hidden_dim: int = 32
    part_class_count: int = len(PART_CLASSES)
    feature_type_count: int = len(FEATURE_TYPES)
    action_count: int = int(ACTION_BITS.numel())
    log_h_count: int = 2
    division_count: int = 3


@dataclass(frozen=True)
class AmgModelOutput:
    part_class_logits: torch.Tensor
    feature_type_logits: torch.Tensor
    feature_action_logits: torch.Tensor
    log_h: torch.Tensor
    division_values: torch.Tensor
    quality_risk_logits: torch.Tensor
    action_mask: torch.Tensor


def _as_sample_list(samples: Any) -> list[Any]:
    if isinstance(samples, Mapping) and "part_features" in samples:
        return [samples]
    if hasattr(samples, "graph") or hasattr(samples, "arrays"):
        return [samples]
    if isinstance(samples, Sequence) and not isinstance(samples, str | bytes):
        return list(samples)
    raise AmgModelError("malformed_samples", "samples must be a sample, graph input, arrays mapping, or sequence")


def _arrays_from_sample(sample: Any) -> tuple[Mapping[str, Any], dict[str, str]]:
    if isinstance(sample, Mapping):
        return sample, {}
    if hasattr(sample, "graph"):
        graph = sample.graph
        return graph.arrays, dict(getattr(sample, "model_input_paths", {}))
    if hasattr(sample, "arrays"):
        return sample.arrays, dict(getattr(sample, "model_input_paths", {}))
    raise AmgModelError("malformed_sample", "sample does not expose graph arrays")


def _array(value: Any, key: str) -> np.ndarray:
    if key not in value:
        raise AmgModelError("missing_graph_array", f"missing graph array: {key}")
    return np.asarray(value[key])


def _action_mask(candidate_features: torch.Tensor) -> torch.Tensor:
    mask_values = candidate_features[:, EXPECTED_ACTION_MASK_COLUMN].to(dtype=torch.int64)
    bits = ACTION_BITS.to(device=candidate_features.device)
    mask = torch.bitwise_and(mask_values.unsqueeze(1), bits.unsqueeze(0)).ne(0)
    unknown_roles = candidate_features[:, ROLE_ID_COLUMN].to(dtype=torch.int64).eq(UNKNOWN_ROLE_ID)
    if unknown_roles.any():
        mask[unknown_roles, SUPPRESS_ACTION_INDEX] = False
    return mask


def _feature_type_prior(candidate_features: torch.Tensor, feature_type_count: int) -> torch.Tensor:
    prior = candidate_features.new_zeros((candidate_features.shape[0], feature_type_count))
    if candidate_features.shape[0] == 0:
        return prior
    type_indices = candidate_features[:, FEATURE_TYPE_ID_COLUMN].round().to(dtype=torch.int64) - 1
    valid = torch.logical_and(type_indices >= 0, type_indices < feature_type_count)
    if valid.any():
        prior[valid, type_indices[valid]] = FEATURE_TYPE_PRIOR_LOGIT
    return prior


def build_graph_batch(samples: Any) -> GraphBatch:
    """Build a minimal tensor batch from T-601 AMG dataset samples or graph arrays."""

    sample_list = _as_sample_list(samples)
    if not sample_list:
        raise AmgModelError("empty_batch", "at least one sample is required")

    part_rows: list[np.ndarray] = []
    candidate_rows: list[np.ndarray] = []
    batch_indices: list[np.ndarray] = []
    paths: list[dict[str, str]] = []
    for batch_index, sample in enumerate(sample_list):
        arrays, model_input_paths = _arrays_from_sample(sample)
        part_features = _array(arrays, "part_features")
        candidate_features = _array(arrays, "feature_candidate_features")
        if part_features.ndim != 2 or part_features.shape[0] != 1:
            raise AmgModelError("malformed_part_features", "part_features must have shape (1, P)")
        if candidate_features.ndim != 2 or candidate_features.shape[1] != FEATURE_CANDIDATE_COLUMN_COUNT:
            raise AmgModelError("malformed_candidate_features", "feature_candidate_features must have shape (N, 14)")
        part_rows.append(part_features[0].astype(np.float32, copy=False))
        candidate_rows.append(candidate_features.astype(np.float32, copy=False))
        batch_indices.append(np.full(candidate_features.shape[0], batch_index, dtype=np.int64))
        paths.append(dict(model_input_paths))

    part_tensor = torch.as_tensor(np.stack(part_rows), dtype=torch.float32)
    if candidate_rows:
        candidate_tensor = torch.as_tensor(np.concatenate(candidate_rows, axis=0), dtype=torch.float32)
        batch_tensor = torch.as_tensor(np.concatenate(batch_indices, axis=0), dtype=torch.long)
    else:
        candidate_tensor = torch.empty((0, FEATURE_CANDIDATE_COLUMN_COUNT), dtype=torch.float32)
        batch_tensor = torch.empty((0,), dtype=torch.long)
    return GraphBatch(
        part_features=part_tensor,
        feature_candidate_features=candidate_tensor,
        feature_batch_indices=batch_tensor,
        action_mask=_action_mask(candidate_tensor),
        model_input_paths=tuple(paths),
    )


class AmgGraphModel(nn.Module):
    """Lightweight multi-head AMG model skeleton for feature candidates."""

    def __init__(self, dimensions: ModelDimensions) -> None:
        super().__init__()
        self.dimensions = dimensions
        self.part_encoder = nn.Sequential(
            nn.Linear(dimensions.part_feature_dim, dimensions.hidden_dim),
            nn.ReLU(),
            nn.Linear(dimensions.hidden_dim, dimensions.hidden_dim),
            nn.ReLU(),
        )
        self.candidate_encoder = nn.Sequential(
            nn.Linear(dimensions.candidate_feature_dim, dimensions.hidden_dim),
            nn.ReLU(),
        )
        self.feature_fusion = nn.Sequential(
            nn.Linear(dimensions.hidden_dim * 2, dimensions.hidden_dim),
            nn.ReLU(),
        )
        self.part_class_head = nn.Linear(dimensions.hidden_dim, dimensions.part_class_count)
        self.feature_type_head = nn.Linear(dimensions.hidden_dim, dimensions.feature_type_count)
        self.feature_action_head = nn.Linear(dimensions.hidden_dim, dimensions.action_count)
        self.log_h_head = nn.Linear(dimensions.hidden_dim, dimensions.log_h_count)
        self.division_head = nn.Linear(dimensions.hidden_dim, dimensions.division_count)
        self.quality_risk_head = nn.Linear(dimensions.hidden_dim, 1)

    def forward(self, batch: GraphBatch) -> AmgModelOutput:
        if batch.part_features.shape[1] != self.dimensions.part_feature_dim:
            raise AmgModelError("part_feature_dim_mismatch", "part feature dimension does not match model")
        if batch.feature_candidate_features.shape[1] != self.dimensions.candidate_feature_dim:
            raise AmgModelError("candidate_feature_dim_mismatch", "candidate feature dimension does not match model")

        part_hidden = self.part_encoder(batch.part_features)
        candidate_hidden = self.candidate_encoder(batch.feature_candidate_features)
        if candidate_hidden.shape[0]:
            candidate_part_hidden = part_hidden[batch.feature_batch_indices]
            fused = self.feature_fusion(torch.cat([candidate_hidden, candidate_part_hidden], dim=-1))
        else:
            fused = candidate_hidden.new_empty((0, self.dimensions.hidden_dim))
        feature_type_logits = self.feature_type_head(fused) + _feature_type_prior(
            batch.feature_candidate_features,
            self.dimensions.feature_type_count,
        )
        return AmgModelOutput(
            part_class_logits=self.part_class_head(part_hidden),
            feature_type_logits=feature_type_logits,
            feature_action_logits=self.feature_action_head(fused),
            log_h=self.log_h_head(fused),
            division_values=self.division_head(fused),
            quality_risk_logits=self.quality_risk_head(fused),
            action_mask=batch.action_mask,
        )
