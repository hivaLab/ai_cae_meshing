"""Training CLI for the primary direct AMG size-field GNN."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import torch
from torch import nn

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
) -> dict:
    if epochs <= 0:
        raise SizeFieldTrainingError("invalid_epochs", "epochs must be positive")
    torch.manual_seed(seed)
    samples = load_entity_samples(dataset_root, split=split)
    first_tensors = build_size_field_graph_tensors(samples[0])
    model = BrepSizeFieldModel(first_tensors.face_inputs.shape[1], first_tensors.edge_inputs.shape[1], hidden_dim=hidden_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=1.0e-3)
    last_loss = None
    target_rows = 0
    for _epoch in range(epochs):
        total = torch.tensor(0.0)
        count = 0
        for sample in samples:
            tensors = build_size_field_graph_tensors(sample)
            targets = build_size_field_targets(sample)
            output = model(tensors)
            loss = _loss(output, targets)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total = total + loss.detach()
            count += 1
            target_rows += int(torch.sum(targets.edge_mask).item() + torch.sum(targets.face_mask).item())
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
    metrics = {
        "status": "SUCCESS",
        "split": split,
        "sample_count": len(samples),
        "target_row_count": target_rows,
        "epochs": epochs,
        "final_loss": last_loss,
        "checkpoint": (out / "model.pt").as_posix(),
        "model": "BrepSizeFieldModel",
    }
    write_json(out / "metrics.json", metrics)
    return metrics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amg-train-size-field")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--hidden-dim", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        metrics = train_size_field_model(args.dataset, args.out, split=args.split, epochs=args.epochs, seed=args.seed, hidden_dim=args.hidden_dim)
    except (SizeFieldTrainingError, SizeFieldModelError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print(metrics)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
