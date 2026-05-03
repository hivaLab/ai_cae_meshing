"""Projection helpers for AMG model outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import torch

ACTION_NAMES = (
    "KEEP_REFINED",
    "KEEP_WITH_WASHER",
    "SUPPRESS",
    "KEEP_WITH_BEND_ROWS",
    "KEEP_WITH_FLANGE_SIZE",
)
ACTION_BITS = torch.tensor([1, 2, 4, 8, 16], dtype=torch.int64)
SUPPRESS_ACTION_INDEX = ACTION_NAMES.index("SUPPRESS")


class AmgModelError(ValueError):
    """Raised when AMG model inputs or outputs are malformed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ProjectedModelOutput:
    action_logits: torch.Tensor
    action_probabilities: torch.Tensor
    h_values_mm: torch.Tensor
    division_values: torch.Tensor
    quality_risk: torch.Tensor


def apply_action_mask(
    logits: torch.Tensor,
    action_mask: torch.Tensor,
    masked_value: float = -1.0e9,
) -> torch.Tensor:
    """Mask disallowed action logits with a large negative sentinel."""

    if logits.shape != action_mask.shape:
        raise AmgModelError("action_mask_shape_mismatch", "action logits and mask must have identical shape")
    if action_mask.dtype is not torch.bool:
        action_mask = action_mask.to(dtype=torch.bool)
    return torch.where(action_mask, logits, torch.full_like(logits, masked_value))


def project_model_output(
    output: Any,
    mesh_policy: Mapping[str, Any],
) -> ProjectedModelOutput:
    """Project raw model heads into bounded, manifest-projectable values."""

    h_min = float(mesh_policy["h_min_mm"])
    h_max = float(mesh_policy["h_max_mm"])
    if h_min <= 0.0 or h_max < h_min:
        raise AmgModelError("malformed_mesh_policy", "mesh policy requires 0 < h_min_mm <= h_max_mm")

    masked_logits = apply_action_mask(output.feature_action_logits, output.action_mask)
    h_values = torch.exp(output.log_h).clamp(min=h_min, max=h_max)
    divisions = torch.clamp(torch.round(output.division_values), min=1.0)
    quality_risk = torch.sigmoid(output.quality_risk_logits)
    return ProjectedModelOutput(
        action_logits=masked_logits,
        action_probabilities=torch.softmax(masked_logits, dim=-1),
        h_values_mm=h_values,
        division_values=divisions,
        quality_risk=quality_risk,
    )
