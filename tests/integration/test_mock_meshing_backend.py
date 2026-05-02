from __future__ import annotations

from pathlib import Path
import json

from ai_mesh_generator.meshing.ansa_runner import AnsaBackendConfig, AnsaCommandBackend
from ai_mesh_generator.meshing.backend_interface import MeshRequest, SyntheticOracleMeshingBackend
from cae_dataset_factory.dataset.sample_writer import build_oracle_labels, build_oracle_recipe
from cae_dataset_factory.workflow.generate_sample import generate_sample


def test_synthetic_oracle_backend_generates_valid_bdf_for_cdf_only(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    labels = build_oracle_labels(assembly)
    recipe = build_oracle_recipe(assembly, labels)
    result = SyntheticOracleMeshingBackend().run(
        MeshRequest(assembly["sample_id"], assembly, recipe, tmp_path, backend="SYNTHETIC_ORACLE")
    )
    assert result.accepted
    assert result.backend == "SYNTHETIC_ORACLE"
    assert SyntheticOracleMeshingBackend().status()["production_allowed"] is False
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
    plan_payload = json.loads((stage / "ansa_recipe_plan.json").read_text(encoding="utf-8"))
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
    assert plan_payload["native_entity_generation"]["solid_tetra"]["entity_type"] == "SOLID"
    assert plan_payload["native_entity_generation"]["solid_tetra"]["method"] == "batchmesh_volume_scenario"
    assert plan_payload["native_entity_generation"]["connector"]["entity_type"] == "CBUSH"
    assert plan_payload["native_entity_generation"]["mass"]["entity_type"] == "CONM2"
    assert plan_payload["fallback_enabled"] is False


def test_ansa_script_uses_native_volume_session_instead_of_manual_solid_creation():
    script = Path("ansa_scripts/common_ansa_utils.py").read_text(encoding="utf-8")

    assert "GetNewVolumeScenario" in script
    assert "GetNewVolumeSession" in script
    assert "_assign_native_solid_solver_cards" in script
    assert "split_pyramid=\"on\"" in script
    assert "second_as_first_solids=\"on\"" in script
    assert 'CreateEntity(constants.NASTRAN, "SOLID"' not in script
