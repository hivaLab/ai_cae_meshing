from __future__ import annotations

import torch

from .encoders import HeteroMessagePassingLayer, TypedNodeEncoder
from .heads import HeteroPredictionHeads


REQUIRED_NODE_TYPES = ["part", "face", "edge", "contact_candidate", "connection"]


class BRepAssemblyNet(torch.nn.Module):
    """Heterogeneous graph neural network for B-Rep assembly meshing decisions."""

    def __init__(
        self,
        node_input_dims: dict[str, int],
        edge_types: list[str],
        hidden_dim: int = 64,
        num_layers: int = 3,
    ) -> None:
        super().__init__()
        if hidden_dim <= 0:
            raise ValueError("hidden_dim must be positive")
        if num_layers <= 0:
            raise ValueError("num_layers must be positive")
        missing = set(REQUIRED_NODE_TYPES) - set(node_input_dims)
        if missing:
            raise ValueError(f"node_input_dims missing required node types {sorted(missing)}")
        if not edge_types:
            raise ValueError("edge_types must not be empty")
        self.node_input_dims = {key: int(value) for key, value in node_input_dims.items()}
        self.edge_types = list(edge_types)
        self.hidden_dim = int(hidden_dim)
        self.num_layers = int(num_layers)
        self.encoder = TypedNodeEncoder(self.node_input_dims, self.hidden_dim)
        self.layers = torch.nn.ModuleList(
            [
                HeteroMessagePassingLayer(sorted(self.node_input_dims), self.edge_types, self.hidden_dim)
                for _ in range(self.num_layers)
            ]
        )
        self.heads = HeteroPredictionHeads(hidden_dim=self.hidden_dim)

    def forward(self, graph_batch: dict[str, object]) -> dict[str, torch.Tensor]:
        node_features = graph_batch.get("node_features")
        edge_index = graph_batch.get("edge_index")
        if not isinstance(node_features, dict) or not isinstance(edge_index, dict):
            raise ValueError("BRepAssemblyNet expects a graph batch with node_features and edge_index dictionaries")
        self._validate_node_features(node_features)
        embeddings = self.encoder(node_features)
        for layer in self.layers:
            embeddings = layer(embeddings, edge_index)
        return self.heads(embeddings)

    def _validate_node_features(self, node_features: dict[str, torch.Tensor]) -> None:
        for node_type, input_dim in self.node_input_dims.items():
            if node_type not in node_features:
                raise ValueError(f"graph batch is missing node type {node_type}")
            tensor = node_features[node_type]
            if tensor.ndim != 2 or tensor.shape[1] != input_dim:
                raise ValueError(
                    f"expected {node_type} node_features shape [num_nodes,{input_dim}], got {tuple(tensor.shape)}"
                )
