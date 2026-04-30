from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from cae_mesh_common.cad.step_io import inspect_step_brep
from cae_mesh_common.cad.topology import DEFAULT_STEP_MATERIAL_LIBRARY, extract_step_assembly_topology


def import_input_assembly(job_dir: Path | str) -> dict:
    job_dir = Path(job_dir)
    assembly_path = job_dir / "metadata" / "assembly.json"
    if assembly_path.exists():
        return _attach_geometry_source(json.loads(assembly_path.read_text(encoding="utf-8")), job_dir)
    step_file = job_dir / "geometry" / "assembly.step"
    if step_file.exists():
        step_info = inspect_step_brep(step_file)
        if bool(step_info.get("is_brep")) and not bool(step_info.get("descriptor_only")):
            manifest = _read_json_if_exists(job_dir / "metadata" / "manifest.json")
            material_library = _read_json_if_exists(job_dir / "metadata" / "material_library.json") or DEFAULT_STEP_MATERIAL_LIBRARY
            connections = _read_connections_if_exists(job_dir / "metadata" / "connections.csv")
            assembly = extract_step_assembly_topology(
                step_file,
                sample_id=str(manifest.get("job_id") or step_file.stem),
                material_library=material_library,
                connections=connections,
            )
            return _attach_geometry_source(_apply_part_attributes(assembly, _read_part_attributes_if_exists(job_dir)), job_dir)
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


def write_step_input_package(
    source_step: Path | str,
    output_dir: Path | str,
    sample_id: str | None = None,
) -> tuple[Path, dict]:
    """Create a valid AMG input package from an external STEP AP242 B-Rep file.

    The package intentionally does not write ``metadata/assembly.json``. AMG
    must re-import the STEP and extract topology rather than relying on a
    procedural descriptor.
    """

    source = Path(source_step)
    job_dir = Path(output_dir)
    geometry_dir = job_dir / "geometry"
    metadata_dir = job_dir / "metadata"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    packaged_step = geometry_dir / "assembly.step"
    if source.resolve() != packaged_step.resolve():
        shutil.copy2(source, packaged_step)
    assembly = extract_step_assembly_topology(packaged_step, sample_id=sample_id or source.stem)

    manifest = {
        "job_id": assembly["sample_id"],
        "schema_version": "0.1.0",
        "unit": "mm",
        "units": "mm",
        "solver": "NASTRAN",
        "analysis_type": ["linear_static"],
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
            "boundary_named_sets": "metadata/boundary_named_sets.json",
            "step_topology": "metadata/step_topology.json",
        },
    }
    (metadata_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (metadata_dir / "product_tree.json").write_text(
        json.dumps(assembly["product_tree"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (metadata_dir / "material_library.json").write_text(
        json.dumps(assembly["material_library"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (metadata_dir / "boundary_named_sets.json").write_text("{}", encoding="utf-8")
    (metadata_dir / "step_topology.json").write_text(json.dumps(assembly, indent=2, sort_keys=True), encoding="utf-8")
    _write_part_attributes(metadata_dir / "part_attributes.csv", assembly)
    _write_connections(metadata_dir / "connections.csv", assembly.get("connections", []))
    _write_mesh_profile(metadata_dir / "mesh_profile.yaml")
    return job_dir, assembly


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
        "cad_kernel": assembly.get("geometry_source", {}).get(
            "cad_kernel",
            "STEP_AP242_BREP" if step_file.exists() and not descriptor_only else "PROCEDURAL_DESCRIPTOR",
        ),
        "step_validation": step_info,
        "topology_extraction": assembly.get("geometry_source", {}).get("topology_extraction"),
    }
    return assembly


def _read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_connections_if_exists(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            part_uid_a = row.get("part_uid_a") or row.get("master_part_uid")
            part_uid_b = row.get("part_uid_b") or row.get("slave_part_uid")
            if not part_uid_a or not part_uid_b:
                continue
            records.append(
                {
                    "connection_uid": row.get("connection_uid") or f"connection_{len(records) + 1:04d}",
                    "type": row.get("type") or "tied",
                    "part_uid_a": part_uid_a,
                    "part_uid_b": part_uid_b,
                    "master_part_uid": row.get("master_part_uid") or part_uid_a,
                    "slave_part_uid": row.get("slave_part_uid") or part_uid_b,
                    "feature_hint": row.get("feature_hint") or "external_step_metadata",
                    "diameter_mm": float(row.get("diameter_mm") or 3.0),
                    "stiffness_profile": row.get("stiffness_profile") or "STEP_default_tied",
                    "washer_radius_mm": float(row.get("washer_radius_mm") or 5.0),
                    "preserve_hole": str(row.get("preserve_hole", "False")).lower() == "true",
                    "confidence": float(row.get("confidence") or 0.75),
                }
            )
    return records or None


def _read_part_attributes_if_exists(job_dir: Path) -> dict[str, dict]:
    path = job_dir / "metadata" / "part_attributes.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return {row["part_uid"]: row for row in csv.DictReader(handle) if row.get("part_uid")}


def _apply_part_attributes(assembly: dict, attributes: dict[str, dict]) -> dict:
    if not attributes:
        return assembly
    material_ids = {item["material_id"] for item in assembly.get("material_library", {}).get("materials", [])}
    for part in assembly.get("parts", []):
        row = attributes.get(part["part_uid"]) or attributes.get(part.get("source_product_name", ""))
        if not row:
            continue
        if row.get("material_id") in material_ids:
            part["material_id"] = row["material_id"]
        if row.get("representation_hint"):
            part["strategy"] = row["representation_hint"]
        thickness = row.get("nominal_thickness") or row.get("nominal_thickness_mm")
        if thickness:
            part["nominal_thickness"] = float(thickness)
        if row.get("name") or row.get("part_name"):
            part["name"] = row.get("name") or row.get("part_name")
    return assembly


def _write_part_attributes(path: Path, assembly: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
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
            "source_product_name",
            "source_solid_index",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for part in assembly["parts"]:
            thickness = float(part["nominal_thickness"])
            writer.writerow(
                {
                    "part_uid": part["part_uid"],
                    "name": part["name"],
                    "part_name": part["name"],
                    "material_id": part["material_id"],
                    "manufacturing_process": "external_step_import",
                    "nominal_thickness": thickness,
                    "nominal_thickness_mm": thickness,
                    "min_thickness_mm": max(0.0, thickness * 0.85),
                    "max_thickness_mm": thickness * 1.15,
                    "component_role": "external_step_part",
                    "mass_handling": "mesh",
                    "mesh_priority": "high",
                    "representation_hint": part["strategy"],
                    "source_product_name": part["source_product_name"],
                    "source_solid_index": part["source_solid_index"],
                }
            )


def _write_connections(path: Path, connections: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
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
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for connection in connections:
            row = dict(connection)
            row.setdefault("master_part_uid", row.get("part_uid_a", ""))
            row.setdefault("slave_part_uid", row.get("part_uid_b", ""))
            row.setdefault("feature_hint", "bbox_nearest_topology_contact")
            row.setdefault("diameter_mm", 3.0)
            row.setdefault("stiffness_profile", "STEP_default_tied")
            row.setdefault("washer_radius_mm", 5.0)
            row.setdefault("preserve_hole", False)
            row.setdefault("confidence", 0.75)
            writer.writerow(row)


def _write_mesh_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "profile_id: external_step_ap242_ingestion",
                "units: mm",
                "target_solver: nastran",
                "shell:",
                "  nominal_size: 8.0",
                "  min_size: 2.0",
                "  max_size: 16.0",
                "solid:",
                "  nominal_size: 8.0",
                "  min_size: 2.0",
                "  max_size: 16.0",
                "quality:",
                "  max_aspect_ratio: 8.0",
                "  max_skew_deg: 60.0",
                "  min_scaled_jacobian: 0.1",
                "",
            ]
        ),
        encoding="utf-8",
    )
