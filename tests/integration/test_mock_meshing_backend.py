from __future__ import annotations

from pathlib import Path

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


def test_ansa_command_construction(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    labels = build_oracle_labels(assembly)
    recipe = build_oracle_recipe(assembly, labels)
    request = MeshRequest(assembly["sample_id"], assembly, recipe, tmp_path, backend="ANSA_BATCH")
    backend = AnsaCommandBackend(AnsaBackendConfig(ansa_executable="C:/ANSA/ansa64.bat", dry_run=True))
    stage = backend.stage_input(request)
    config = backend.write_config(request, stage)
    command = backend.build_command(config)
    assert "-nogui" in command
    assert "load_script:" in command[-1]
