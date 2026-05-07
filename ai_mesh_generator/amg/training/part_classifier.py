"""Train the primary AMG v2 part classifier."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np

from ai_mesh_generator.amg.model.part_classifier import (
    PART_CLASS_ORDER,
    PartClassifierError,
    predict_part_class,
    save_part_classifier,
    train_part_classifier,
)
from ai_mesh_generator.amg.training._entity_common import load_entity_samples, write_json


def _confusion_matrix(labels: list[str], predictions: list[str]) -> dict[str, dict[str, int]]:
    matrix = {truth: {pred: 0 for pred in PART_CLASS_ORDER} for truth in PART_CLASS_ORDER}
    for truth, pred in zip(labels, predictions, strict=True):
        matrix[truth][pred] += 1
    return matrix


def train_part_classifier_from_dataset(
    dataset_root: str | Path,
    output_dir: str | Path,
    *,
    split: str | None = None,
    eval_split: str | None = None,
    seed: int = 1,
    n_estimators: int = 300,
    uncertainty_threshold: float = 0.60,
) -> dict:
    samples = load_entity_samples(dataset_root, split=split)
    model, metadata = train_part_classifier(samples, seed=seed, n_estimators=n_estimators)
    labels = [sample.labels.part_class["part_class"] for sample in samples]
    predictions = [predict_part_class(model, sample, uncertainty_threshold=uncertainty_threshold) for sample in samples]
    pred_labels = [item.part_class for item in predictions]
    confidences = [item.confidence for item in predictions]
    uncertain_count = sum(1 for item in predictions if item.uncertain)
    out = Path(output_dir)
    save_part_classifier(out / "model.pkl", model, metadata)
    metrics = {
        "schema": "AMG_PART_CLASSIFIER_METRICS_V1",
        "dataset_root": Path(dataset_root).as_posix(),
        "split": split,
        "sample_count": len(samples),
        "class_order": list(PART_CLASS_ORDER),
        "label_counts": dict(Counter(labels)),
        "training_accuracy": float(np.mean(np.asarray(labels) == np.asarray(pred_labels))),
        "mean_confidence": float(np.mean(confidences)),
        "uncertainty_threshold": uncertainty_threshold,
        "uncertain_count": int(uncertain_count),
        "model_path": (out / "model.pkl").as_posix(),
    }
    if eval_split:
        eval_samples = load_entity_samples(dataset_root, split=eval_split)
        eval_labels = [sample.labels.part_class["part_class"] for sample in eval_samples]
        eval_predictions = [predict_part_class(model, sample, uncertainty_threshold=uncertainty_threshold) for sample in eval_samples]
        eval_pred_labels = [item.part_class for item in eval_predictions]
        eval_confidences = [item.confidence for item in eval_predictions]
        eval_uncertain_count = sum(1 for item in eval_predictions if item.uncertain)
        eval_metrics = {
            "schema": "AMG_PART_CLASSIFIER_EVAL_METRICS_V1",
            "split": eval_split,
            "sample_count": len(eval_samples),
            "label_counts": dict(Counter(eval_labels)),
            "accuracy": float(np.mean(np.asarray(eval_labels) == np.asarray(eval_pred_labels))),
            "mean_confidence": float(np.mean(eval_confidences)),
            "uncertain_count": int(eval_uncertain_count),
        }
        metrics["evaluation"] = eval_metrics
        write_json(out / "eval_metrics.json", eval_metrics)
        write_json(out / "eval_confusion_matrix.json", {"schema": "AMG_PART_CLASSIFIER_CONFUSION_V1", "split": eval_split, "matrix": _confusion_matrix(eval_labels, eval_pred_labels)})
    write_json(out / "metrics.json", metrics)
    write_json(out / "confusion_matrix.json", {"schema": "AMG_PART_CLASSIFIER_CONFUSION_V1", "matrix": _confusion_matrix(labels, pred_labels)})
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amg-train-part-classifier")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--split")
    parser.add_argument("--eval-split")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--uncertainty-threshold", type=float, default=0.60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metrics = train_part_classifier_from_dataset(
            args.dataset,
            args.out,
            split=args.split,
            eval_split=args.eval_split,
            seed=args.seed,
            n_estimators=args.n_estimators,
            uncertainty_threshold=args.uncertainty_threshold,
        )
    except (PartClassifierError, ValueError) as exc:
        print({"status": "FAILED", "message": str(exc)})
        return 1
    print({"status": "SUCCESS", "metrics_path": str(Path(args.out) / "metrics.json"), "sample_count": metrics["sample_count"]})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
