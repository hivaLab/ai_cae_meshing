from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ai_mesh_generator.meshing.backend_interface import LocalProceduralMeshingBackend, MeshRequest
from cae_mesh_common.io.package_writer import zip_directory
from cae_dataset_factory.cad.cad_exporter import export_assembly_step
from cae_dataset_factory.graph.brep_graph_builder import build_brep_graph
from cae_dataset_factory.graph.pyg_exporter import export_graph
from cae_dataset_factory.labeling.connection_oracle import connection_labels
from cae_dataset_factory.labeling.edge_semantic_oracle import edge_labels
from cae_dataset_factory.labeling.face_semantic_oracle import face_labels
from cae_dataset_factory.labeling.failure_labeler import failure_risks
from cae_dataset_factory.labeling.part_strategy_oracle import part_strategy
from cae_dataset_factory.labeling.size_field_oracle import size_for_part
from cae_dataset_factory.meshing.mesh_recipe_writer import write_mesh_recipe


def build_oracle_labels(assembly: dict[str, Any]) -> dict[str, Any]:
    part_labels = [{"part_uid": part["part_uid"], "strategy": part_strategy(part)} for part in assembly["parts"]]
    face_records = [record for part in assembly["parts"] for record in face_labels(part)]
    edge_records = [record for part in assembly["parts"] for record in edge_labels(part)]
    defects_by_part: dict[str, int] = {}
    for defect in assembly.get("defects", []):
        defects_by_part[defect["part_uid"]] = defects_by_part.get(defect["part_uid"], 0) + 1
    size_records = [
        {"part_uid": part["part_uid"], "target_size": size_for_part(part, defects_by_part.get(part["part_uid"], 0))}
        for part in assembly["parts"]
    ]
    repair_actions = [
        {"target_uid": defect["part_uid"], "action": defect["repair_action"], "defect_uid": defect["defect_uid"]}
        for defect in assembly.get("defects", [])
    ]
    return {
        "sample_id": assembly["sample_id"],
        "part_labels": part_labels,
        "face_labels": face_records,
        "edge_labels": edge_records,
        "size_field_labels": size_records,
        "connection_labels": connection_labels(assembly.get("connections", [])),
        "failure_risks": failure_risks(assembly),
        "repair_actions": repair_actions,
    }


def build_oracle_recipe(assembly: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any]:
    base_size = sum(item["target_size"] for item in labels["size_field_labels"]) / len(labels["size_field_labels"])
    return {
        "recipe_id": f"recipe_{assembly['sample_id']}",
        "sample_id": assembly["sample_id"],
        "backend": "LOCAL_PROCEDURAL",
        "base_size": round(base_size, 4),
        "part_strategies": [
            {"part_uid": item["part_uid"], "strategy": item["strategy"], "confidence": 1.0}
            for item in labels["part_labels"]
        ],
        "size_fields": [
            {"part_uid": item["part_uid"], "target_size": item["target_size"], "confidence": 1.0}
            for item in labels["size_field_labels"]
        ],
        "connections": assembly.get("connections", []),
        "guard": {"source": "oracle", "manual_review": []},
    }


def write_sample(assembly: dict[str, Any], dataset_dir: Path | str, mesh_profile: dict[str, Any]) -> dict[str, Any]:
    dataset_dir = Path(dataset_dir)
    sample_id = assembly["sample_id"]
    sample_dir = dataset_dir / "samples" / sample_id
    input_dir = sample_dir / "input_package"
    metadata_dir = input_dir / "metadata"
    geometry_dir = input_dir / "geometry"
    labels_dir = sample_dir / "labels"
    graph_dir = sample_dir / "graphs"
    mesh_dir = sample_dir / "mesh"
    for path in [metadata_dir, geometry_dir, labels_dir, graph_dir, mesh_dir]:
        path.mkdir(parents=True, exist_ok=True)

    export_assembly_step(geometry_dir / "assembly.step", sample_id, assembly["parts"])
    manifest = {
        "job_id": sample_id,
        "schema_version": "0.1.0",
        "unit": "mm",
        "units": "mm",
        "solver": "NASTRAN",
        "analysis_type": ["linear_static", "modal", "frequency_response"],
        "geometry_file": "geometry/assembly.step",
        "mesh_profile": "metadata/mesh_profile.yaml",
        "product_tree_file": "metadata/product_tree.json",
        "part_attribute_file": "metadata/part_attributes.csv",
        "connection_file": "metadata/connections.csv",
        "boundary_named_set_file": "metadata/boundary_named_sets.json",
        "geometry": {"assembly_step": "geometry/assembly.step"},
        "metadata": {
            "product_tree": "metadata/product_tree.json",
            "part_attributes": "metadata/part_attributes.csv",
            "material_library": "metadata/material_library.json",
            "connections": "metadata/connections.csv",
            "mesh_profile": "metadata/mesh_profile.yaml",
        },
    }
    (metadata_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (metadata_dir / "product_tree.json").write_text(json.dumps(assembly["product_tree"], indent=2, sort_keys=True), encoding="utf-8")
    (metadata_dir / "material_library.json").write_text(json.dumps(assembly["material_library"], indent=2, sort_keys=True), encoding="utf-8")
    (metadata_dir / "boundary_named_sets.json").write_text(json.dumps(assembly["boundary_named_sets"], indent=2, sort_keys=True), encoding="utf-8")
    (metadata_dir / "mesh_profile.yaml").write_text(yaml.safe_dump(mesh_profile, sort_keys=True), encoding="utf-8")
    (metadata_dir / "assembly.json").write_text(json.dumps(assembly, indent=2, sort_keys=True), encoding="utf-8")
    (sample_dir / "assembly.json").write_text(json.dumps(assembly, indent=2, sort_keys=True), encoding="utf-8")

    with (metadata_dir / "part_attributes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "part_uid",
                "name",
                "part_name",
                "material_id",
                "manufacturing_process",
                "nominal_thickness",
                "nominal_thickness_mm",
                "min_thickness_mm",
                "max_thickness_mm",
                "component_role",
                "mass_handling",
                "mesh_priority",
                "representation_hint",
            ],
        )
        writer.writeheader()
        for part in assembly["parts"]:
            mass_handling = "mass_only" if part["strategy"] == "mass_only" else "mesh"
            writer.writerow(
                {
                    "part_uid": part["part_uid"],
                    "name": part["name"],
                    "part_name": part["name"],
                    "material_id": part["material_id"],
                    "manufacturing_process": _manufacturing_process(part),
                    "nominal_thickness": part["nominal_thickness"],
                    "nominal_thickness_mm": part["nominal_thickness"],
                    "min_thickness_mm": max(0.0, float(part["nominal_thickness"]) * 0.85),
                    "max_thickness_mm": float(part["nominal_thickness"]) * 1.15,
                    "component_role": _component_role(part),
                    "mass_handling": mass_handling,
                    "mesh_priority": "high" if part["strategy"] in {"solid", "mass_only"} else "normal",
                    "representation_hint": part["strategy"],
                }
            )

    with (metadata_dir / "connections.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "connection_uid",
                "type",
                "part_uid_a",
                "part_uid_b",
                "master_part_uid",
                "slave_part_uid",
                "feature_hint",
                "diameter_mm",
                "stiffness_profile",
                "washer_radius_mm",
                "preserve_hole",
                "confidence",
            ],
        )
        writer.writeheader()
        for connection in assembly.get("connections", []):
            row = dict(connection)
            row.setdefault("master_part_uid", connection["part_uid_a"])
            row.setdefault("slave_part_uid", connection["part_uid_b"])
            row.setdefault("feature_hint", "hole_pair_auto")
            row.setdefault("diameter_mm", 3.0)
            row.setdefault("stiffness_profile", "M3_default")
            row.setdefault("washer_radius_mm", 5.0)
            writer.writerow(row)

    labels = build_oracle_labels(assembly)
    recipe = build_oracle_recipe(assembly, labels)
    label_path = labels_dir / "labels.parquet"
    pd.DataFrame([_flatten_labels(labels, recipe)]).to_parquet(label_path, index=False)
    (labels_dir / "labels.json").write_text(json.dumps(labels, indent=2, sort_keys=True), encoding="utf-8")
    recipe_path = sample_dir / "mesh_recipe_oracle.json"
    write_mesh_recipe(recipe, recipe_path)

    graph = build_brep_graph(assembly)
    graph_path = export_graph(graph, graph_dir / "graph.pt")
    mesh_result = LocalProceduralMeshingBackend().run(MeshRequest(sample_id, assembly, recipe, mesh_dir))
    input_zip = zip_directory(input_dir, sample_dir / "LGE_CAE_MESH_JOB.zip")

    return {
        "sample_id": sample_id,
        "sample_dir": str(sample_dir),
        "input_zip": str(input_zip),
        "bdf_path": str(mesh_result.bdf_path),
        "graph_path": str(graph_path),
        "label_path": str(label_path),
        "label_json_path": str(labels_dir / "labels.json"),
        "recipe_path": str(recipe_path),
        "qa_metrics_path": str(mesh_result.qa_metrics_path),
        "accepted": mesh_result.accepted,
        "oracle_base_size": recipe["base_size"],
        "part_count": len(assembly["parts"]),
        "connection_count": len(assembly.get("connections", [])),
        "defect_count": len(assembly.get("defects", [])),
    }


def _flatten_labels(labels: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": labels["sample_id"],
        "part_label_count": len(labels["part_labels"]),
        "face_label_count": len(labels["face_labels"]),
        "edge_label_count": len(labels["edge_labels"]),
        "failure_risk_mean": sum(item["risk"] for item in labels["failure_risks"]) / len(labels["failure_risks"]),
        "repair_action_count": len(labels["repair_actions"]),
        "oracle_base_size": recipe["base_size"],
        "labels_json": json.dumps(labels, sort_keys=True),
    }


def _manufacturing_process(part: dict[str, Any]) -> str:
    name = str(part.get("name", ""))
    if "plastic" in name or "cover" in name:
        return "injection_plastic"
    if "pcb" in name:
        return "electronic_module"
    if "screw" in name:
        return "purchased_fastener"
    return "sheet_metal"


def _component_role(part: dict[str, Any]) -> str:
    name = str(part.get("name", ""))
    for role in ["base", "cover", "bracket", "fastener", "motor"]:
        if role in name:
            return role
    if "pcb" in name:
        return "electronic_module"
    return "unknown"
