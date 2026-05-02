from __future__ import annotations

import json
from pathlib import Path

from ai_mesh_generator.cad.importer import import_input_assembly
from cae_mesh_common.cad.step_io import cad_kernel_status, inspect_step_brep, validate_feature_bearing_step
from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.cad.cad_exporter import export_assembly_step


def test_cadquery_ocp_exports_real_ap242_brep_step(tmp_path: Path):
    status = cad_kernel_status()
    assert status["step_ap242_brep_export"], status

    assembly = AssemblyGrammar(123).generate(0)
    job_dir = tmp_path / "input_package"
    geometry_dir = job_dir / "geometry"
    metadata_dir = job_dir / "metadata"
    geometry_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    step_path = export_assembly_step(geometry_dir / "assembly.step", assembly["sample_id"], assembly["parts"])
    (metadata_dir / "assembly.json").write_text(json.dumps(assembly, indent=2), encoding="utf-8")

    info = inspect_step_brep(step_path)
    imported = import_input_assembly(job_dir)

    assert info["valid_step"]
    assert info["is_ap242"]
    assert info["is_brep"]
    assert not info["descriptor_only"]
    assert info["advanced_face_count"] > 6 * len(assembly["parts"])
    assert info["cylindrical_surface_count"] > 0
    assert info["product_count"] >= len(assembly["parts"])
    feature_info = validate_feature_bearing_step(step_path, assembly["parts"])
    assert feature_info["feature_bearing"], feature_info
    assert imported["geometry_source"]["cad_kernel"] == "STEP_AP242_BREP"
    assert imported["geometry_source"]["step_descriptor_only"] is False
    assert "deterministic procedural geometry descriptor" not in step_path.read_text(
        encoding="utf-8", errors="replace"
    )
