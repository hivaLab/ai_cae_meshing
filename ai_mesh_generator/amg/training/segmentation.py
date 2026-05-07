"""Train the primary AMG v2 face/edge segmentation model."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

from ai_mesh_generator.amg.model.segmentation import (
    EDGE_SEGMENTATION_CLASSES,
    FACE_SEGMENTATION_CLASSES,
    BrepSegmentationModel,
    build_entity_graph_tensors,
    build_segmentation_targets,
)
from ai_mesh_generator.amg.training._entity_common import load_entity_samples, write_json


class SegmentationTrainingError(ValueError):
    pass


def _load_torch():
    try:
        import torch
        import torch.nn.functional as F
    except ModuleNotFoundError as exc:
        raise SegmentationTrainingError("torch is required for entity segmentation training") from exc
    return torch, F


def _class_weights(counts: np.ndarray) -> np.ndarray:
    weights = np.asarray([1.0 / math.sqrt(float(count) + 1.0) for count in counts], dtype=np.float32)
    return weights / max(float(weights.mean()), 1.0e-12)


def _segmentation_stats(confusion: np.ndarray, classes: tuple[str, ...]) -> dict:
    per_class = {}
    true_histogram = {}
    predicted_histogram = {}
    for index, label in enumerate(classes):
        tp = int(confusion[index, index])
        fp = int(confusion[:, index].sum() - tp)
        fn = int(confusion[index, :].sum() - tp)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2.0 * precision * recall / max(precision + recall, 1.0e-12)
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": int(confusion[index, :].sum())}
        true_histogram[label] = int(confusion[index, :].sum())
        predicted_histogram[label] = int(confusion[:, index].sum())
    return {
        "classes": list(classes),
        "confusion_matrix": confusion.astype(int).tolist(),
        "per_class": per_class,
        "true_histogram": true_histogram,
        "predicted_histogram": predicted_histogram,
    }


def _evaluate_segmentation_model(samples: list, model: BrepSegmentationModel, torch_module) -> dict:
    face_total = edge_total = face_correct = edge_correct = 0
    face_confusion = np.zeros((len(FACE_SEGMENTATION_CLASSES), len(FACE_SEGMENTATION_CLASSES)), dtype=np.int64)
    edge_confusion = np.zeros((len(EDGE_SEGMENTATION_CLASSES), len(EDGE_SEGMENTATION_CLASSES)), dtype=np.int64)
    with torch_module.no_grad():
        for sample in samples:
            tensors = build_entity_graph_tensors(sample)
            targets = build_segmentation_targets(sample)
            output = model(tensors)
            face_pred = output.face_logits.argmax(dim=-1)
            edge_pred = output.edge_logits.argmax(dim=-1)
            face_correct += int((face_pred == targets.face_labels).sum().item())
            edge_correct += int((edge_pred == targets.edge_labels).sum().item())
            face_total += int(targets.face_labels.numel())
            edge_total += int(targets.edge_labels.numel())
            for target, prediction in zip(targets.face_labels.cpu().numpy(), face_pred.cpu().numpy(), strict=True):
                face_confusion[int(target), int(prediction)] += 1
            for target, prediction in zip(targets.edge_labels.cpu().numpy(), edge_pred.cpu().numpy(), strict=True):
                edge_confusion[int(target), int(prediction)] += 1
    return {
        "face_accuracy": float(face_correct / max(face_total, 1)),
        "edge_accuracy": float(edge_correct / max(edge_total, 1)),
        "face_metrics": _segmentation_stats(face_confusion, FACE_SEGMENTATION_CLASSES),
        "edge_metrics": _segmentation_stats(edge_confusion, EDGE_SEGMENTATION_CLASSES),
    }


def train_entity_segmentation_from_dataset(
    dataset_root: str | Path,
    output_dir: str | Path,
    *,
    split: str | None = None,
    eval_split: str | None = None,
    epochs: int = 5,
    hidden_dim: int = 64,
    lr: float = 1e-3,
    seed: int = 1,
    edge_loss_multiplier: float = 2.0,
) -> dict:
    torch, F = _load_torch()
    torch.manual_seed(seed)
    samples = load_entity_samples(dataset_root, split=split)
    first = build_entity_graph_tensors(samples[0])
    model = BrepSegmentationModel(first.face_features.shape[1], first.edge_features.shape[1], hidden_dim=hidden_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    face_counts = np.zeros((len(FACE_SEGMENTATION_CLASSES),), dtype=np.int64)
    edge_counts = np.zeros((len(EDGE_SEGMENTATION_CLASSES),), dtype=np.int64)
    for sample in samples:
        targets = build_segmentation_targets(sample)
        face_counts += np.bincount(targets.face_labels.numpy(), minlength=len(FACE_SEGMENTATION_CLASSES))
        edge_counts += np.bincount(targets.edge_labels.numpy(), minlength=len(EDGE_SEGMENTATION_CLASSES))
    face_weights = torch.as_tensor(_class_weights(face_counts), dtype=torch.float32)
    edge_weights = torch.as_tensor(_class_weights(edge_counts), dtype=torch.float32)
    losses: list[float] = []
    for _ in range(epochs):
        epoch_loss = 0.0
        for sample in samples:
            tensors = build_entity_graph_tensors(sample)
            targets = build_segmentation_targets(sample)
            output = model(tensors)
            loss = F.cross_entropy(output.face_logits, targets.face_labels, weight=face_weights) + edge_loss_multiplier * F.cross_entropy(
                output.edge_logits,
                targets.edge_labels,
                weight=edge_weights,
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach().cpu())
        losses.append(epoch_loss / len(samples))

    train_eval = _evaluate_segmentation_model(samples, model, torch)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "face_feature_dim": first.face_features.shape[1],
            "edge_feature_dim": first.edge_features.shape[1],
            "hidden_dim": hidden_dim,
            "face_classes": FACE_SEGMENTATION_CLASSES,
            "edge_classes": EDGE_SEGMENTATION_CLASSES,
        },
        out / "model.pt",
    )
    metrics = {
        "schema": "AMG_ENTITY_SEGMENTATION_METRICS_V1",
        "dataset_root": Path(dataset_root).as_posix(),
        "split": split,
        "sample_count": len(samples),
        "epochs": epochs,
        "loss_history": losses,
        "final_loss": losses[-1] if losses else None,
        "face_accuracy": train_eval["face_accuracy"],
        "edge_accuracy": train_eval["edge_accuracy"],
        "face_classes": list(FACE_SEGMENTATION_CLASSES),
        "edge_classes": list(EDGE_SEGMENTATION_CLASSES),
        "face_class_weights": {label: float(face_weights[index].item()) for index, label in enumerate(FACE_SEGMENTATION_CLASSES)},
        "edge_class_weights": {label: float(edge_weights[index].item()) for index, label in enumerate(EDGE_SEGMENTATION_CLASSES)},
        "edge_loss_multiplier": edge_loss_multiplier,
        "face_metrics": train_eval["face_metrics"],
        "edge_metrics": train_eval["edge_metrics"],
        "model_path": (out / "model.pt").as_posix(),
    }
    if eval_split:
        eval_samples = load_entity_samples(dataset_root, split=eval_split)
        eval_metrics = {
            "schema": "AMG_ENTITY_SEGMENTATION_EVAL_METRICS_V1",
            "split": eval_split,
            "sample_count": len(eval_samples),
            **_evaluate_segmentation_model(eval_samples, model, torch),
        }
        metrics["evaluation"] = eval_metrics
        write_json(out / "eval_metrics.json", eval_metrics)
    if not np.isfinite(metrics["final_loss"]):
        raise SegmentationTrainingError("non-finite segmentation loss")
    write_json(out / "metrics.json", metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amg-train-entity-segmentation")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split")
    parser.add_argument("--eval-split")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--edge-loss-multiplier", type=float, default=2.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metrics = train_entity_segmentation_from_dataset(
            args.dataset,
            args.out,
            split=args.split,
            eval_split=args.eval_split,
            epochs=args.epochs,
            hidden_dim=args.hidden_dim,
            lr=args.lr,
            seed=args.seed,
            edge_loss_multiplier=args.edge_loss_multiplier,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "metrics_path": str(Path(args.out) / "metrics.json"), "final_loss": metrics["final_loss"]})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
