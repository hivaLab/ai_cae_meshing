"""Quality-aware AMG training from CDF quality exploration evidence."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from ai_mesh_generator.amg.dataset import AmgDatasetSample, load_amg_dataset_sample, load_dataset_index
from ai_mesh_generator.amg.quality_features import build_quality_feature_vector


class AmgQualityTrainingError(ValueError):
    """Raised when quality-aware training cannot proceed safely."""

    def __init__(self, code: str, message: str, path: str | Path | None = None) -> None:
        self.code = code
        self.path = Path(path) if path is not None else None
        prefix = code if path is None else f"{code} [{Path(path).as_posix()}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class QualityTrainingConfig:
    dataset_root: Path
    quality_exploration_root: Path
    output_dir: Path
    epochs: int = 10
    batch_size: int = 32
    seed: int = 708
    learning_rate: float = 1.0e-3
    hidden_dim: int = 32


@dataclass(frozen=True)
class QualityTrainingResult:
    status: str
    checkpoint_path: str
    metrics_path: str
    training_config_path: str
    metrics: dict[str, Any]


class QualityControlRanker(nn.Module):
    """Small lower-is-better quality score regressor for graph/control pairs."""

    def __init__(self, input_dim: int, hidden_dim: int = 32) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features).squeeze(-1)


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AmgQualityTrainingError(code, f"could not read {path}", path) from exc
    except json.JSONDecodeError as exc:
        raise AmgQualityTrainingError("json_parse_failed", f"could not parse {path}", path) from exc
    if not isinstance(loaded, dict):
        raise AmgQualityTrainingError("json_document_not_object", "JSON document must be an object", path)
    return loaded


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _accepted_sample_dirs(dataset_root: Path) -> dict[str, Path]:
    index = load_dataset_index(dataset_root)
    result: dict[str, Path] = {}
    for record in index.get("accepted_samples", []):
        if isinstance(record, str):
            sample_id = record
            result[sample_id] = dataset_root / "samples" / sample_id
        elif isinstance(record, Mapping):
            sample_id = record.get("sample_id")
            if isinstance(sample_id, str):
                sample_dir = record.get("sample_dir", f"samples/{sample_id}")
                result[sample_id] = dataset_root / str(sample_dir)
    return result


def _split_ids(dataset_root: Path, split: str) -> set[str]:
    path = dataset_root / "splits" / f"{split}.txt"
    if not path.is_file():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _resolve_path(path_text: str, quality_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute() or path.exists():
        return path
    candidate = quality_root / path
    return candidate if candidate.exists() else path


def _quality_summary_path(root: Path) -> Path:
    path = root / "quality_exploration_summary.json"
    if path.is_file():
        return path
    if root.is_file():
        return root
    raise AmgQualityTrainingError("missing_quality_exploration_summary", "quality exploration summary not found", root)


def _load_examples(dataset_root: Path, quality_root: Path) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    summary = _read_json(_quality_summary_path(quality_root), "quality_summary_read_failed")
    records = summary.get("records", [])
    if not isinstance(records, list):
        raise AmgQualityTrainingError("malformed_quality_summary", "records must be a list", quality_root)
    sample_dirs = _accepted_sample_dirs(dataset_root)
    examples: list[dict[str, Any]] = []
    sample_cache: dict[str, AmgDatasetSample] = {}
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("quality_score"), (int, float)):
            continue
        sample_id = record.get("sample_id")
        manifest_path = record.get("manifest_path")
        if not isinstance(sample_id, str) or sample_id not in sample_dirs or not isinstance(manifest_path, str):
            continue
        if sample_id not in sample_cache:
            sample_cache[sample_id] = load_amg_dataset_sample(sample_dirs[sample_id])
        manifest = _read_json(_resolve_path(manifest_path, quality_root), "manifest_read_failed")
        examples.append(
            {
                "sample_id": sample_id,
                "evaluation_id": str(record.get("evaluation_id", "")),
                "features": build_quality_feature_vector(sample_cache[sample_id], manifest),
                "quality_score": float(record["quality_score"]),
            }
        )
    if not examples:
        raise AmgQualityTrainingError("empty_quality_examples", "no quality-scored examples were found", quality_root)
    return examples, sample_dirs


def _split_examples(dataset_root: Path, examples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    train_ids = _split_ids(dataset_root, "train")
    val_ids = _split_ids(dataset_root, "val")
    if train_ids and val_ids:
        train = [example for example in examples if example["sample_id"] in train_ids]
        val = [example for example in examples if example["sample_id"] in val_ids]
        if train and val:
            return train, val, "dataset_splits"
    sample_ids = sorted({example["sample_id"] for example in examples})
    split = max(1, int(0.8 * len(sample_ids)))
    train_id_set = set(sample_ids[:split])
    train = [example for example in examples if example["sample_id"] in train_id_set]
    val = [example for example in examples if example["sample_id"] not in train_id_set]
    if not val:
        val = train[-1:]
        train = train[:-1] or val
    return train, val, "deterministic_80_20_fallback"


def _pair_indices(examples: Sequence[dict[str, Any]]) -> list[tuple[int, int]]:
    by_sample: dict[str, list[int]] = defaultdict(list)
    for index, example in enumerate(examples):
        by_sample[str(example["sample_id"])].append(index)
    pairs: list[tuple[int, int]] = []
    for indices in by_sample.values():
        for left_pos, left in enumerate(indices):
            for right in indices[left_pos + 1 :]:
                if not math.isclose(float(examples[left]["quality_score"]), float(examples[right]["quality_score"])):
                    pairs.append((left, right))
    return pairs


def _tensor(examples: Sequence[dict[str, Any]]) -> torch.Tensor:
    return torch.as_tensor(np.stack([example["features"] for example in examples]), dtype=torch.float32)


def _quality_targets(examples: Sequence[dict[str, Any]]) -> torch.Tensor:
    return torch.as_tensor([float(example["quality_score"]) for example in examples], dtype=torch.float32)


def _ranking_loss(predictions: torch.Tensor, scores: torch.Tensor, pairs: Sequence[tuple[int, int]]) -> torch.Tensor:
    if not pairs:
        raise AmgQualityTrainingError("empty_pairwise_targets", "quality training requires at least one unequal quality pair")
    logits: list[torch.Tensor] = []
    targets: list[float] = []
    for left, right in pairs:
        logits.append(predictions[right] - predictions[left])
        targets.append(1.0 if float(scores[left]) < float(scores[right]) else 0.0)
    return F.binary_cross_entropy_with_logits(torch.stack(logits), torch.as_tensor(targets, dtype=torch.float32, device=predictions.device))


def _ranking_accuracy(predictions: torch.Tensor, scores: torch.Tensor, pairs: Sequence[tuple[int, int]]) -> float:
    if not pairs:
        return 0.0
    correct = 0
    for left, right in pairs:
        predicted_left_better = float(predictions[left]) < float(predictions[right])
        true_left_better = float(scores[left]) < float(scores[right])
        if predicted_left_better == true_left_better:
            correct += 1
    return correct / len(pairs)


def run_quality_training(config: QualityTrainingConfig) -> QualityTrainingResult:
    if config.epochs <= 0:
        raise AmgQualityTrainingError("invalid_epochs", "epochs must be positive")
    torch.manual_seed(config.seed)
    random.seed(config.seed)
    examples, _sample_dirs = _load_examples(config.dataset_root, config.quality_exploration_root)
    train_examples, val_examples, split_source = _split_examples(config.dataset_root, examples)
    train_pairs = _pair_indices(train_examples)
    val_pairs = _pair_indices(val_examples)
    if not train_pairs:
        raise AmgQualityTrainingError("empty_pairwise_targets", "train split has no unequal quality pairs")

    input_dim = int(train_examples[0]["features"].shape[0])
    model = QualityControlRanker(input_dim=input_dim, hidden_dim=config.hidden_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    train_x = _tensor(train_examples)
    train_scores = _quality_targets(train_examples)
    rng = random.Random(config.seed)
    for _epoch in range(config.epochs):
        order = list(train_pairs)
        rng.shuffle(order)
        model.train()
        optimizer.zero_grad(set_to_none=True)
        predictions = model(train_x)
        loss = _ranking_loss(predictions, train_scores, order)
        if not torch.isfinite(loss):
            raise AmgQualityTrainingError("non_finite_loss", "quality ranking loss became non-finite")
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        train_predictions = model(train_x)
        train_loss = _ranking_loss(train_predictions, train_scores, train_pairs)
        train_accuracy = _ranking_accuracy(train_predictions, train_scores, train_pairs)
        val_x = _tensor(val_examples)
        val_scores = _quality_targets(val_examples)
        val_predictions = model(val_x)
        val_loss = _ranking_loss(val_predictions, val_scores, val_pairs) if val_pairs else torch.tensor(0.0)
        val_accuracy = _ranking_accuracy(val_predictions, val_scores, val_pairs)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = config.output_dir / "quality_ranker_checkpoint.pt"
    metrics_path = config.output_dir / "quality_training_metrics.json"
    training_config_path = config.output_dir / "quality_training_config.json"
    torch.save(
        {
            "model_state": model.state_dict(),
            "input_dim": input_dim,
            "hidden_dim": config.hidden_dim,
            "metrics_path": metrics_path.as_posix(),
        },
        checkpoint_path,
    )
    metrics: dict[str, Any] = {
        "schema": "AMG_QUALITY_TRAINING_METRICS_V1",
        "status": "SUCCESS",
        "dataset_root": config.dataset_root.as_posix(),
        "quality_exploration_root": config.quality_exploration_root.as_posix(),
        "example_count": len(examples),
        "train_example_count": len(train_examples),
        "validation_example_count": len(val_examples),
        "train_pair_count": len(train_pairs),
        "validation_pair_count": len(val_pairs),
        "train_pairwise_loss": float(train_loss),
        "validation_pairwise_loss": float(val_loss),
        "train_pairwise_accuracy": float(train_accuracy),
        "validation_pairwise_accuracy": float(val_accuracy),
        "quality_score_variance": float(statistics.pvariance([example["quality_score"] for example in examples])) if len(examples) > 1 else 0.0,
        "split_source": split_source,
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "seed": config.seed,
        "learning_rate": config.learning_rate,
        "hidden_dim": config.hidden_dim,
        "checkpoint_path": checkpoint_path.as_posix(),
    }
    _write_json(training_config_path, {
        "dataset_root": config.dataset_root.as_posix(),
        "quality_exploration_root": config.quality_exploration_root.as_posix(),
        "output_dir": config.output_dir.as_posix(),
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "seed": config.seed,
        "learning_rate": config.learning_rate,
        "hidden_dim": config.hidden_dim,
    })
    _write_json(metrics_path, metrics)
    return QualityTrainingResult(
        status="SUCCESS",
        checkpoint_path=checkpoint_path.as_posix(),
        metrics_path=metrics_path.as_posix(),
        training_config_path=training_config_path.as_posix(),
        metrics=metrics,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train AMG quality-control ranker from real ANSA exploration evidence.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--quality-exploration", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=708)
    parser.add_argument("--learning-rate", type=float, default=1.0e-3)
    parser.add_argument("--hidden-dim", type=int, default=32)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_quality_training(
            QualityTrainingConfig(
                dataset_root=Path(args.dataset),
                quality_exploration_root=Path(args.quality_exploration),
                output_dir=Path(args.out),
                epochs=args.epochs,
                batch_size=args.batch_size,
                seed=args.seed,
                learning_rate=args.learning_rate,
                hidden_dim=args.hidden_dim,
            )
        )
    except AmgQualityTrainingError as exc:
        print(json.dumps({"status": "FAILED", "error_code": exc.code, "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"status": result.status, **result.metrics}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
