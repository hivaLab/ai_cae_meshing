from __future__ import annotations

import csv
import json
from pathlib import Path

from cae_mesh_common.schema.validators import SchemaValidationError, validate_json_file


def validate_input_package_dir(job_dir: Path | str) -> dict:
    job_dir = Path(job_dir)
    manifest = validate_json_file(job_dir / "metadata" / "manifest.json", "input_package.schema.json")
    required = [
        job_dir / manifest["geometry"]["assembly_step"],
        job_dir / manifest["metadata"]["product_tree"],
        job_dir / manifest["metadata"]["part_attributes"],
        job_dir / manifest["metadata"]["material_library"],
        job_dir / manifest["metadata"]["connections"],
        job_dir / manifest["metadata"]["mesh_profile"],
        job_dir / manifest["metadata"].get("boundary_named_sets", "metadata/boundary_named_sets.json"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SchemaValidationError(f"missing input package artifacts: {missing}")
    validate_json_file(job_dir / manifest["metadata"]["product_tree"], "product_tree.schema.json")
    validate_json_file(job_dir / manifest["metadata"]["mesh_profile"], "mesh_profile.schema.json")
    material_library = validate_json_file(job_dir / manifest["metadata"]["material_library"], "material_library.schema.json")
    material_ids = {item["material_id"] for item in material_library["materials"]}
    part_ids: set[str] = set()
    with (job_dir / manifest["metadata"]["part_attributes"]).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row.get("part_uid"):
                raise SchemaValidationError("part_attributes.csv: part_uid is required")
            part_ids.add(row["part_uid"])
            if row.get("material_id") not in material_ids:
                raise SchemaValidationError(f"part_attributes.csv: unknown material {row.get('material_id')}")
    with (job_dir / manifest["metadata"]["connections"]).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            a = row.get("part_uid_a") or row.get("master_part_uid")
            b = row.get("part_uid_b") or row.get("slave_part_uid")
            if a not in part_ids or b not in part_ids:
                raise SchemaValidationError(f"connections.csv: unknown part reference {a}->{b}")
    return {"manifest": manifest, "valid": True}
