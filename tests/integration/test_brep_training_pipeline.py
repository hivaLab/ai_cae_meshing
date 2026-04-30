from __future__ import annotations

from pathlib import Path

import torch

from ai_mesh_generator.inference.model_loader import load_model
from cae_dataset_factory.workflow.build_dataset import build_dataset
from training_pipeline.data.dataset import BRepAssemblyDataset
from training_pipeline.evaluate import evaluate_model
from training_pipeline.export_model import export_model
from training_pipeline.train import train_model


def test_brep_training_evaluate_export_pipeline(tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    build_dataset("configs/cdf/base_indoor_generation_v001.yaml", dataset_dir, num_samples=12)

    train_split = BRepAssemblyDataset(dataset_dir, "train")
    assert len(train_split) > 0
    item = train_split[0]
    assert item["part_strategy"].dtype == torch.long
    assert item["graph"]["node_features"]["part"].ndim == 2
    assert item["graph"]["node_features"]["face"].shape[0] == 72
    assert item["graph"]["edge_index"]["face__incident_to__edge"].shape[0] == 2
    assert item["part_strategy"].shape == (12,)
    assert item["face_semantic"].shape == (72,)
    assert item["edge_semantic"].shape == (144,)
    assert Path(item["graph_path"]).with_name("brep_graph.json").exists()
    assert Path(item["graph_path"]).with_name("assembly_graph.json").exists()

    model_dir = tmp_path / "model"
    result = train_model("configs/training/brep_assembly_net.yaml", dataset_dir, model_dir)
    artifact = torch.load(result["model_path"], map_location="cpu", weights_only=False)
    assert artifact["framework"] == "torch"
    assert artifact["model_type"] == "hetero_brep_assembly_net"
    assert artifact["node_input_dims"]["part"] == item["graph"]["node_features"]["part"].shape[1]
    assert "feature_order" not in artifact
    assert artifact["state_dict"]
    assert all(torch.is_tensor(value) for value in artifact["state_dict"].values())

    metrics = evaluate_model(model_dir / "model.pt", dataset_dir, "test", tmp_path / "eval")
    assert metrics["sample_count"] > 0
    assert "part_strategy_macro_f1" in metrics

    exported = export_model(model_dir / "model.pt", tmp_path / "exported_model.pt")
    exported_payload = load_model(exported)
    assert exported_payload["export_format"] == "amg_deployment_artifact_v1"
    assert exported_payload["model_type"] == "hetero_brep_assembly_net"
    assert "node_feature_stats" in exported_payload
    assert "training_history" not in exported_payload
    assert exported.with_suffix(".pt.manifest.json").exists()
