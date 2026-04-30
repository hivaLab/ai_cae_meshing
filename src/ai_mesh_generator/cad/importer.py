from __future__ import annotations

import csv
import json
from pathlib import Path

from cae_mesh_common.cad.step_io import inspect_step_brep


def import_input_assembly(job_dir: Path | str) -> dict:
    job_dir = Path(job_dir)
    assembly_path = job_dir / "metadata" / "assembly.json"
    if assembly_path.exists():
        return _attach_geometry_source(json.loads(assembly_path.read_text(encoding="utf-8")), job_dir)
    product_tree = json.loads((job_dir / "metadata" / "product_tree.json").read_text(encoding="utf-8"))
    material_library = json.loads((job_dir / "metadata" / "material_library.json").read_text(encoding="utf-8"))
    parts = []
    with (job_dir / "metadata" / "part_attributes.csv").open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            parts.append(
                {
                    "part_uid": row["part_uid"],
                    "name": row.get("name") or row.get("part_name", row["part_uid"]),
                    "material_id": row["material_id"],
                    "strategy": row.get("representation_hint", "shell"),
                    "nominal_thickness": float(row.get("nominal_thickness") or row.get("nominal_thickness_mm", 1.0)),
                    "dimensions": {"length": 100.0, "width": 50.0, "height": 20.0},
                    "features": [],
                    "face_labels": [],
                    "ports": [],
                    "face_signatures": [],
                }
            )
    connections = []
    with (job_dir / "metadata" / "connections.csv").open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["part_uid_a"] = row.get("part_uid_a") or row.get("master_part_uid", "")
            row["part_uid_b"] = row.get("part_uid_b") or row.get("slave_part_uid", "")
            row["preserve_hole"] = str(row.get("preserve_hole", "True")).lower() == "true"
            row["confidence"] = float(row.get("confidence", 1.0))
            connections.append(row)
    return _attach_geometry_source({
        "sample_id": product_tree["assembly_id"],
        "schema_version": "0.1.0",
        "units": "mm",
        "parts": parts,
        "product_tree": product_tree,
        "material_library": material_library,
        "connections": connections,
        "boundary_named_sets": {},
        "defects": [],
    }, job_dir)


def _attach_geometry_source(assembly: dict, job_dir: Path) -> dict:
    assembly = dict(assembly)
    step_file = job_dir / "geometry" / "assembly.step"
    descriptor_only = True
    step_info = {"exists": False}
    if step_file.exists():
        step_info = inspect_step_brep(step_file)
        descriptor_only = bool(step_info["descriptor_only"])
    assembly["geometry_source"] = {
        "input_package_dir": str(job_dir.resolve()),
        "step_file": str(step_file.resolve()) if step_file.exists() else None,
        "step_descriptor_only": descriptor_only,
        "cad_kernel": "STEP_AP242_BREP" if step_file.exists() and not descriptor_only else "PROCEDURAL_DESCRIPTOR",
        "step_validation": step_info,
    }
    return assembly
