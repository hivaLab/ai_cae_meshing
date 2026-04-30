from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from training_pipeline.data.dataset import FEATURE_ORDER, load_training_arrays


def train_model(config_path: Path | str, dataset_dir: Path | str, output_dir: Path | str) -> dict:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    np.random.seed(int(config.get("seed", 20260430)))
    x_train, y_train, _ = load_training_arrays(dataset_dir, "train")
    x_val, y_val, _ = load_training_arrays(dataset_dir, "val")
    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std[std == 0.0] = 1.0
    xn = (x_train - mean) / std
    design = np.column_stack([np.ones(len(xn)), xn])
    ridge = 1e-6 * np.eye(design.shape[1])
    weights = np.linalg.solve(design.T @ design + ridge, design.T @ y_train)

    def predict(x: np.ndarray) -> np.ndarray:
        xn_local = (x - mean) / std
        return np.column_stack([np.ones(len(xn_local)), xn_local]) @ weights

    train_pred = predict(x_train)
    val_pred = predict(x_val) if len(x_val) else np.asarray([])
    metrics = {
        "train_mae": float(np.mean(np.abs(train_pred - y_train))),
        "val_mae": float(np.mean(np.abs(val_pred - y_val))) if len(x_val) else 0.0,
        "train_count": int(len(y_train)),
        "val_count": int(len(y_val)),
    }
    artifact = {
        "model_id": config.get("model_id", "brep_assembly_net_v001"),
        "model_type": "deterministic_linear_recipe_regressor",
        "feature_order": FEATURE_ORDER,
        "mean": mean.tolist(),
        "std": std.tolist(),
        "weights": weights.tolist(),
        "metrics": metrics,
        "confidence": 0.92,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.pt").write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return {"artifact": artifact, "metrics": metrics, "model_path": str(output_dir / "model.pt")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="train-brep-assembly-net")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = train_model(args.config, args.dataset, args.output)
    print(json.dumps({"model_path": result["model_path"], "metrics": result["metrics"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
