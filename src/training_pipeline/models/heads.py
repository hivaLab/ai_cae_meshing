from __future__ import annotations

import torch

FEATURE_REFINEMENT_CLASS_COUNT = 9


class HeteroPredictionHeads(torch.nn.Module):
    def __init__(self, hidden_dim: int = 64) -> None:
        super().__init__()
        self.part_strategy = torch.nn.Linear(hidden_dim, 4)
        self.face_semantic = torch.nn.Linear(hidden_dim, 5)
        self.edge_semantic = torch.nn.Linear(hidden_dim, 4)
        self.part_size = torch.nn.Linear(hidden_dim, 1)
        self.face_size = torch.nn.Linear(hidden_dim, 1)
        self.edge_size = torch.nn.Linear(hidden_dim, 1)
        self.contact_size = torch.nn.Linear(hidden_dim, 1)
        self.feature_refinement_class = torch.nn.Linear(hidden_dim, FEATURE_REFINEMENT_CLASS_COUNT)
        self.connection_candidate = torch.nn.Linear(hidden_dim, 2)
        self.failure_risk = torch.nn.Linear(hidden_dim, 1)
        self.repair_action = torch.nn.Linear(hidden_dim, 4)

    def forward(self, embeddings: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        return {
            "part_strategy": self.part_strategy(embeddings["part"]),
            "face_semantic": self.face_semantic(embeddings["face"]),
            "edge_semantic": self.edge_semantic(embeddings["edge"]),
            "part_size": self.part_size(embeddings["part"]),
            "size_field": self.part_size(embeddings["part"]),
            "face_size": self.face_size(embeddings["face"]),
            "edge_size": self.edge_size(embeddings["edge"]),
            "contact_size": self.contact_size(embeddings["contact_candidate"]),
            "feature_refinement_class": self.feature_refinement_class(embeddings["face"]),
            "connection_candidate": self.connection_candidate(embeddings["contact_candidate"]),
            "failure_risk": torch.sigmoid(self.failure_risk(embeddings["part"])),
            "repair_action": self.repair_action(embeddings["part"]),
        }
