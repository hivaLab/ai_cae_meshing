"""Tiny deterministic training-loop smoke utilities for AMG models."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

from ai_mesh_generator.amg.model import AmgGraphModel, AmgModelOutput, GraphBatch, ModelDimensions, apply_action_mask, build_graph_batch
from ai_mesh_generator.amg.model.graph_model import FEATURE_TYPES, PART_CLASSES

FEATURE_TYPE_COLUMN = 0
SIZE_1_COLUMN = 2
SIZE_2_COLUMN = 3
CLEARANCE_RATIO_COLUMN = 12


class AmgTrainingSmokeError(ValueError):
    """Raised when the AMG smoke training path cannot run safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SmokeTargets:
    part_class_targets: torch.Tensor
    feature_type_targets: torch.Tensor
    feature_action_targets: torch.Tensor
    log_h_targets: torch.Tensor
    division_targets: torch.Tensor
    quality_risk_targets: torch.Tensor


@dataclass(frozen=True)
class SmokeLossBreakdown:
    total: torch.Tensor
    part_class: torch.Tensor
    feature_type: torch.Tensor
    feature_action: torch.Tensor
    log_h: torch.Tensor
    division: torch.Tensor
    quality_risk: torch.Tensor

    def as_metrics(self) -> dict[str, float]:
        return {
            "loss_total": float(self.total.detach().cpu()),
            "loss_part_class": float(self.part_class.detach().cpu()),
            "loss_feature_type": float(self.feature_type.detach().cpu()),
            "loss_feature_action": float(self.feature_action.detach().cpu()),
            "loss_log_h": float(self.log_h.detach().cpu()),
            "loss_division": float(self.division.detach().cpu()),
            "loss_quality_risk": float(self.quality_risk.detach().cpu()),
        }


@dataclass(frozen=True)
class SmokeTrainingResult:
    initial_loss: float
    final_loss: float
    steps: int
    metrics: dict[str, float]
    checkpoint_path: str
    loss_history: tuple[float, ...]


def _part_class_targets(batch: GraphBatch, manifest: Any | None) -> torch.Tensor:
    targets = torch.zeros((batch.part_features.shape[0],), dtype=torch.long, device=batch.part_features.device)
    if manifest is None:
        return targets

    manifests: list[Any]
    if isinstance(manifest, Mapping):
        manifests = [manifest] * batch.part_features.shape[0]
    elif isinstance(manifest, Sequence) and not isinstance(manifest, str | bytes):
        manifests = list(manifest)
    else:
        raise AmgTrainingSmokeError("malformed_manifest", "manifest must be a mapping or sequence of mappings")
    if len(manifests) != batch.part_features.shape[0]:
        raise AmgTrainingSmokeError("manifest_batch_mismatch", "manifest count must match part batch size")

    for index, document in enumerate(manifests):
        if not isinstance(document, Mapping):
            raise AmgTrainingSmokeError("malformed_manifest", "manifest entries must be mappings")
        part = document.get("part", {})
        part_class = part.get("part_class") if isinstance(part, Mapping) else None
        if part_class is not None:
            try:
                targets[index] = PART_CLASSES.index(str(part_class))
            except ValueError as exc:
                raise AmgTrainingSmokeError("unknown_part_class", f"unsupported part_class: {part_class}") from exc
    return targets


def _feature_type_targets(candidate_features: torch.Tensor) -> torch.Tensor:
    raw_types = torch.round(candidate_features[:, FEATURE_TYPE_COLUMN]).to(dtype=torch.long)
    if raw_types.numel() and ((raw_types < 1) | (raw_types > len(FEATURE_TYPES))).any():
        raise AmgTrainingSmokeError("malformed_feature_type", "feature_type_id must be in the canonical 1..5 range")
    return raw_types - 1


def _feature_action_targets(action_mask: torch.Tensor) -> torch.Tensor:
    if action_mask.shape[0] == 0:
        raise AmgTrainingSmokeError("empty_candidate_batch", "at least one feature candidate is required")
    if action_mask.dtype is not torch.bool:
        action_mask = action_mask.to(dtype=torch.bool)
    empty_rows = ~action_mask.any(dim=1)
    if empty_rows.any():
        first = int(torch.nonzero(empty_rows, as_tuple=False)[0].item())
        raise AmgTrainingSmokeError("empty_action_mask", f"feature candidate row {first} has no allowed actions")
    return action_mask.to(dtype=torch.float32).argmax(dim=1).to(dtype=torch.long)


def build_smoke_targets(batch: GraphBatch, manifest: Any | None = None) -> SmokeTargets:
    """Build deterministic smoke targets from graph candidate rows and masks."""

    candidate_features = batch.feature_candidate_features
    if candidate_features.ndim != 2:
        raise AmgTrainingSmokeError("malformed_candidate_features", "candidate features must be a 2D tensor")
    if candidate_features.shape[0] == 0:
        raise AmgTrainingSmokeError("empty_candidate_batch", "at least one feature candidate is required")

    feature_type_targets = _feature_type_targets(candidate_features)
    feature_action_targets = _feature_action_targets(batch.action_mask)
    positive_sizes = torch.clamp(torch.abs(candidate_features[:, [SIZE_1_COLUMN, SIZE_2_COLUMN]]), min=1.0e-3)
    log_h_targets = torch.log(positive_sizes)
    mask_counts = batch.action_mask.to(dtype=torch.float32).sum(dim=1).clamp(min=1.0)
    clearance = torch.clamp(torch.abs(candidate_features[:, CLEARANCE_RATIO_COLUMN]), min=1.0)
    division_targets = torch.stack(
        [
            feature_type_targets.to(dtype=torch.float32) + 1.0,
            feature_action_targets.to(dtype=torch.float32) + 1.0,
            mask_counts + clearance,
        ],
        dim=1,
    )
    quality_risk_targets = torch.lt(candidate_features[:, [CLEARANCE_RATIO_COLUMN]], 1.0).to(dtype=torch.float32)
    return SmokeTargets(
        part_class_targets=_part_class_targets(batch, manifest),
        feature_type_targets=feature_type_targets,
        feature_action_targets=feature_action_targets,
        log_h_targets=log_h_targets,
        division_targets=division_targets,
        quality_risk_targets=quality_risk_targets,
    )


def compute_smoke_loss(output: AmgModelOutput, targets: SmokeTargets) -> SmokeLossBreakdown:
    """Compute a finite multi-head smoke loss for one model output."""

    masked_action_logits = apply_action_mask(output.feature_action_logits, output.action_mask)
    part_class_loss = F.cross_entropy(output.part_class_logits, targets.part_class_targets)
    feature_type_loss = F.cross_entropy(output.feature_type_logits, targets.feature_type_targets)
    feature_action_loss = F.cross_entropy(masked_action_logits, targets.feature_action_targets)
    log_h_loss = F.smooth_l1_loss(output.log_h, targets.log_h_targets)
    division_loss = F.smooth_l1_loss(output.division_values, targets.division_targets)
    quality_risk_loss = F.binary_cross_entropy_with_logits(output.quality_risk_logits, targets.quality_risk_targets)
    total = part_class_loss + feature_type_loss + feature_action_loss + log_h_loss + division_loss + quality_risk_loss
    if not torch.isfinite(total):
        raise AmgTrainingSmokeError("non_finite_loss", "smoke loss must be finite")
    return SmokeLossBreakdown(
        total=total,
        part_class=part_class_loss,
        feature_type=feature_type_loss,
        feature_action=feature_action_loss,
        log_h=log_h_loss,
        division=division_loss,
        quality_risk=quality_risk_loss,
    )


def save_smoke_checkpoint(
    path: str | Path,
    model: AmgGraphModel,
    optimizer: torch.optim.Optimizer,
    step: int,
    metrics: Mapping[str, float],
) -> None:
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "step": int(step),
            "metrics": dict(metrics),
        },
        checkpoint_path,
    )


def load_smoke_checkpoint(
    path: str | Path,
    model: AmgGraphModel,
    optimizer: torch.optim.Optimizer | None = None,
) -> dict[str, Any]:
    try:
        checkpoint = torch.load(Path(path), map_location="cpu", weights_only=False)
    except TypeError:
        checkpoint = torch.load(Path(path), map_location="cpu")
    if not isinstance(checkpoint, Mapping):
        raise AmgTrainingSmokeError("malformed_checkpoint", "checkpoint must contain a mapping payload")
    model.load_state_dict(checkpoint["model_state"])
    if optimizer is not None and "optimizer_state" in checkpoint:
        optimizer.load_state_dict(checkpoint["optimizer_state"])
    return dict(checkpoint)


def _parameter_delta_norm(initial_parameters: list[torch.Tensor], model: AmgGraphModel) -> float:
    total = 0.0
    index = 0
    for parameter in model.parameters():
        if not parameter.requires_grad:
            continue
        total += float(torch.norm(parameter.detach().cpu() - initial_parameters[index]).item())
        index += 1
    return total


def run_training_smoke(
    samples: Any,
    output_dir: str | Path,
    steps: int = 2,
    seed: int = 1234,
) -> SmokeTrainingResult:
    """Run a tiny deterministic optimizer loop and checkpoint round-trip."""

    if steps <= 0:
        raise AmgTrainingSmokeError("invalid_steps", "steps must be positive")
    torch.manual_seed(seed)
    batch = build_graph_batch(samples)
    targets = build_smoke_targets(batch)
    model = AmgGraphModel(ModelDimensions(part_feature_dim=batch.part_features.shape[1], hidden_dim=16))
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    initial_parameters = [parameter.detach().cpu().clone() for parameter in model.parameters() if parameter.requires_grad]

    loss_history: list[float] = []
    last_breakdown: SmokeLossBreakdown | None = None
    for _step in range(1, steps + 1):
        optimizer.zero_grad(set_to_none=True)
        output = model(batch)
        breakdown = compute_smoke_loss(output, targets)
        breakdown.total.backward()
        optimizer.step()
        last_breakdown = breakdown
        loss_value = float(breakdown.total.detach().cpu())
        if not math.isfinite(loss_value):
            raise AmgTrainingSmokeError("non_finite_loss", "smoke loss must be finite")
        loss_history.append(loss_value)

    if last_breakdown is None:
        raise AmgTrainingSmokeError("invalid_steps", "steps must be positive")
    metrics = last_breakdown.as_metrics()
    metrics["parameter_delta_norm"] = _parameter_delta_norm(initial_parameters, model)
    metrics["steps"] = float(steps)
    checkpoint_path = Path(output_dir) / "amg_training_smoke.pt"
    save_smoke_checkpoint(checkpoint_path, model, optimizer, steps, metrics)

    reload_model = AmgGraphModel(ModelDimensions(part_feature_dim=batch.part_features.shape[1], hidden_dim=16))
    load_smoke_checkpoint(checkpoint_path, reload_model)
    return SmokeTrainingResult(
        initial_loss=loss_history[0],
        final_loss=loss_history[-1],
        steps=steps,
        metrics=metrics,
        checkpoint_path=str(checkpoint_path),
        loss_history=tuple(loss_history),
    )
