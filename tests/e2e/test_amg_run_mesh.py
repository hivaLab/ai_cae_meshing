from __future__ import annotations

from pathlib import Path

import pytest

from ai_mesh_generator.meshing.ansa_runner import AnsaCommandBackend
from ai_mesh_generator.workflow.run_mesh_job import run_mesh_job
from cae_dataset_factory.dataset.dataset_indexer import read_dataset_index
from cae_dataset_factory.workflow.build_dataset import build_dataset
from training_pipeline.train import train_model


def test_amg_run_mesh_e2e(tmp_path: Path):
    if not AnsaCommandBackend().status()["available"]:
        pytest.skip("ANSA_BATCH is required for production AMG meshing")
    dataset = tmp_path / "dataset"
    build_dataset("configs/cdf/base_indoor_generation_v001.yaml", dataset, num_samples=10)
    model_dir = tmp_path / "model"
    train_model("configs/training/brep_assembly_net.yaml", dataset, model_dir)
    first = read_dataset_index(dataset).iloc[-1]
    output = tmp_path / "MESH_RESULT.zip"
    summary = run_mesh_job(first["input_zip"], model_dir / "model.pt", output)
    assert output.exists()
    assert summary["result_validation"]["passed"]
    assert summary["mesh_result"]["metrics"]["bdf_parse_success"]


def test_amg_rejects_synthetic_oracle_as_production_backend():
    with pytest.raises(ValueError, match="supports only ANSA_BATCH"):
        run_mesh_job("unused.zip", "unused.pt", "unused_result.zip", backend="SYNTHETIC_ORACLE")


def test_amg_fails_explicitly_when_ansa_unavailable(monkeypatch):
    monkeypatch.setattr(
        AnsaCommandBackend,
        "status",
        lambda self: {"backend": "ANSA_BATCH", "available": False, "fallback_enabled": False},
    )
    with pytest.raises(RuntimeError, match="ANSA_BATCH backend is required"):
        run_mesh_job("unused.zip", "unused.pt", "unused_result.zip")
