from __future__ import annotations

import torch


def multitask_loss(outputs: dict[str, torch.Tensor], targets: dict[str, torch.Tensor]) -> torch.Tensor:
    loss = torch.tensor(0.0, dtype=torch.float32, device=next(iter(outputs.values())).device)
    for key in ["part_size", "face_size", "edge_size", "contact_size"]:
        if key in targets and key in outputs and len(targets[key]) > 0:
            loss = loss + torch.nn.functional.mse_loss(outputs[key].squeeze(-1), targets[key])
    if "size_field" in targets and "part_size" not in targets:
        loss = loss + torch.nn.functional.mse_loss(outputs["size_field"].squeeze(-1), targets["size_field"])
    if "failure_risk" in targets:
        loss = loss + torch.nn.functional.mse_loss(outputs["failure_risk"].squeeze(-1), targets["failure_risk"])
    for key in ["part_strategy", "face_semantic", "edge_semantic", "connection_candidate", "repair_action", "feature_refinement_class"]:
        if key in targets and len(targets[key]) > 0:
            loss = loss + torch.nn.functional.cross_entropy(outputs[key], targets[key])
    return loss
