from __future__ import annotations

import torch


def multitask_loss(outputs: dict[str, torch.Tensor], targets: dict[str, torch.Tensor]) -> torch.Tensor:
    loss = torch.tensor(0.0, dtype=torch.float32, device=next(iter(outputs.values())).device)
    if "size_field" in targets:
        loss = loss + torch.nn.functional.mse_loss(outputs["size_field"].squeeze(-1), targets["size_field"])
    if "failure_risk" in targets:
        loss = loss + torch.nn.functional.mse_loss(outputs["failure_risk"].squeeze(-1), targets["failure_risk"])
    for key in ["part_strategy", "face_semantic", "edge_semantic", "connection_candidate", "repair_action"]:
        if key in targets and len(targets[key]) > 0:
            loss = loss + torch.nn.functional.cross_entropy(outputs[key], targets[key])
    return loss
