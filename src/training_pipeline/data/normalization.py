from __future__ import annotations

import torch


def compute_node_feature_stats(graph_batch: dict[str, object]) -> dict[str, dict[str, list[float]]]:
    stats = {}
    for node_type, features in graph_batch["node_features"].items():
        tensor = torch.as_tensor(features, dtype=torch.float32)
        mean = tensor.mean(dim=0)
        std = tensor.std(dim=0)
        std = torch.where(std == 0.0, torch.ones_like(std), std)
        stats[node_type] = {"mean": mean.tolist(), "std": std.tolist()}
    return stats


def normalize_graph_batch(graph_batch: dict[str, object], stats: dict[str, dict[str, list[float]]]) -> dict[str, object]:
    normalized = {
        key: value
        for key, value in graph_batch.items()
        if key not in {"node_features"}
    }
    normalized_features = {}
    for node_type, features in graph_batch["node_features"].items():
        if node_type not in stats:
            raise ValueError(f"normalization stats missing node type {node_type}")
        tensor = torch.as_tensor(features, dtype=torch.float32)
        mean = torch.as_tensor(stats[node_type]["mean"], dtype=tensor.dtype, device=tensor.device)
        std = torch.as_tensor(stats[node_type]["std"], dtype=tensor.dtype, device=tensor.device)
        normalized_features[node_type] = (tensor - mean) / std
    normalized["node_features"] = normalized_features
    return normalized


def normalize_size_targets(batch: dict[str, object], target_mean: float, target_std: float) -> dict[str, object]:
    result = dict(batch)
    raw = torch.as_tensor(batch["size_field"], dtype=torch.float32)
    result["size_field_raw"] = raw
    result["size_field"] = (raw - float(target_mean)) / float(target_std)
    return result
