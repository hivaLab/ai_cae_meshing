from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from training_pipeline.data.dataset import load_training_arrays


def load_model_artifact(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def predict_array(model: dict, x: np.ndarray) -> np.ndarray:
    mean = np.asarray(model["mean"], dtype=np.float64)
    std = np.asarray(model["std"], dtype=np.float64)
    weights = np.asarray(model["weights"], dtype=np.float64)
    xn = (x - mean) / std
    return np.column_stack([np.ones(len(xn)), xn]) @ weights


def evaluate_model(model_path: Path | str, dataset_dir: Path | str, split: str, output_dir: Path | str) -> dict:
    model = load_model_artifact(model_path)
    x, y, ids = load_training_arrays(dataset_dir, split)
    pred = predict_array(model, x)
    metrics = {
        "split": split,
        "sample_count": int(len(ids)),
        "mae": float(np.mean(np.abs(pred - y))) if len(ids) else 0.0,
        "rmse": float(np.sqrt(np.mean((pred - y) ** 2))) if len(ids) else 0.0,
        "recipe_size_within_20pct": float(np.mean(np.abs(pred - y) <= np.maximum(0.2 * y, 1e-9))) if len(ids) else 0.0,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate-brep-assembly-net")
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    metrics = evaluate_model(args.model, args.dataset, args.split, args.output)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
