from __future__ import annotations

from pathlib import Path

import torch


def load_model(path: Path | str) -> dict:
    payload = torch.load(Path(path), map_location="cpu", weights_only=False)
    required = {
        "node_input_dims",
        "node_feature_names",
        "edge_types",
        "node_feature_stats",
        "target_mean",
        "target_std",
        "state_dict",
        "hidden_dim",
        "num_layers",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"invalid neural model artifact, missing {sorted(missing)}")
    if payload.get("model_type") != "hetero_brep_assembly_net":
        raise ValueError(f"unsupported model_type: {payload.get('model_type')}")
    if payload.get("framework") != "torch":
        raise ValueError(f"unsupported model framework: {payload.get('framework')}")
    return payload
