from __future__ import annotations

import csv
import json
from pathlib import Path


def import_input_assembly(job_dir: Path | str) -> dict:
    job_dir = Path(job_dir)
    assembly_path = job_dir / "metadata" / "assembly.json"
    if assembly_path.exists():
        return json.loads(assembly_path.read_text(encoding="utf-8"))
    product_tree = json.loads((job_dir / "metadata" / "product_tree.json").read_text(encoding="utf-8"))
    material_library = json.loads((job_dir / "metadata" / "material_library.json").read_text(encoding="utf-8"))
    parts = []
    with (job_dir / "metadata" / "part_attributes.csv").open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            parts.append(
                {
                    "part_uid": row["part_uid"],
                    "name": row["name"],
                    "material_id": row["material_id"],
                    "strategy": row.get("representation_hint", "shell"),
                    "nominal_thickness": float(row.get("nominal_thickness", 1.0)),
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
            row["preserve_hole"] = str(row.get("preserve_hole", "True")).lower() == "true"
            row["confidence"] = float(row.get("confidence", 1.0))
            connections.append(row)
    return {
        "sample_id": product_tree["assembly_id"],
        "schema_version": "0.1.0",
        "units": "mm",
        "parts": parts,
        "product_tree": product_tree,
        "material_library": material_library,
        "connections": connections,
        "boundary_named_sets": {},
        "defects": [],
    }
