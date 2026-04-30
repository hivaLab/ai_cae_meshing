from __future__ import annotations

import json
import shutil
from pathlib import Path

from ai_mesh_generator.cad.feature_extractor import extract_features
from ai_mesh_generator.cad.healer import heal_geometry
from ai_mesh_generator.cad.importer import import_input_assembly
from ai_mesh_generator.graph.graph_builder import build_amg_graph, build_and_save_graph
from ai_mesh_generator.inference.model_loader import load_model
from ai_mesh_generator.inference.predictor import predict_recipe_signals
from ai_mesh_generator.input.validator import validate_input_package_dir
from ai_mesh_generator.meshing.ansa_runner import AnsaBackendConfig, AnsaCommandBackend
from ai_mesh_generator.meshing.backend_interface import LocalProceduralMeshingBackend, MeshRequest
from ai_mesh_generator.output.result_packager import package_result, validate_result_package
from ai_mesh_generator.recipe.guard import apply_recipe_guard
from ai_mesh_generator.recipe.recipe_schema import validate_mesh_recipe
from ai_mesh_generator.recipe.recipe_writer import build_mesh_recipe, write_recipe
from cae_mesh_common.io.package_reader import extract_job_package


def run_mesh_job(job: Path | str, model: Path | str, output: Path | str, backend: str = "LOCAL_PROCEDURAL") -> dict:
    output = Path(output)
    workdir = output.with_suffix("")
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    job_dir = extract_job_package(job, workdir / "input")
    validate_input_package_dir(job_dir)
    assembly = extract_features(heal_geometry(import_input_assembly(job_dir)))
    graph_dir = workdir / "graph"
    graph_path = build_and_save_graph(assembly, graph_dir)
    graph = build_amg_graph(assembly)
    model_artifact = load_model(model)
    prediction = predict_recipe_signals(model_artifact, graph, assembly)
    guarded = apply_recipe_guard(prediction, assembly)
    recipe = build_mesh_recipe(assembly["sample_id"], prediction, guarded, backend=backend)
    validate_mesh_recipe(recipe)
    write_recipe(recipe, workdir / "mesh_recipe_predicted.json")
    mesh_output = workdir / "result"
    if backend == "ANSA_BATCH":
        backend_impl = AnsaCommandBackend(AnsaBackendConfig(dry_run=True))
    else:
        backend_impl = LocalProceduralMeshingBackend()
    mesh_result = backend_impl.run(MeshRequest(assembly["sample_id"], assembly, recipe, mesh_output, backend=backend))
    package_path = package_result(mesh_output, output)
    validation = validate_result_package(package_path)
    summary = {
        "sample_id": assembly["sample_id"],
        "graph_path": str(graph_path),
        "mesh_result": mesh_result.to_dict(),
        "result_package": str(package_path),
        "result_validation": validation,
    }
    (workdir / "amg_run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
