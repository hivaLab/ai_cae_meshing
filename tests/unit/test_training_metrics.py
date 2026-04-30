from __future__ import annotations

import pytest
import torch

from training_pipeline.train import _macro_f1, _mean_iou, _recall, _threshold_recall


def test_macro_f1_is_not_accuracy_alias():
    logits = torch.tensor(
        [
            [3.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 3.0],
        ]
    )
    target = torch.tensor([0, 1, 1, 2])

    assert _macro_f1(logits, target) == pytest.approx((1.0 + 2.0 / 3.0 + 2.0 / 3.0) / 3.0)
    assert _macro_f1(logits, target) != pytest.approx((torch.argmax(logits, dim=1) == target).float().mean().item())


def test_mean_iou_uses_intersection_over_union():
    logits = torch.tensor(
        [
            [3.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 0.0, 3.0],
            [0.0, 0.0, 3.0],
        ]
    )
    target = torch.tensor([0, 1, 1, 2])

    assert _mean_iou(logits, target) == pytest.approx((1.0 + 0.5 + 0.5) / 3.0)


def test_binary_recall_metrics_use_positive_class_hits():
    logits = torch.tensor([[3.0, 0.0], [0.0, 3.0], [3.0, 0.0], [3.0, 0.0]])
    target = torch.tensor([0, 1, 1, 0])
    pred_scores = torch.tensor([0.1, 0.6, 0.4])
    target_scores = torch.tensor([0.2, 0.9, 0.8])

    assert _recall(logits, target, positive_class=1) == pytest.approx(0.5)
    assert _threshold_recall(pred_scores, target_scores, threshold=0.5) == pytest.approx(0.5)
