from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
import yaml

from training_pipeline.data.collate import collate_graph_batch
from training_pipeline.data.dataset import BRepAssemblyDataset
from training_pipeline.data.dataset import (
    CONNECTION_CLASSES,
    EDGE_SEMANTIC_CLASSES,
    FACE_SEMANTIC_CLASSES,
    PART_STRATEGY_CLASSES,
    REPAIR_ACTION_CLASSES,
)
from training_pipeline.data.normalization import compute_node_feature_stats, normalize_graph_batch, normalize_size_targets
from training_pipeline.losses.multitask_loss import multitask_loss
from training_pipeline.models.brep_assembly_net import BRepAssemblyNet


def train_model(config_path: Path | str, dataset_dir: Path | str, output_dir: Path | str) -> dict:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    seed = int(config.get("seed", 20260430))
    epochs = int(config.get("epochs", 20))
    learning_rate = float(config.get("learning_rate", 0.01))
    hidden_dim = int(config.get("hidden_dim", 64))
    num_layers = int(config.get("num_layers", 3))
    _set_deterministic_seed(seed)

    train_batch = _load_split_batch(dataset_dir, "train")
    val_batch = _load_split_batch(dataset_dir, "val")
    node_feature_stats = compute_node_feature_stats(train_batch["graph"])
    target_mean = float(torch.mean(train_batch["size_field"]).item())
    target_std = float(torch.std(train_batch["size_field"]).item())
    if target_std == 0.0:
        target_std = 1.0
    train_batch = _prepare_batch(train_batch, node_feature_stats, target_mean, target_std)
    val_batch = _prepare_batch(val_batch, node_feature_stats, target_mean, target_std)

    model = BRepAssemblyNet(
        node_input_dims=_node_input_dims(train_batch["graph"]),
        edge_types=list(train_batch["graph"]["edge_index"]),
        hidden_dim=hidden_dim,
        num_layers=num_layers,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    history: list[dict[str, float]] = []
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        outputs = model(train_batch["graph"])
        loss = multitask_loss(outputs, train_batch)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            val_outputs = model(val_batch["graph"])
            val_loss = multitask_loss(val_outputs, val_batch)
        history.append({"epoch": float(epoch + 1), "train_loss": float(loss.item()), "val_loss": float(val_loss.item())})

    model.eval()
    with torch.no_grad():
        train_metrics = _metrics(model(train_batch["graph"]), train_batch, "train", target_mean, target_std)
        val_metrics = _metrics(model(val_batch["graph"]), val_batch, "val", target_mean, target_std)
    metrics = {
        **train_metrics,
        **val_metrics,
        "train_count": int(train_batch["graph"]["num_graphs"]),
        "val_count": int(val_batch["graph"]["num_graphs"]),
        "final_train_loss": history[-1]["train_loss"],
        "final_val_loss": history[-1]["val_loss"],
    }

    artifact = {
        "model_id": config.get("model_id", "brep_assembly_net_v001"),
        "model_type": "hetero_brep_assembly_net",
        "framework": "torch",
        "node_input_dims": _node_input_dims(train_batch["graph"]),
        "node_feature_names": train_batch["graph"].get("node_feature_names", {}),
        "edge_types": list(train_batch["graph"]["edge_index"]),
        "hidden_dim": hidden_dim,
        "num_layers": num_layers,
        "node_feature_stats": node_feature_stats,
        "target_mean": target_mean,
        "target_std": target_std,
        "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
        "heads": _head_schema(),
        "metrics": metrics,
        "training_history": history,
        "confidence": _confidence_from_metrics(metrics),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(artifact, output_dir / "model.pt")
    (output_dir / "model_manifest.json").write_text(json.dumps(_jsonable_artifact(artifact), indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return {"artifact": artifact, "metrics": metrics, "model_path": str(output_dir / "model.pt")}


def _load_split_batch(dataset_dir: Path | str, split: str) -> dict[str, object]:
    dataset = BRepAssemblyDataset(dataset_dir, split)
    if len(dataset) == 0:
        raise ValueError(f"dataset split {split!r} is empty")
    return collate_graph_batch([dataset[index] for index in range(len(dataset))])


def _prepare_batch(batch: dict[str, object], node_feature_stats: dict, target_mean: float, target_std: float) -> dict[str, object]:
    prepared = dict(batch)
    prepared["graph"] = normalize_graph_batch(batch["graph"], node_feature_stats)
    return normalize_size_targets(prepared, target_mean, target_std)


def _set_deterministic_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def _node_input_dims(graph_batch: dict[str, object]) -> dict[str, int]:
    return {node_type: int(features.shape[1]) for node_type, features in graph_batch["node_features"].items()}


def _metrics(
    outputs: dict[str, torch.Tensor],
    targets: dict[str, torch.Tensor],
    prefix: str,
    target_mean: float | None = None,
    target_std: float | None = None,
) -> dict[str, float]:
    size_pred = outputs["size_field"].squeeze(-1)
    size_target = targets["size_field"]
    if target_mean is not None and target_std is not None:
        size_pred = size_pred * target_std + target_mean
        size_target = targets["size_field_raw"]
    result = {
        f"{prefix}_mae": float(torch.mean(torch.abs(size_pred - size_target)).item()),
        f"{prefix}_rmse": float(torch.sqrt(torch.mean((size_pred - size_target) ** 2)).item()),
        f"{prefix}_size_field_mae_percent": float(torch.mean(torch.abs(size_pred - size_target) / torch.clamp(size_target, min=1e-9)).item()),
        f"{prefix}_failure_risk_mae": float(torch.mean(torch.abs(outputs["failure_risk"].squeeze(-1) - targets["failure_risk"])).item()),
    }
    for key in ["part_strategy", "face_semantic", "edge_semantic", "connection_candidate", "repair_action"]:
        result[f"{prefix}_{key}_accuracy"] = _accuracy(outputs[key], targets[key])
    result[f"{prefix}_part_strategy_macro_f1"] = _macro_f1(outputs["part_strategy"], targets["part_strategy"])
    result[f"{prefix}_face_semantic_mean_iou"] = _mean_iou(outputs["face_semantic"], targets["face_semantic"])
    result[f"{prefix}_edge_semantic_macro_f1"] = _macro_f1(outputs["edge_semantic"], targets["edge_semantic"])
    result[f"{prefix}_connection_candidate_recall"] = _recall(
        outputs["connection_candidate"], targets["connection_candidate"], positive_class=CONNECTION_CLASSES.index("keep")
    )
    result[f"{prefix}_failure_risk_recall"] = _threshold_recall(outputs["failure_risk"].squeeze(-1), targets["failure_risk"])
    result[f"{prefix}_repair_action_top1_accuracy"] = result[f"{prefix}_repair_action_accuracy"]
    return result


def _accuracy(logits: torch.Tensor, target: torch.Tensor) -> float:
    if len(target) == 0:
        return 0.0
    return float((torch.argmax(logits, dim=1) == target).float().mean().item())


def _macro_f1(logits: torch.Tensor, target: torch.Tensor, class_count: int | None = None) -> float:
    if len(target) == 0:
        return 0.0
    pred = torch.argmax(logits, dim=1)
    classes = range(int(class_count or logits.shape[1]))
    scores = []
    for class_index in classes:
        cls = torch.as_tensor(class_index, device=target.device)
        tp = torch.logical_and(pred == cls, target == cls).sum().float()
        fp = torch.logical_and(pred == cls, target != cls).sum().float()
        fn = torch.logical_and(pred != cls, target == cls).sum().float()
        denominator = 2.0 * tp + fp + fn
        scores.append(torch.tensor(0.0, device=target.device) if denominator.item() == 0.0 else (2.0 * tp / denominator))
    return float(torch.stack(scores).mean().item()) if scores else 0.0


def _mean_iou(logits: torch.Tensor, target: torch.Tensor, class_count: int | None = None) -> float:
    if len(target) == 0:
        return 0.0
    pred = torch.argmax(logits, dim=1)
    scores = []
    for class_index in range(int(class_count or logits.shape[1])):
        cls = torch.as_tensor(class_index, device=target.device)
        intersection = torch.logical_and(pred == cls, target == cls).sum().float()
        union = torch.logical_or(pred == cls, target == cls).sum().float()
        if union.item() > 0.0:
            scores.append(intersection / union)
    return float(torch.stack(scores).mean().item()) if scores else 0.0


def _recall(logits: torch.Tensor, target: torch.Tensor, positive_class: int = 1) -> float:
    if len(target) == 0:
        return 0.0
    pred = torch.argmax(logits, dim=1)
    positive = target == int(positive_class)
    total_positive = positive.sum().float()
    if total_positive.item() == 0.0:
        return 1.0 if (pred == int(positive_class)).sum().item() == 0 else 0.0
    true_positive = torch.logical_and(pred == int(positive_class), positive).sum().float()
    return float((true_positive / total_positive).item())


def _threshold_recall(pred_scores: torch.Tensor, target_scores: torch.Tensor, threshold: float = 0.5) -> float:
    if len(target_scores) == 0:
        return 0.0
    target_positive = target_scores >= threshold
    total_positive = target_positive.sum().float()
    pred_positive = pred_scores >= threshold
    if total_positive.item() == 0.0:
        return 1.0 if pred_positive.sum().item() == 0 else 0.0
    true_positive = torch.logical_and(pred_positive, target_positive).sum().float()
    return float((true_positive / total_positive).item())


def _confidence_from_metrics(metrics: dict[str, float]) -> float:
    size_score = max(0.0, 1.0 - metrics.get("val_size_field_mae_percent", 1.0))
    class_keys = [
        "val_part_strategy_accuracy",
        "val_face_semantic_accuracy",
        "val_edge_semantic_accuracy",
        "val_connection_candidate_accuracy",
        "val_repair_action_accuracy",
    ]
    class_score = sum(metrics.get(key, 0.0) for key in class_keys) / len(class_keys)
    return float(max(0.05, min(0.99, 0.5 * size_score + 0.5 * class_score)))


def _jsonable_artifact(artifact: dict) -> dict:
    return {key: value for key, value in artifact.items() if key != "state_dict"}


def _head_schema() -> dict[str, list[str] | str]:
    return {
        "part_strategy": PART_STRATEGY_CLASSES,
        "face_semantic": FACE_SEMANTIC_CLASSES,
        "edge_semantic": EDGE_SEMANTIC_CLASSES,
        "size_field": "part_node_regression_mm",
        "connection_candidate": CONNECTION_CLASSES,
        "failure_risk": "part_node_regression_probability",
        "repair_action": REPAIR_ACTION_CLASSES,
    }


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
