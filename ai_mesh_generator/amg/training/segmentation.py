"""Train the primary AMG v2 face/edge segmentation model."""

from __future__ import annotations

import argparse
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


def train_entity_segmentation_from_dataset(
    dataset_root: str | Path,
    output_dir: str | Path,
    *,
    split: str | None = None,
    epochs: int = 5,
    hidden_dim: int = 64,
    lr: float = 1e-3,
    seed: int = 1,
) -> dict:
    torch, F = _load_torch()
    torch.manual_seed(seed)
    samples = load_entity_samples(dataset_root, split=split)
    first = build_entity_graph_tensors(samples[0])
    model = BrepSegmentationModel(first.face_features.shape[1], first.edge_features.shape[1], hidden_dim=hidden_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    losses: list[float] = []
    for _ in range(epochs):
        epoch_loss = 0.0
        for sample in samples:
            tensors = build_entity_graph_tensors(sample)
            targets = build_segmentation_targets(sample)
            output = model(tensors)
            loss = F.cross_entropy(output.face_logits, targets.face_labels) + F.cross_entropy(output.edge_logits, targets.edge_labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach().cpu())
        losses.append(epoch_loss / len(samples))

    face_total = edge_total = face_correct = edge_correct = 0
    with torch.no_grad():
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
        "face_accuracy": float(face_correct / max(face_total, 1)),
        "edge_accuracy": float(edge_correct / max(edge_total, 1)),
        "face_classes": list(FACE_SEGMENTATION_CLASSES),
        "edge_classes": list(EDGE_SEGMENTATION_CLASSES),
        "model_path": (out / "model.pt").as_posix(),
    }
    if not np.isfinite(metrics["final_loss"]):
        raise SegmentationTrainingError("non-finite segmentation loss")
    write_json(out / "metrics.json", metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amg-train-entity-segmentation")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metrics = train_entity_segmentation_from_dataset(args.dataset, args.out, split=args.split, epochs=args.epochs, hidden_dim=args.hidden_dim, lr=args.lr, seed=args.seed)
    except Exception as exc:  # noqa: BLE001 - CLI boundary.
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "metrics_path": str(Path(args.out) / "metrics.json"), "final_loss": metrics["final_loss"]})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
