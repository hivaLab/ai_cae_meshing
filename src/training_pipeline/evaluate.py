from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from training_pipeline.data.collate import collate_graph_batch
from training_pipeline.data.dataset import BRepAssemblyDataset
from training_pipeline.data.normalization import normalize_graph_batch, normalize_size_targets
from training_pipeline.models.brep_assembly_net import BRepAssemblyNet
from training_pipeline.train import _metrics


def load_model_artifact(path: Path | str) -> dict:
    return torch.load(Path(path), map_location="cpu", weights_only=False)


def build_model_from_artifact(artifact: dict) -> BRepAssemblyNet:
    model = BRepAssemblyNet(
        node_input_dims={key: int(value) for key, value in artifact["node_input_dims"].items()},
        edge_types=list(artifact["edge_types"]),
        hidden_dim=int(artifact["hidden_dim"]),
        num_layers=int(artifact["num_layers"]),
    )
    state_dict = {key: torch.as_tensor(value) for key, value in artifact["state_dict"].items()}
    model.load_state_dict(state_dict)
    model.eval()
    return model


def evaluate_model(model_path: Path | str, dataset_dir: Path | str, split: str, output_dir: Path | str) -> dict:
    artifact = load_model_artifact(model_path)
    batch = _load_eval_batch(dataset_dir, split, artifact)
    target_mean = float(artifact["target_mean"])
    target_std = float(artifact["target_std"])
    model = build_model_from_artifact(artifact)
    with torch.no_grad():
        outputs = model(batch["graph"])
    raw = _metrics(outputs, batch, split, target_mean, target_std)
    metrics = {
        "split": split,
        "sample_count": int(batch["graph"]["num_graphs"]),
        "part_node_count": int(len(batch["part_strategy"])),
        "face_node_count": int(len(batch["face_semantic"])),
        "edge_node_count": int(len(batch["edge_semantic"])),
        "contact_candidate_node_count": int(len(batch["connection_candidate"])),
        "mae": raw[f"{split}_mae"],
        "rmse": raw[f"{split}_rmse"],
        "size_field_mae_percent": raw[f"{split}_size_field_mae_percent"],
        "refinement_size_mae_percent": raw[f"{split}_refinement_size_mae_percent"],
        "face_size_mae_percent": raw.get(f"{split}_face_size_mae_percent", 0.0),
        "edge_size_mae_percent": raw.get(f"{split}_edge_size_mae_percent", 0.0),
        "contact_size_mae_percent": raw.get(f"{split}_contact_size_mae_percent", 0.0),
        "recipe_size_within_20pct": _within_20pct(
            outputs["face_size"].squeeze(-1) * target_std + target_mean,
            batch["face_size_raw"],
        ),
        "part_strategy_accuracy": raw[f"{split}_part_strategy_accuracy"],
        "face_semantic_accuracy": raw[f"{split}_face_semantic_accuracy"],
        "edge_semantic_accuracy": raw[f"{split}_edge_semantic_accuracy"],
        "connection_candidate_accuracy": raw[f"{split}_connection_candidate_accuracy"],
        "failure_risk_mae": raw[f"{split}_failure_risk_mae"],
        "repair_action_accuracy": raw[f"{split}_repair_action_accuracy"],
        "feature_refinement_class_accuracy": raw[f"{split}_feature_refinement_class_accuracy"],
        "part_strategy_macro_f1": raw[f"{split}_part_strategy_macro_f1"],
        "face_semantic_mean_iou": raw[f"{split}_face_semantic_mean_iou"],
        "edge_semantic_macro_f1": raw[f"{split}_edge_semantic_macro_f1"],
        "connection_candidate_recall": raw[f"{split}_connection_candidate_recall"],
        "failure_risk_recall": raw[f"{split}_failure_risk_recall"],
        "repair_action_top1_accuracy": raw[f"{split}_repair_action_top1_accuracy"],
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return metrics


def _load_eval_batch(dataset_dir: Path | str, split: str, artifact: dict) -> dict[str, object]:
    dataset = BRepAssemblyDataset(dataset_dir, split)
    if len(dataset) == 0:
        raise ValueError(f"dataset split {split!r} is empty")
    batch = collate_graph_batch([dataset[index] for index in range(len(dataset))])
    prepared = dict(batch)
    prepared["graph"] = normalize_graph_batch(batch["graph"], artifact["node_feature_stats"])
    return normalize_size_targets(prepared, float(artifact["target_mean"]), float(artifact["target_std"]))


def _within_20pct(pred: torch.Tensor, target: torch.Tensor) -> float:
    if len(target) == 0:
        return 0.0
    return float((torch.abs(pred - target) <= torch.clamp(0.2 * target, min=1e-9)).float().mean().item())


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
