from __future__ import annotations

from pathlib import Path
from typing import Any

from cae_mesh_common.bdf.bdf_reader import BDFModel, read_bdf


def validate_bdf_traceability(
    bdf_path: Path | str,
    plan: dict[str, Any],
    ansa_recipe_application: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that exported BDF entities remain traceable to source parts.

    The BDF validator checks structural references. This check verifies the
    production mapping expected by the ANSA adapter: material cards exist,
    native solid property records carry the planned material IDs, connector
    properties cover CBUSH elements, and mass-only parts are reflected by CONM2.
    """

    model = read_bdf(bdf_path)
    application = ansa_recipe_application or {}
    native = application.get("native_entity_generation", {})
    solid_assignment = native.get("solid_tetra", {}).get("solver_card_assignment", {})
    property_application = application.get("property_application", {})
    records = []
    failures = []

    material_result = _validate_materials(model, plan)
    records.extend(material_result["records"])
    failures.extend(material_result["failures"])

    shell_result = _validate_shell_assignments(model, property_application)
    records.extend(shell_result["records"])
    failures.extend(shell_result["failures"])

    solid_result = _validate_solid_assignments(model, solid_assignment)
    records.extend(solid_result["records"])
    failures.extend(solid_result["failures"])

    connector_result = _validate_connectors(model, plan)
    records.extend(connector_result["records"])
    failures.extend(connector_result["failures"])

    mass_result = _validate_masses(model, plan, native)
    records.extend(mass_result["records"])
    failures.extend(mass_result["failures"])

    coverage_result = _validate_part_representation_coverage(model, plan, records)
    records.extend(coverage_result["records"])
    failures.extend(coverage_result["failures"])

    source_part_count = len(plan.get("parts", []))
    mapped_part_uids = sorted(
        {
            str(record.get("part_uid"))
            for record in records
            if record.get("part_uid") and record.get("status") == "passed"
        }
    )
    return {
        "passed": not failures,
        "source_part_count": source_part_count,
        "mapped_part_uid_count": len(mapped_part_uids),
        "mapped_part_uids": mapped_part_uids,
        "record_count": len(records),
        "failure_count": len(failures),
        "failures": failures,
        "records": records,
        "method": "bdf_property_material_element_traceability",
        "representation_policy": "no_silent_cad_part_omission",
    }


def _validate_materials(model: BDFModel, plan: dict[str, Any]) -> dict[str, Any]:
    records = []
    failures = []
    for material in plan.get("materials", []):
        mid = int(material["mid"])
        status = "passed" if mid in model.materials else "failed"
        record = {
            "kind": "material",
            "material_id": material["material_id"],
            "mid": mid,
            "status": status,
        }
        records.append(record)
        if status != "passed":
            failures.append({**record, "reason": "MAT1 card is missing"})
    return {"records": records, "failures": failures}


def _validate_shell_assignments(model: BDFModel, property_application: dict[str, Any]) -> dict[str, Any]:
    records = []
    failures = []
    for assignment in property_application.get("assignments", []):
        pid = int(assignment["pshell_id"])
        expected_mid = int(assignment["mid"])
        prop = model.properties.get(pid)
        element_count = _element_count_by_pid(model, pid)
        thickness = float(prop.get("thickness", 0.0)) if prop else 0.0
        if element_count == 0:
            records.append(
                {
                    "kind": "shell_property",
                    "part_uid": assignment.get("part_uid"),
                    "property_id": pid,
                    "expected_mid": expected_mid,
                    "element_count": element_count,
                    "thickness": thickness,
                    "status": "not_applicable_no_shell_elements",
                }
            )
            continue
        status = (
            "passed"
            if prop
            and prop.get("type") == "PSHELL"
            and int(prop.get("mid", 0)) == expected_mid
            and thickness > 0.0
            else "failed"
        )
        record = {
            "kind": "shell_property",
            "part_uid": assignment.get("part_uid"),
            "property_id": pid,
            "expected_mid": expected_mid,
            "element_count": element_count,
            "thickness": thickness,
            "status": status,
        }
        records.append(record)
        if status != "passed":
            failures.append({**record, "reason": "PSHELL material, thickness, or element coverage does not match source part"})
    return {"records": records, "failures": failures}


def _validate_solid_assignments(model: BDFModel, solid_assignment: dict[str, Any]) -> dict[str, Any]:
    records = []
    failures = []
    for assignment in solid_assignment.get("records", []):
        pid = int(assignment["new_property_id"])
        expected_mid = int(assignment["material_numeric_id"])
        prop = model.properties.get(pid)
        element_count = _element_count_by_pid(model, pid)
        property_matches = prop and prop.get("type") == "PSOLID" and int(prop.get("mid", 0)) == expected_mid
        if property_matches and element_count > 0:
            status = "passed"
        elif property_matches and element_count == 0:
            status = "not_applicable_no_exported_solid_elements"
        else:
            status = "failed"
        record = {
            "kind": "solid_property",
            "part_uid": assignment.get("part_uid"),
            "property_id": pid,
            "expected_mid": expected_mid,
            "element_count": element_count,
            "solid_type_counts": assignment.get("solid_type_counts", {}),
            "status": status,
        }
        records.append(record)
        if status == "failed":
            failures.append({**record, "reason": "PSOLID material or element distribution does not match source part"})
    return {"records": records, "failures": failures}


def _validate_connectors(model: BDFModel, plan: dict[str, Any]) -> dict[str, Any]:
    connections = plan.get("connections", [])
    connector_count = len(connections)
    if connector_count == 0:
        return {"records": [], "failures": []}
    pid = int(plan.get("connector_property", {}).get("property_id", 9001))
    prop = model.properties.get(pid)
    cbush_count = sum(1 for element in model.elements.values() if element.get("type") == "CBUSH" and element.get("pid") == pid)
    status = "passed" if prop and prop.get("type") == "PBUSH" and cbush_count >= connector_count else "failed"
    record = {
        "kind": "connector_property",
        "property_id": pid,
        "expected_connection_count": connector_count,
        "cbush_count": cbush_count,
        "status": status,
    }
    records = [record]
    if status == "passed":
        connected_parts = sorted(
            {
                str(value)
                for connection in connections
                for value in (connection.get("part_uid_a"), connection.get("part_uid_b"))
                if value
            }
        )
        records.extend(
            {
                "kind": "connector_attachment",
                "part_uid": part_uid,
                "property_id": pid,
                "status": "passed",
            }
            for part_uid in connected_parts
        )
    failures = [] if status == "passed" else [{**record, "reason": "PBUSH/CBUSH connector coverage is incomplete"}]
    return {"records": records, "failures": failures}


def _validate_masses(model: BDFModel, plan: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    expected = int(plan.get("summary", {}).get("mass_only_part_count", 0))
    if expected == 0:
        return {"records": [], "failures": []}
    native_records = native.get("masses", {}).get("records", [])
    if native_records:
        records = []
        failures = []
        for mass in native_records:
            eid = int(mass["element_id"])
            element = model.elements.get(eid)
            status = "passed" if element and element.get("type") == "CONM2" else "failed"
            record = {
                "kind": "mass_entity",
                "part_uid": mass.get("part_uid"),
                "element_id": eid,
                "grid_id": mass.get("grid_id"),
                "status": status,
            }
            records.append(record)
            if status != "passed":
                failures.append({**record, "reason": "CONM2 mass entity is missing from BDF"})
        if len(native_records) < expected:
            failures.append(
                {
                    "kind": "mass_entity",
                    "expected_mass_only_part_count": expected,
                    "native_mass_record_count": len(native_records),
                    "status": "failed",
                    "reason": "native mass record coverage is incomplete",
                }
            )
        return {"records": records, "failures": failures}
    conm2_count = sum(1 for element in model.elements.values() if element.get("type") == "CONM2")
    status = "passed" if conm2_count >= expected else "failed"
    record = {
        "kind": "mass_entity",
        "expected_mass_only_part_count": expected,
        "conm2_count": conm2_count,
        "status": status,
    }
    failures = [] if status == "passed" else [{**record, "reason": "CONM2 mass coverage is incomplete"}]
    return {"records": [record], "failures": failures}


def _validate_part_representation_coverage(
    model: BDFModel, plan: dict[str, Any], existing_records: list[dict[str, Any]]
) -> dict[str, Any]:
    records = []
    failures = []
    passed_by_part: dict[str, list[dict[str, Any]]] = {}
    for record in existing_records:
        part_uid = record.get("part_uid")
        if part_uid and record.get("status") == "passed":
            passed_by_part.setdefault(str(part_uid), []).append(record)

    for part in plan.get("parts", []):
        part_uid = str(part.get("part_uid", ""))
        strategy = _normalize_strategy(str(part.get("strategy", "")))
        if not part_uid:
            continue
        representation = _representation_for_strategy(strategy)
        part_records = passed_by_part.get(part_uid, [])
        if representation == "approved_exclude":
            approved = bool(part.get("approved_exclude", False)) or bool(part.get("approved_exclude_reason"))
            status = "passed" if approved else "failed"
            record = {
                "kind": "part_representation",
                "part_uid": part_uid,
                "representation": "approved_exclude",
                "status": status,
            }
            records.append(record)
            if status != "passed":
                failures.append({**record, "reason": "CAD part is excluded without explicit approval"})
            continue
        if representation == "manual_review":
            records.append(
                {
                    "kind": "part_representation",
                    "part_uid": part_uid,
                    "representation": "manual_review",
                    "status": "manual_review",
                }
            )
            continue
        status = "passed" if part_records else "failed"
        record = {
            "kind": "part_representation",
            "part_uid": part_uid,
            "representation": representation,
            "status": status,
            "trace_record_count": len(part_records),
        }
        records.append(record)
        if status != "passed":
            failures.append(
                {
                    **record,
                    "reason": "missing_representation_failure",
                    "allowed_representations": [
                        "explicit_mesh",
                        "connector",
                        "mass",
                        "approved_exclude",
                        "manual_review",
                    ],
                }
            )
    return {"records": records, "failures": failures}


def _normalize_strategy(strategy: str) -> str:
    lookup = {
        "SHELL_MIDSURFACE": "shell",
        "SOLID_TETRA": "solid",
        "CONNECTOR_REPLACEMENT": "connector",
        "MASS_ONLY": "mass_only",
        "APPROVED_EXCLUDE": "approved_exclude",
        "MANUAL_REVIEW": "manual_review",
    }
    return lookup.get(strategy.upper(), strategy.lower())


def _representation_for_strategy(strategy: str) -> str:
    if strategy in {"shell", "solid", "solid_tet"}:
        return "explicit_mesh"
    if strategy == "mass_only":
        return "mass"
    if strategy == "connector":
        return "connector"
    if strategy == "approved_exclude":
        return "approved_exclude"
    if strategy == "manual_review":
        return "manual_review"
    return "explicit_mesh"


def _element_count_by_pid(model: BDFModel, pid: int) -> int:
    return sum(1 for element in model.elements.values() if element.get("pid") == pid)
