from __future__ import annotations

import numpy as np

from cae_mesh_common.graph.hetero_graph import HeteroGraph


def predict_recipe_signals(model: dict, graph: HeteroGraph, assembly: dict) -> dict:
    features = np.asarray([[graph.graph_features[key] for key in model["feature_order"]]], dtype=np.float64)
    mean = np.asarray(model["mean"], dtype=np.float64)
    std = np.asarray(model["std"], dtype=np.float64)
    weights = np.asarray(model["weights"], dtype=np.float64)
    pred = float((np.column_stack([np.ones(1), (features - mean) / std]) @ weights)[0])
    confidence = float(model.get("confidence", 0.75))
    part_strategies = [
        {"part_uid": part["part_uid"], "strategy": part.get("strategy", "shell"), "confidence": confidence}
        for part in assembly["parts"]
    ]
    size_fields = [
        {"part_uid": part["part_uid"], "target_size": round(max(2.0, pred), 4), "confidence": confidence}
        for part in assembly["parts"]
    ]
    return {
        "base_size": round(max(2.0, pred), 4),
        "part_strategies": part_strategies,
        "size_fields": size_fields,
        "connections": assembly.get("connections", []),
        "confidence": confidence,
    }
