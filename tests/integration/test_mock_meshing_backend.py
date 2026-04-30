from __future__ import annotations

from pathlib import Path
import json

from ai_mesh_generator.meshing.ansa_runner import AnsaBackendConfig, AnsaCommandBackend
from ai_mesh_generator.meshing.backend_interface import LocalProceduralMeshingBackend, MeshRequest
from cae_dataset_factory.dataset.sample_writer import build_oracle_labels, build_oracle_recipe
from cae_dataset_factory.workflow.generate_sample import generate_sample


def test_local_backend_generates_valid_bdf(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    labels = build_oracle_labels(assembly)
    recipe = build_oracle_recipe(assembly, labels)
    result = LocalProceduralMeshingBackend().run(MeshRequest(assembly["sample_id"], assembly, recipe, tmp_path))
    assert result.accepted
    assert result.bdf_path.exists()
    assert result.qa_report_path.exists()
    assert (tmp_path / "solver_deck" / "materials.inc").exists()
    assert (tmp_path / "solver_deck" / "properties.inc").exists()
    assert (tmp_path / "report" / "qa_metrics_global.json").exists()
    assert (tmp_path / "report" / "qa_metrics_part.csv").exists()
    assert (tmp_path / "report" / "qa_metrics_element.parquet").exists()
    assert (tmp_path / "metadata" / "cad_to_mesh_mapping.parquet").exists()
    assert (tmp_path / "viewer" / "mesh_preview.vtk").exists()


def test_ansa_command_construction(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    labels = build_oracle_labels(assembly)
    recipe = build_oracle_recipe(assembly, labels)
    request = MeshRequest(assembly["sample_id"], assembly, recipe, tmp_path, backend="ANSA_BATCH")
    executable = tmp_path / "ansa64.bat"
    executable.write_text("@echo off\n", encoding="utf-8")
    backend = AnsaCommandBackend(AnsaBackendConfig(ansa_executable=str(executable)))
    stage = backend.stage_input(request)
    config = backend.write_config(request, stage)
    config_payload = json.loads(config.read_text(encoding="utf-8"))
    command = backend.build_command(config)
    assert "-nogui" in command
    assert any(part.startswith("load_script:") for part in command)
    assert any(part.startswith("run_batch_mesh(") for part in command)
    assert backend.status()["fallback_enabled"] is False
    assert (stage / "ansa_recipe_plan.json").exists()
    assert (stage / "ansa_mesh_parameters.json").exists()
    assert (stage / "ansa_quality_criteria.json").exists()
    assert Path(config_payload["ansa_recipe_plan_json"]).exists()
    assert config_payload["geometry_mode"] == "PROCEDURAL_DESCRIPTOR"
