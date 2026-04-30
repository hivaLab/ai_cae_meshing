from __future__ import annotations

import torch

from .encoders import SimpleGraphEncoder
from .heads import MultiTaskHeads


class BRepAssemblyNet(torch.nn.Module):
    def __init__(self, input_dim: int = 7, hidden_dim: int = 32) -> None:
        super().__init__()
        self.encoder = SimpleGraphEncoder(input_dim=input_dim, hidden_dim=hidden_dim)
        self.heads = MultiTaskHeads(hidden_dim=hidden_dim)

    def forward(self, graph_features: torch.Tensor) -> dict[str, torch.Tensor]:
        return self.heads(self.encoder(graph_features))
