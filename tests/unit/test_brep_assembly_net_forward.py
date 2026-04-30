from __future__ import annotations

import torch

from training_pipeline.losses.multitask_loss import multitask_loss
from training_pipeline.models.brep_assembly_net import BRepAssemblyNet


def test_brep_assembly_net_forward_shapes_and_loss():
    model = BRepAssemblyNet(input_dim=7, hidden_dim=16)
    outputs = model(torch.ones(3, 7))
    assert outputs["part_strategy"].shape == (3, 4)
    assert outputs["size_field"].shape == (3, 1)
    loss = multitask_loss(outputs, {"size_field": torch.ones(3), "failure_risk": torch.zeros(3)})
    assert torch.isfinite(loss)
