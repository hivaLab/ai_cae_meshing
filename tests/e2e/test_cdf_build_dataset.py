from __future__ import annotations

from pathlib import Path

from cae_dataset_factory.dataset.dataset_validator import validate_dataset
from cae_dataset_factory.workflow.build_dataset import build_dataset


def test_cdf_build_dataset_smoke(tmp_path: Path):
    dataset = tmp_path / "dataset"
    build_dataset("configs/cdf/base_indoor_generation_v001.yaml", dataset, num_samples=10)
    summary = validate_dataset(dataset)
    assert summary.passed
    assert summary.accepted_count == 10
    assert summary.train_count == 8
    assert summary.val_count == 1
    assert summary.test_count == 1
