from __future__ import annotations

from pathlib import Path
import zipfile

from ai_mesh_generator.workflow.run_mesh_job import run_mesh_job
from cae_dataset_factory.dataset.dataset_indexer import read_dataset_index
from cae_dataset_factory.workflow.build_dataset import build_dataset
from training_pipeline.train import train_model


def test_amg_run_mesh_e2e(tmp_path: Path):
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
    with zipfile.ZipFile(output, "r") as archive:
        names = set(archive.namelist())
    assert "solver_deck/model_final.bdf" in names
    assert "report/qa_metrics_global.json" in names
    assert "metadata/engineering_guard_log.json" in names
    assert "viewer/mesh_preview.vtk" in names
