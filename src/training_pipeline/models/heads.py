from __future__ import annotations

import torch


class MultiTaskHeads(torch.nn.Module):
    def __init__(self, hidden_dim: int = 32) -> None:
        super().__init__()
        self.part_strategy = torch.nn.Linear(hidden_dim, 4)
        self.face_semantic = torch.nn.Linear(hidden_dim, 5)
        self.edge_semantic = torch.nn.Linear(hidden_dim, 4)
        self.size_field = torch.nn.Linear(hidden_dim, 1)
        self.connection_candidate = torch.nn.Linear(hidden_dim, 2)
        self.failure_risk = torch.nn.Linear(hidden_dim, 1)
        self.repair_action = torch.nn.Linear(hidden_dim, 4)

    def forward(self, h: torch.Tensor) -> dict[str, torch.Tensor]:
        return {
            "part_strategy": self.part_strategy(h),
            "face_semantic": self.face_semantic(h),
            "edge_semantic": self.edge_semantic(h),
            "size_field": self.size_field(h),
            "connection_candidate": self.connection_candidate(h),
            "failure_risk": torch.sigmoid(self.failure_risk(h)),
            "repair_action": self.repair_action(h),
        }
