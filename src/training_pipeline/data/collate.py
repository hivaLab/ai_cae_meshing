from __future__ import annotations

import torch


TARGET_KEYS = [
    "part_strategy",
    "face_semantic",
    "edge_semantic",
    "size_field",
    "failure_risk",
    "connection_candidate",
    "repair_action",
]


def collate_graph_batch(batch: list[dict]) -> dict:
    if not batch:
        raise ValueError("cannot collate an empty batch")
    return {
        "sample_id": [str(item["sample_id"]) for item in batch],
        "graph_path": [str(item["graph_path"]) for item in batch],
        "graph": batch_hetero_graphs([item["graph"] for item in batch]),
        **{key: torch.cat([item[key] for item in batch], dim=0) for key in TARGET_KEYS},
    }


def batch_hetero_graphs(graphs: list[dict]) -> dict[str, object]:
    if not graphs:
        raise ValueError("cannot batch zero graphs")
    node_types = list(graphs[0]["node_features"])
    edge_types = list(graphs[0]["edge_index"])
    node_features = {node_type: [] for node_type in node_types}
    batch_index = {node_type: [] for node_type in node_types}
    offsets = {node_type: 0 for node_type in node_types}
    batched_edges = {edge_type: [] for edge_type in edge_types}

    for graph_index, graph in enumerate(graphs):
        if set(graph["node_features"]) != set(node_types):
            raise ValueError("all graphs in a batch must have the same node types")
        if set(graph["edge_index"]) != set(edge_types):
            raise ValueError("all graphs in a batch must have the same edge types")
        local_offsets = dict(offsets)
        for node_type in node_types:
            features = torch.as_tensor(graph["node_features"][node_type], dtype=torch.float32)
            node_features[node_type].append(features)
            batch_index[node_type].append(torch.full((features.shape[0],), graph_index, dtype=torch.long))
            offsets[node_type] += int(features.shape[0])
        for edge_type in edge_types:
            source_type, _, target_type = edge_type.split("__")
            edge_index = torch.as_tensor(graph["edge_index"][edge_type], dtype=torch.long)
            if edge_index.ndim != 2 or edge_index.shape[0] != 2:
                raise ValueError(f"edge_index for {edge_type} must have shape [2, num_edges]")
            if edge_index.shape[1] == 0:
                batched_edges[edge_type].append(edge_index)
                continue
            shifted = edge_index.clone()
            shifted[0] += local_offsets[source_type]
            shifted[1] += local_offsets[target_type]
            batched_edges[edge_type].append(shifted)

    return {
        "format": "cae_hetero_graph_batch_v1",
        "num_graphs": len(graphs),
        "sample_id": [str(graph["sample_id"]) for graph in graphs],
        "node_feature_names": graphs[0].get("node_feature_names", {}),
        "node_features": {
            node_type: torch.cat(chunks, dim=0) if chunks else torch.empty((0, 0), dtype=torch.float32)
            for node_type, chunks in node_features.items()
        },
        "edge_index": {
            edge_type: torch.cat(chunks, dim=1) if chunks else torch.empty((2, 0), dtype=torch.long)
            for edge_type, chunks in batched_edges.items()
        },
        "batch_index": {
            node_type: torch.cat(chunks, dim=0) if chunks else torch.empty((0,), dtype=torch.long)
            for node_type, chunks in batch_index.items()
        },
    }
