"""Training CLI for the primary direct AMG size-field GNN."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Sequence

import torch
from torch import nn

from ai_mesh_generator.amg.model.part_classifier import PART_CLASS_ORDER, load_part_classifier, predict_part_class
from ai_mesh_generator.amg.model.segmentation import load_segmentation_model, predict_entity_segmentation_probabilities
from ai_mesh_generator.amg.model.size_field import (
    BrepSizeFieldModel,
    SizeFieldModelError,
    build_size_field_graph_tensors,
    build_size_field_targets,
)
from ai_mesh_generator.amg.training._entity_common import load_entity_samples, write_json


class SizeFieldTrainingError(ValueError):
    """Raised when direct size-field training cannot produce a real model artifact."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _loss(output, targets) -> torch.Tensor:  # noqa: ANN001
    losses: list[torch.Tensor] = []
    if torch.any(targets.edge_mask):
        losses.append(nn.functional.smooth_l1_loss(output.edge_log_h[targets.edge_mask], targets.edge_log_h[targets.edge_mask]))
    if torch.any(targets.face_mask):
        losses.append(nn.functional.smooth_l1_loss(output.face_log_h[targets.face_mask], targets.face_log_h[targets.face_mask]))
    if not losses:
        raise SizeFieldTrainingError("missing_size_targets", "no edge or face size targets are available")
    return sum(losses)


def train_size_field_model(
    dataset_root: str | Path,
    output_dir: str | Path,
    *,
    split: str | None = None,
    epochs: int = 10,
    seed: int = 1,
    hidden_dim: int = 64,
    prefer_quality_evidence: bool = False,
    part_classifier_path: str | Path | None = None,
    segmentation_checkpoint_path: str | Path | None = None,
    use_predicted_context: bool = False,
) -> dict:
    if epochs <= 0:
        raise SizeFieldTrainingError("invalid_epochs", "epochs must be positive")
    torch.manual_seed(seed)
    samples = load_entity_samples(dataset_root, split=split, require_quality=False)
    part_model = segmentation_model = None
    if use_predicted_context:
        if part_classifier_path is None:
            raise SizeFieldTrainingError("missing_part_classifier", "predicted-context size training requires --part-classifier")
        if segmentation_checkpoint_path is None:
            raise SizeFieldTrainingError("missing_segmentation_checkpoint", "predicted-context size training requires --segmentation-checkpoint")
        part_model, _metadata = load_part_classifier(part_classifier_path)
        segmentation_model = load_segmentation_model(segmentation_checkpoint_path)
    first_tensors = _graph_tensors_for_training(samples[0], part_model=part_model, segmentation_model=segmentation_model, use_predicted_context=use_predicted_context)
    model = BrepSizeFieldModel(first_tensors.face_inputs.shape[1], first_tensors.edge_inputs.shape[1], hidden_dim=hidden_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    last_loss = None
    target_rows = 0
    skipped_samples: set[str] = set()
    metric_edge_targets: list[float] = []
    metric_h_min_values: list[float] = []
    for epoch in range(epochs):
        total = torch.tensor(0.0)
        count = 0
        for sample in samples:
            tensors = _graph_tensors_for_training(sample, part_model=part_model, segmentation_model=segmentation_model, use_predicted_context=use_predicted_context)
            try:
                targets = build_size_field_targets(sample, prefer_quality_evidence=prefer_quality_evidence)
            except SizeFieldModelError as exc:
                if prefer_quality_evidence and exc.code in {"missing_quality_evidence", "missing_quality_edge_targets", "missing_edge_size_targets"}:
                    skipped_samples.add(sample.sample_id)
                    continue
                raise
            output = model(tensors)
            loss = _loss(output, targets)
            if epoch == 0:
                edge_values = torch.exp(targets.edge_log_h[targets.edge_mask]).detach().cpu().tolist()
                metric_edge_targets.extend(float(value) for value in edge_values)
                global_mesh = sample.labels.mesh_size_field.get("global_mesh", {}) if hasattr(sample, "labels") else {}
                h_min = float(global_mesh.get("h_min_mm", 0.5)) if isinstance(global_mesh, dict) else 0.5
                metric_h_min_values.extend([h_min] * len(edge_values))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total = total + loss.detach()
            count += 1
            target_rows += int(torch.sum(targets.edge_mask).item() + torch.sum(targets.face_mask).item())
        if count == 0:
            raise SizeFieldTrainingError("missing_usable_quality_targets", "no samples with usable quality size targets were available")
        last_loss = float((total / max(count, 1)).item())
        if not torch.isfinite(torch.tensor(last_loss)):
            raise SizeFieldTrainingError("non_finite_loss", "training produced a non-finite loss")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "face_input_dim": first_tensors.face_inputs.shape[1],
        "edge_input_dim": first_tensors.edge_inputs.shape[1],
        "hidden_dim": hidden_dim,
        "seed": seed,
    }
    torch.save(checkpoint, out / "model.pt")
    edge_target_stats = _edge_target_stats(metric_edge_targets, metric_h_min_values)
    learning_signal_status = "SUCCESS"
    if edge_target_stats["count"] == 0 or edge_target_stats["h_min_edge_fraction"] >= 1.0 or edge_target_stats["std"] <= 1.0e-9:
        learning_signal_status = "FAILED_LEARNING_SIGNAL"
    metrics = {
        "status": "SUCCESS",
        "learning_signal_status": learning_signal_status,
        "split": split,
        "sample_count": len(samples),
        "trained_sample_count": len(samples) - len(skipped_samples),
        "skipped_sample_count": len(skipped_samples),
        "skipped_samples": sorted(skipped_samples),
        "target_row_count": target_rows,
        "epochs": epochs,
        "final_loss": last_loss,
        "checkpoint": (out / "model.pt").as_posix(),
        "model": "BrepSizeFieldModel",
        "prefer_quality_evidence": prefer_quality_evidence,
        "use_predicted_context": use_predicted_context,
        "part_classifier_path": Path(part_classifier_path).as_posix() if part_classifier_path is not None else None,
        "segmentation_checkpoint_path": Path(segmentation_checkpoint_path).as_posix() if segmentation_checkpoint_path is not None else None,
        "edge_target_size_stats": edge_target_stats,
    }
    write_json(out / "metrics.json", metrics)
    return metrics


def _graph_tensors_for_training(sample, *, part_model, segmentation_model, use_predicted_context: bool):  # noqa: ANN001
    if not use_predicted_context:
        return build_size_field_graph_tensors(sample)
    part_prediction = predict_part_class(part_model, sample, uncertainty_threshold=0.0)
    part_probabilities = torch.zeros((len(PART_CLASS_ORDER),), dtype=torch.float32).numpy()
    for index, label in enumerate(PART_CLASS_ORDER):
        part_probabilities[index] = float(part_prediction.probabilities[label])
    face_probs, edge_probs = predict_entity_segmentation_probabilities(sample, segmentation_model)
    return build_size_field_graph_tensors(
        sample,
        face_segmentation_probabilities=face_probs,
        edge_segmentation_probabilities=edge_probs,
        part_probabilities=part_probabilities,
        use_label_segmentation=False,
    )


def _edge_target_stats(values: list[float], h_min_values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "min": 0.0, "mean": 0.0, "max": 0.0, "std": 0.0, "h_min_edge_fraction": 1.0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    h_min_count = 0
    for value, h_min in zip(values, h_min_values, strict=True):
        if abs(value - h_min) <= max(1.0e-9, h_min * 1.0e-6):
            h_min_count += 1
    return {
        "count": len(values),
        "min": min(values),
        "mean": mean,
        "max": max(values),
        "std": math.sqrt(variance),
        "h_min_edge_fraction": h_min_count / len(values),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg-train-size-field")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--prefer-quality-evidence", action="store_true")
    parser.add_argument("--part-classifier")
    parser.add_argument("--segmentation-checkpoint")
    parser.add_argument("--use-predicted-context", action="store_true")
    args = parser.parse_args(argv)
    try:
        metrics = train_size_field_model(
            args.dataset,
            args.out,
            split=args.split,
            epochs=args.epochs,
            seed=args.seed,
            hidden_dim=args.hidden_dim,
            prefer_quality_evidence=args.prefer_quality_evidence,
            part_classifier_path=args.part_classifier,
            segmentation_checkpoint_path=args.segmentation_checkpoint,
            use_predicted_context=args.use_predicted_context,
        )
    except (SizeFieldTrainingError, SizeFieldModelError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print(metrics)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
