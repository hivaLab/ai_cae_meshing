from __future__ import annotations

import torch


def edge_module_key(edge_type: str) -> str:
    return edge_type.replace("__", "_to_")


class TypedNodeEncoder(torch.nn.Module):
    def __init__(self, node_input_dims: dict[str, int], hidden_dim: int) -> None:
        super().__init__()
        self.node_types = sorted(node_input_dims)
        self.encoders = torch.nn.ModuleDict(
            {
                node_type: torch.nn.Sequential(
                    torch.nn.Linear(input_dim, hidden_dim),
                    torch.nn.LayerNorm(hidden_dim),
                    torch.nn.GELU(),
                    torch.nn.Linear(hidden_dim, hidden_dim),
                    torch.nn.GELU(),
                )
                for node_type, input_dim in node_input_dims.items()
            }
        )

    def forward(self, node_features: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        missing = set(self.node_types) - set(node_features)
        if missing:
            raise ValueError(f"graph is missing node feature tensors for {sorted(missing)}")
        return {
            node_type: self.encoders[node_type](node_features[node_type])
            for node_type in self.node_types
        }


class HeteroMessagePassingLayer(torch.nn.Module):
    def __init__(self, node_types: list[str], edge_types: list[str], hidden_dim: int) -> None:
        super().__init__()
        self.node_types = node_types
        self.edge_types = edge_types
        self.self_updates = torch.nn.ModuleDict({node_type: torch.nn.Linear(hidden_dim, hidden_dim) for node_type in node_types})
        self.message_updates = torch.nn.ModuleDict(
            {edge_module_key(edge_type): torch.nn.Linear(hidden_dim, hidden_dim, bias=False) for edge_type in edge_types}
        )
        self.norms = torch.nn.ModuleDict({node_type: torch.nn.LayerNorm(hidden_dim) for node_type in node_types})

    def forward(self, embeddings: dict[str, torch.Tensor], edge_index: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        aggregated = {node_type: torch.zeros_like(values) for node_type, values in embeddings.items()}
        degrees = {
            node_type: torch.zeros((values.shape[0], 1), dtype=values.dtype, device=values.device)
            for node_type, values in embeddings.items()
        }
        for edge_type in self.edge_types:
            if edge_type not in edge_index:
                raise ValueError(f"graph is missing edge_index for {edge_type}")
            source_type, _, target_type = edge_type.split("__")
            indices = edge_index[edge_type].to(device=embeddings[source_type].device, dtype=torch.long)
            if indices.ndim != 2 or indices.shape[0] != 2:
                raise ValueError(f"edge_index for {edge_type} must have shape [2, num_edges]")
            if indices.shape[1] == 0:
                continue
            source, target = indices[0], indices[1]
            messages = self.message_updates[edge_module_key(edge_type)](embeddings[source_type][source])
            aggregated[target_type].index_add_(0, target, messages)
            degrees[target_type].index_add_(0, target, torch.ones((len(target), 1), dtype=messages.dtype, device=messages.device))
        updated = {}
        for node_type, values in embeddings.items():
            message = aggregated[node_type] / torch.clamp(degrees[node_type], min=1.0)
            updated[node_type] = torch.nn.functional.gelu(self.norms[node_type](self.self_updates[node_type](values) + message))
        return updated
