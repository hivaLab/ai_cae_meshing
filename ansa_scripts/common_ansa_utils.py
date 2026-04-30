from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_mesh_generator.meshing.ansa_quality import summarize_ansa_quality_statistics
from ai_mesh_generator.meshing.ansa_recipe import apply_solver_deck_recipe


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_result_manifest(output_dir: str, success: bool, details: dict | None = None) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"success": success, "details": details or {}}
    path = output / "ansa_result_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def run_ansa_batch_adapter(config_path: str, mode: str) -> int:
    config = load_config(config_path)
    try:
        details = _run_explicit_ansa_export(config, mode)
    except Exception as exc:
        write_result_manifest(
            config["output_dir"],
            False,
            {
                "mode": mode,
                "error": str(exc),
                "fallback_enabled": False,
            },
        )
        return 2
    write_result_manifest(config["output_dir"], True, details)
    return 0


def _run_explicit_ansa_export(config: dict, mode: str) -> dict:
    _require_ansa_runtime()
    output_dir = Path(config["output_dir"])
    stage_dir = Path(config["stage_dir"])
    solver_dir = output_dir / "solver_deck"
    native_dir = output_dir / "native"
    solver_dir.mkdir(parents=True, exist_ok=True)
    native_dir.mkdir(parents=True, exist_ok=True)

    assembly = load_config(config["assembly_json"])
    plan = load_config(config["ansa_recipe_plan_json"])
    final_bdf = Path(config["expected_solver_deck"])
    final_bdf.parent.mkdir(parents=True, exist_ok=True)
    step_file = Path(str(config.get("step_file") or ""))
    if config.get("step_descriptor_only", True):
        raise RuntimeError("ANSA batch meshing requires a real AP242 B-Rep STEP file, not a descriptor")
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file is missing: {step_file}")

    from ansa import base, batchmesh, constants, mesh, session

    session.New("discard")
    base.SetCurrentDeck(constants.NASTRAN)
    open_status = base.Open(str(step_file))
    import_counts = _collect_counts(base, constants)
    faces = base.CollectEntities(constants.NASTRAN, None, "FACE", True) or []
    if not faces:
        raise RuntimeError(f"ANSA opened STEP but found no CAD FACE entities: {import_counts}")
    geometry_healing = _apply_geometry_healing(base, constants, faces)
    material_application = _create_ansa_materials(base, constants, plan)
    property_application = _assign_ansa_properties(base, constants, plan)
    session_application = _run_recipe_batch_sessions(base, batchmesh, constants, plan, stage_dir)
    batch_counts = _collect_counts(base, constants)
    if int(batch_counts.get("__ELEMENTS__", 0)) <= 0:
        raise RuntimeError(f"ANSA Batch Mesh Manager sessions produced no FE elements: {batch_counts}")
    native_solid_generation = _run_native_solid_tetra_meshing(base, batchmesh, constants, mesh, plan, stage_dir)
    native_solid_generation["solver_card_assignment"] = _assign_native_solid_solver_cards(
        base, constants, plan, native_solid_generation
    )
    native_entity_generation = _create_native_solver_entities(base, constants, plan, native_solid_generation)
    quality_repair_loop = _run_quality_repair_loop(base, batchmesh, constants, plan, stage_dir, session_application)
    final_counts = _collect_counts(base, constants)
    if int(native_entity_generation["solid_tetra"]["created_count"]) <= 0:
        raise RuntimeError(f"ANSA native CTETRA generation produced no solid elements: {native_entity_generation}")
    if int(native_entity_generation["connectors"]["created_count"]) < int(plan.get("summary", {}).get("connection_count", 0)):
        raise RuntimeError(f"ANSA native connector generation did not cover all planned connections: {native_entity_generation}")
    if int(native_entity_generation["masses"]["created_count"]) < int(plan.get("summary", {}).get("mass_only_part_count", 0)):
        raise RuntimeError(f"ANSA native mass generation did not cover all mass-only parts: {native_entity_generation}")
    native_path = native_dir / "model_final.ansa"
    save_status = base.SaveAs(str(native_path))
    output_status = base.OutputNastran(
        filename=str(final_bdf),
        mode="all",
        format="free",
        continuation_lines="on",
        enddata="on",
        split_pyramid="on",
        disregard_includes="on",
        beginbulk="on",
        second_as_first_solids="on",
        write_comments="off",
    )
    if not final_bdf.exists():
        raise RuntimeError(f"ANSA did not export expected solver deck: {final_bdf}")

    deck_application = apply_solver_deck_recipe(final_bdf, plan, create_missing_elements=False)
    _write_include_cards(final_bdf, solver_dir)
    recipe_application = {
        "plan_version": plan.get("plan_version"),
        "recipe_id": plan.get("recipe_id"),
        "summary": plan.get("summary", {}),
        "geometry_healing": geometry_healing,
        "material_application": material_application,
        "property_application": property_application,
        "batch_mesh_sessions": session_application,
        "native_entity_generation": native_entity_generation,
        "ansa_quality_repair_loop": quality_repair_loop,
        "solver_deck_application": deck_application,
    }
    (output_dir / "ansa_recipe_application.json").write_text(
        json.dumps(recipe_application, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {
        "mode": mode,
        "geometry_mode": config.get("geometry_mode"),
        "step_file": config.get("step_file"),
        "step_descriptor_only": False,
        "batch_meshing_manager_invoked": True,
        "batch_meshing_manager_reason": "ANSA batchmesh sessions applied AI mesh recipe parameters per part and ran Batch Mesh Manager",
        "ansa_open_step_status": open_status,
        "ansa_import_counts": import_counts,
        "ansa_batch_counts_before_native": batch_counts,
        "ansa_batch_counts": final_counts,
        "ansa_save_status": save_status,
        "ansa_output_nastran_status": output_status,
        "ansa_recipe_application": recipe_application,
        "solver_deck_recipe_application": deck_application,
        "native_entity_generation": native_entity_generation,
        "ansa_quality_repair_loop": quality_repair_loop,
        "expected_solver_deck": str(final_bdf),
        "native_model": str(native_path),
        "fallback_enabled": False,
        "node_count": int(final_counts.get("GRID", 0)),
        "element_count": int(final_counts.get("__ELEMENTS__", 0)),
        "shell_count": int(final_counts.get("SHELL", 0)),
        "solid_count": int(final_counts.get("SOLID", 0)),
        "connector_count": int(final_counts.get("CBUSH", 0))
        + int(final_counts.get("RBE2", 0))
        + int(final_counts.get("RBE3", 0)),
        "mass_count": int(final_counts.get("CONM2", 0)),
    }


def _require_ansa_runtime() -> None:
    try:
        import ansa  # noqa: F401
    except Exception as exc:
        raise RuntimeError("ANSA Python runtime is unavailable") from exc


def _collect_counts(base, constants) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entity_type in (
        "ANSAPART",
        "FACE",
        "SHELL",
        "SOLID",
        "PSHELL",
        "PSOLID",
        "MAT1",
        "PBUSH",
        "__ELEMENTS__",
        "GRID",
        "CBUSH",
        "RBE2",
        "RBE3",
        "CONM2",
    ):
        try:
            counts[entity_type] = len(base.CollectEntities(constants.NASTRAN, None, entity_type, True) or [])
        except Exception:
            counts[entity_type] = 0
    return counts


def _apply_geometry_healing(base, constants, faces) -> dict[str, object]:
    options = ["CRACKS", "TRIPLE CONS", "OVERLAPS", "NEEDLE FACES", "COLLAPSED CONS"]
    fixes = [1, 1, 1, 1, 1]
    try:
        result = base.CheckAndFixGeometry(faces, options, fixes)
    except Exception as exc:
        raise RuntimeError(f"ANSA geometry healing failed: {exc}") from exc
    remaining = len(result.get("failed", [])) if isinstance(result, dict) else 0
    return {"options": options, "remaining_error_count": remaining, "status": "completed"}


def _create_ansa_materials(base, constants, plan: dict) -> dict[str, object]:
    created = []
    for material in plan.get("materials", []):
        fields = {
            "MID": int(material["mid"]),
            "Name": str(material.get("name") or material["material_id"]),
            "E": float(material["young_modulus"]),
            "NU": float(material["poisson_ratio"]),
            "RHO": float(material["density"]),
        }
        try:
            entity = base.GetEntity(constants.NASTRAN, "MAT1", int(material["mid"]))
            if not entity:
                entity = base.CreateEntity(constants.NASTRAN, "MAT1", fields)
            else:
                base.SetEntityCardValues(constants.NASTRAN, entity, fields)
        except Exception as exc:
            raise RuntimeError(f"failed to create/update ANSA MAT1 for {material['material_id']}: {exc}") from exc
        if not entity:
            raise RuntimeError(f"failed to create/update ANSA MAT1 for {material['material_id']}")
        created.append({"material_id": material["material_id"], "mid": int(material["mid"])})
    return {"created_count": len(created), "materials": created}


def _assign_ansa_properties(base, constants, plan: dict) -> dict[str, object]:
    pshells = sorted(base.CollectEntities(constants.NASTRAN, None, "PSHELL", True) or [], key=lambda ent: ent._id)
    part_plans = [part for part in plan.get("parts", []) if part.get("solver_property_type") == "PSHELL"]
    if not pshells and part_plans:
        raise RuntimeError("ANSA imported no PSHELL properties to receive AI recipe material/thickness assignments")
    assignments = []
    for prop, part in zip(pshells, part_plans):
        fields = {
            "Name": str(part["property_name"]),
            "MID1": int(part["material_numeric_id"]),
            "T": float(part["nominal_thickness"]),
        }
        try:
            base.SetEntityCardValues(constants.NASTRAN, prop, fields)
        except Exception as exc:
            raise RuntimeError(f"failed to assign ANSA PSHELL for {part['part_uid']}: {exc}") from exc
        assignments.append(
            {
                "part_uid": part["part_uid"],
                "pshell_id": int(prop._id),
                "mid": int(part["material_numeric_id"]),
                "thickness": float(part["nominal_thickness"]),
                "target_size": float(part["target_size"]),
            }
        )
    return {"assigned_count": len(assignments), "assignments": assignments}


def _run_recipe_batch_sessions(base, batchmesh, constants, plan: dict, stage_dir: Path) -> dict[str, object]:
    base.SetCurrentMenu("MESH")
    stage_dir.mkdir(parents=True, exist_ok=True)
    ansa_parts = sorted(base.CollectEntities(constants.NASTRAN, None, "ANSAPART", True) or [], key=lambda ent: ent._id)
    pshells = sorted(base.CollectEntities(constants.NASTRAN, None, "PSHELL", True) or [], key=lambda ent: ent._id)
    targets = ansa_parts if ansa_parts else pshells
    session_records = []
    for index, part in enumerate(plan.get("parts", [])):
        if not part.get("batch_mesh", True):
            session_records.append({"part_uid": part["part_uid"], "status": "skipped", "strategy": part["strategy"]})
            continue
        if index >= len(targets):
            raise RuntimeError(f"no ANSA part/property target for recipe part {part['part_uid']}")
        target = targets[index]
        bm_session = batchmesh.GetNewSession()
        parameters = dict(part["mesh_session_keywords"])
        set_status = batchmesh.SetSessionParameters(bm_session, parameters)
        if int(set_status) != 0:
            raise RuntimeError(f"ANSA rejected batch mesh parameters for {part['part_uid']}: {parameters}")
        add_status = batchmesh.AddPartToSession(target, bm_session)
        run_status = batchmesh.RunSession(bm_session)
        if int(run_status) != 1:
            raise RuntimeError(f"ANSA Batch Mesh Manager session did not run for {part['part_uid']}: status={run_status}")
        mpar_path = stage_dir / f"{part['part_uid']}.ansa_mpar"
        qual_path = stage_dir / f"{part['part_uid']}.ansa_qual"
        save_mpar = _call_optional(batchmesh, "SaveSessionMeshParams", bm_session, str(mpar_path))
        save_qual = _call_optional(batchmesh, "SaveSessionQualityCriteria", bm_session, str(qual_path))
        statistics_path = stage_dir / f"{part['part_uid']}.ansa_statistics.html"
        write_statistics = _call_optional(batchmesh, "WriteStatistics", bm_session, str(statistics_path))
        session_records.append(
            {
                "part_uid": part["part_uid"],
                "status": "ran",
                "strategy": part["strategy"],
                "target_size": float(part["target_size"]),
                "target_entity_type": target._ansaType(constants.NASTRAN),
                "target_entity_id": int(target._id),
                "set_parameters_status": int(set_status),
                "add_part_status": _jsonable(add_status),
                "run_session_status": int(run_status),
                "mesh_params_file": str(mpar_path),
                "quality_criteria_file": str(qual_path),
                "statistics_report_file": str(statistics_path),
                "save_mesh_params_status": _jsonable(save_mpar),
                "save_quality_criteria_status": _jsonable(save_qual),
                "write_statistics_status": _jsonable(write_statistics),
            }
        )
    return {
        "mode": plan.get("ansa_session", {}).get("mode"),
        "session_count": sum(1 for item in session_records if item.get("status") != "skipped"),
        "records": session_records,
        "quality_summary": summarize_ansa_quality_statistics(session_records),
    }


def _run_native_solid_tetra_meshing(base, batchmesh, constants, mesh, plan: dict, stage_dir: Path) -> dict[str, object]:
    solid_part_count = sum(1 for part in plan.get("parts", []) if part.get("strategy") in {"solid", "solid_tet"})
    if solid_part_count == 0:
        return {
            "enabled": True,
            "method": "batchmesh_volume_scenario",
            "created_count": 0,
            "expected_solid_part_count": 0,
            "run_status": 0,
        }

    before_counts = _collect_counts(base, constants)
    before_solid_count = int(before_counts.get("SOLID", 0))
    target_size = _solid_target_size(plan)
    scenario_name = f"AI_SOLID_VOLUME_SCENARIO_{plan['sample_id']}"
    session_name = f"AI_TETRA_VOLUME_SESSION_{plan['sample_id']}"
    volume_scenario = batchmesh.GetNewVolumeScenario(
        name=scenario_name,
        auto_detect=True,
        parts="one_part_for_volume",
        include_facets=False,
    )
    if not volume_scenario:
        raise RuntimeError("ANSA failed to create a native volume meshing scenario")
    volume_session = batchmesh.GetNewVolumeSession(session_name)
    if not volume_session:
        raise RuntimeError("ANSA failed to create a native volume meshing session")

    parameter_status = _configure_volume_tetra_session(base, batchmesh, mesh, volume_session, target_size, stage_dir)
    add_session_status = batchmesh.AddSessionToMeshingScenario([volume_session], volume_scenario)
    if int(add_session_status) != 1:
        raise RuntimeError(f"ANSA failed to add volume tetra session to scenario: status={add_session_status}")

    volumes_before = base.CollectEntities(constants.NASTRAN, None, "VOLUME", True) or []
    run_status = batchmesh.RunMeshingScenario(volume_scenario, 60)
    normalized_run_status = int(run_status.get("return", 0)) if isinstance(run_status, dict) else int(run_status)
    if normalized_run_status != 1:
        raise RuntimeError(f"ANSA native volume tetra meshing scenario did not run: status={run_status}")

    volumes_after = base.CollectEntities(constants.NASTRAN, None, "VOLUME", True) or []
    after_counts = _collect_counts(base, constants)
    created_count = int(after_counts.get("SOLID", 0)) - before_solid_count
    statistics_path = stage_dir / "ansa_native_volume_tetra_statistics.html"
    write_statistics = _call_optional(batchmesh, "WriteStatistics", volume_session, str(statistics_path))
    if created_count < solid_part_count:
        raise RuntimeError(
            "ANSA native volume tetra meshing did not create enough solid elements: "
            f"created={created_count}, expected>={solid_part_count}, counts={after_counts}"
        )
    return {
        "enabled": True,
        "method": "batchmesh_volume_scenario",
        "scenario_name": scenario_name,
        "session_name": session_name,
        "expected_solid_part_count": solid_part_count,
        "created_count": created_count,
        "run_status": normalized_run_status,
        "parameter_status": int(parameter_status),
        "add_session_status": int(add_session_status),
        "target_size": float(target_size),
        "volume_count_before": len(volumes_before),
        "volume_count_after": len(volumes_after),
        "counts_before": before_counts,
        "counts_after": after_counts,
        "statistics_report_file": str(statistics_path),
        "write_statistics_status": _jsonable(write_statistics),
    }


def _configure_volume_tetra_session(base, batchmesh, mesh, volume_session, target_size: float, stage_dir: Path) -> int:
    base.BCSettingsSetValues(
        {
            "tetras_algorithm": "Tetra Rapid",
            "tetras_max_elem_length": float(target_size),
            "tetras_max_growth_rate": 1.35,
        }
    )
    mpar_path = stage_dir / "ai_native_volume_tetra.ansa_mpar"
    mesh.SaveMeshParams(str(mpar_path))
    if not mpar_path.exists():
        raise RuntimeError(f"ANSA did not write native volume tetra mesh parameters: {mpar_path}")
    read_status = batchmesh.ReadSessionMeshParams(volume_session, str(mpar_path))
    if int(read_status) != 1:
        raise RuntimeError(f"ANSA rejected native volume tetra mesh parameter file: status={read_status}")
    set_status = batchmesh.SetSessionParameters(
        volume_session,
        {
            "tetras_algorithm": "Tetra Rapid",
            "tetras_max_elem_length": float(target_size),
            "tetras_max_growth_rate": "1.35",
        },
    )
    if int(set_status) != 0:
        raise RuntimeError(f"ANSA rejected native volume tetra session parameters: status={set_status}")
    return 1


def _solid_target_size(plan: dict) -> float:
    sizes = [
        float(part.get("target_size", plan.get("base_size", 8.0)))
        for part in plan.get("parts", [])
        if part.get("strategy") in {"solid", "solid_tet"}
    ]
    return max(0.5, min(sizes) if sizes else float(plan.get("base_size", 8.0)))


def _assign_native_solid_solver_cards(base, constants, plan: dict, solid_tetra_generation: dict[str, object]) -> dict[str, object]:
    expected_solid_count = int(solid_tetra_generation.get("expected_solid_part_count", 0))
    if expected_solid_count <= 0:
        return {
            "enabled": True,
            "assigned_count": 0,
            "created_property_count": 0,
            "expected_solid_part_count": 0,
            "records": [],
        }

    solids = sorted(base.CollectEntities(constants.NASTRAN, None, "SOLID", True) or [], key=lambda ent: ent._id)
    if not solids:
        raise RuntimeError("ANSA native volume meshing reported solids, but no SOLID entities are available for solver card assignment")

    solid_part_plans = [part for part in plan.get("parts", []) if part.get("strategy") in {"solid", "solid_tet"}]
    if not solid_part_plans:
        raise RuntimeError("native SOLID entities exist, but the recipe contains no solid part plans")

    before_samples = _sample_entity_card_values(base, constants, solids, ("EID", "PID", "type"))
    groups: dict[int, list[object]] = {}
    for solid in solids:
        values = _get_entity_card_values(base, constants, solid, ("PID",))
        old_pid = _safe_int(values.get("PID"), 0)
        groups.setdefault(old_pid, []).append(solid)

    property_base = max(
        _max_entity_id(base, constants, "PSOLID") + 1,
        int(plan.get("native_entity_generation", {}).get("id_start", 800000)) + 1000,
    )
    records = []
    assigned_count = 0
    failed_count = 0
    for group_index, old_pid in enumerate(sorted(groups)):
        group_solids = groups[old_pid]
        part = solid_part_plans[group_index % len(solid_part_plans)]
        new_pid = property_base + group_index
        psolid = _create_or_update_psolid(base, constants, new_pid, int(part["material_numeric_id"]), str(part["property_name"]))
        group_failed = 0
        type_counts: dict[str, int] = {}
        for solid in group_solids:
            values = _get_entity_card_values(base, constants, solid, ("type",))
            solid_type = str(values.get("type") or "").upper()
            fields = {"PID": new_pid}
            if not solid_type:
                fields["type"] = "CTETRA"
                solid_type = "CTETRA"
            type_counts[solid_type] = type_counts.get(solid_type, 0) + 1
            try:
                base.SetEntityCardValues(constants.NASTRAN, solid, fields)
                assigned_count += 1
            except Exception:
                group_failed += 1
                failed_count += 1
        records.append(
            {
                "old_property_id": old_pid,
                "new_property_id": int(getattr(psolid, "_id", new_pid)),
                "part_uid": part["part_uid"],
                "material_numeric_id": int(part["material_numeric_id"]),
                "solid_count": len(group_solids),
                "failed_assignment_count": group_failed,
                "solid_type_counts": type_counts,
            }
        )

    after_samples = _sample_entity_card_values(base, constants, solids, ("EID", "PID", "type"))
    if assigned_count < expected_solid_count or failed_count:
        raise RuntimeError(
            "ANSA native SOLID solver card assignment did not cover enough native solids: "
            f"assigned={assigned_count}, failed={failed_count}, expected>={expected_solid_count}"
        )
    return {
        "enabled": True,
        "method": "assign_solver_cards_to_native_volume_solids",
        "assigned_count": assigned_count,
        "failed_assignment_count": failed_count,
        "created_property_count": len(records),
        "expected_solid_part_count": expected_solid_count,
        "solid_entity_count": len(solids),
        "before_samples": before_samples,
        "after_samples": after_samples,
        "records": records,
    }


def _create_or_update_psolid(base, constants, pid: int, mid: int, name: str):
    fields = {
        "PID": int(pid),
        "Name": name,
        "MID": int(mid),
    }
    entity = base.GetEntity(constants.NASTRAN, "PSOLID", int(pid))
    if entity:
        base.SetEntityCardValues(constants.NASTRAN, entity, fields)
        return entity
    entity = base.CreateEntity(constants.NASTRAN, "PSOLID", fields)
    if not entity:
        raise RuntimeError(f"failed to create/update native ANSA PSOLID {pid}")
    return entity


def _create_native_solver_entities(base, constants, plan: dict, solid_tetra_generation: dict[str, object]) -> dict[str, object]:
    next_node_id = max(_max_entity_id(base, constants, "GRID") + 1, int(plan.get("native_entity_generation", {}).get("id_start", 800000)))
    next_element_id = max(
        _max_entity_id(base, constants, "__ELEMENTS__") + 1,
        int(plan.get("native_entity_generation", {}).get("id_start", 800000)),
    )

    connector_pid = int(plan.get("connector_property", {}).get("property_id", 9001))
    pbush = _create_or_update_pbush(base, constants, connector_pid, plan)
    connectors = []
    part_by_uid = {str(part["part_uid"]): part for part in plan.get("parts", [])}
    for connection in plan.get("connections", []):
        endpoint_a = _point(connection["endpoint_a"])
        endpoint_b = _point(connection["endpoint_b"])
        endpoint_a, endpoint_b = _separate_connector_points(endpoint_a, endpoint_b, connection, part_by_uid)
        ga = next_node_id
        next_node_id += 1
        gb = next_node_id
        next_node_id += 1
        _create_grid(base, constants, ga, endpoint_a)
        _create_grid(base, constants, gb, endpoint_b)
        orientation = _connector_orientation(endpoint_a, endpoint_b)
        eid = next_element_id
        next_element_id += 1
        entity = base.CreateEntity(
            constants.NASTRAN,
            "CBUSH",
            {
                "EID": eid,
                "PID": connector_pid,
                "GA": ga,
                "GB": gb,
                "X1": orientation[0],
                "X2": orientation[1],
                "X3": orientation[2],
            },
        )
        if not entity:
            raise RuntimeError(f"failed to create native ANSA CBUSH for {connection['connection_uid']}")
        connectors.append(
            {
                "connection_uid": connection["connection_uid"],
                "element_id": int(getattr(entity, "_id", eid)),
                "property_id": connector_pid,
                "node_ids": [ga, gb],
                "endpoint_a": list(endpoint_a),
                "endpoint_b": list(endpoint_b),
            }
        )

    masses = []
    for part in plan.get("parts", []):
        if part.get("strategy") != "mass_only":
            continue
        center = _point(part["geometry_box"]["center"])
        grid_id = next_node_id
        next_node_id += 1
        _create_grid(base, constants, grid_id, center)
        eid = next_element_id
        next_element_id += 1
        mass = _mass_for_part(part, plan)
        entity = base.CreateEntity(constants.NASTRAN, "CONM2", {"EID": eid, "G": grid_id, "M": mass})
        if not entity:
            raise RuntimeError(f"failed to create native ANSA CONM2 for {part['part_uid']}")
        masses.append(
            {
                "part_uid": part["part_uid"],
                "element_id": int(getattr(entity, "_id", eid)),
                "grid_id": grid_id,
                "mass": mass,
            }
        )

    return {
        "mode": "ansa_native_solver_entities",
        "solid_tetra": solid_tetra_generation,
        "connectors": {
            "property_id": int(getattr(pbush, "_id", connector_pid)) if pbush else connector_pid,
            "created_count": len(connectors),
            "records": connectors,
        },
        "masses": {
            "created_count": len(masses),
            "records": masses,
        },
    }


def _run_quality_repair_loop(base, batchmesh, constants, plan: dict, stage_dir: Path, session_application: dict) -> dict[str, object]:
    records = list(session_application.get("records", []))
    iterations = [
        {
            "iteration": 0,
            "action": "parse_ansa_batchmesh_statistics",
            "summary": summarize_ansa_quality_statistics(records),
        }
    ]
    initial_summary = iterations[0]["summary"]
    if initial_summary.get("passed"):
        return {"status": "passed_no_repair_required", "iteration_count": 1, "records": iterations}

    rerun_records = []
    part_by_uid = {part["part_uid"]: part for part in plan.get("parts", [])}
    for issue in initial_summary.get("issue_records", []):
        part_uid = issue.get("part_uid")
        part = part_by_uid.get(part_uid)
        source_record = next((item for item in records if item.get("part_uid") == part_uid), None)
        if not part or not source_record:
            continue
        target = base.GetEntity(constants.NASTRAN, source_record["target_entity_type"], int(source_record["target_entity_id"]))
        if not target:
            continue
        bm_session = batchmesh.GetNewSession()
        parameters = _repair_mesh_parameters(dict(part["mesh_session_keywords"]))
        set_status = batchmesh.SetSessionParameters(bm_session, parameters)
        add_status = batchmesh.AddPartToSession(target, bm_session)
        run_status = batchmesh.RunSession(bm_session)
        statistics_path = stage_dir / f"{part_uid}.ansa_repair_statistics.html"
        write_statistics = _call_optional(batchmesh, "WriteStatistics", bm_session, str(statistics_path))
        rerun_records.append(
            {
                "part_uid": part_uid,
                "status": "repair_ran",
                "strategy": part["strategy"],
                "target_size": float(part["target_size"]),
                "target_entity_type": source_record["target_entity_type"],
                "target_entity_id": int(source_record["target_entity_id"]),
                "set_parameters_status": int(set_status),
                "add_part_status": _jsonable(add_status),
                "run_session_status": int(run_status),
                "statistics_report_file": str(statistics_path),
                "write_statistics_status": _jsonable(write_statistics),
                "repair_parameters": parameters,
            }
        )
    repair_summary = summarize_ansa_quality_statistics(rerun_records)
    iterations.append(
        {
            "iteration": 1,
            "action": "rerun_batchmesh_with_refined_size_field",
            "summary": repair_summary,
            "records": rerun_records,
        }
    )
    return {
        "status": "passed_after_repair" if repair_summary.get("passed") else "completed_with_reported_quality_issues",
        "iteration_count": len(iterations),
        "records": iterations,
    }


def _max_entity_id(base, constants, entity_type: str) -> int:
    try:
        entities = base.CollectEntities(constants.NASTRAN, None, entity_type, True) or []
    except Exception:
        return 0
    ids = [int(getattr(entity, "_id", 0) or 0) for entity in entities]
    return max(ids or [0])


def _create_or_update_pbush(base, constants, pid: int, plan: dict):
    stiffness = list(plan.get("connector_property", {}).get("stiffness", [100000.0] * 6))
    fields = {
        "PID": int(pid),
        "Name": "AI_NATIVE_CONNECTOR_PBUSH",
        "K1": float(stiffness[0]),
        "K2": float(stiffness[1]),
        "K3": float(stiffness[2]),
        "K4": float(stiffness[3]),
        "K5": float(stiffness[4]),
        "K6": float(stiffness[5]),
    }
    entity = base.GetEntity(constants.NASTRAN, "PBUSH", int(pid))
    if entity:
        base.SetEntityCardValues(constants.NASTRAN, entity, fields)
        return entity
    entity = base.CreateEntity(constants.NASTRAN, "PBUSH", fields)
    if not entity:
        raise RuntimeError(f"failed to create native ANSA PBUSH {pid}")
    return entity


def _create_grid(base, constants, nid: int, coords: tuple[float, float, float]):
    entity = base.CreateEntity(
        constants.NASTRAN,
        "GRID",
        {
            "NID": int(nid),
            "X1": float(coords[0]),
            "X2": float(coords[1]),
            "X3": float(coords[2]),
        },
    )
    if not entity:
        raise RuntimeError(f"failed to create native ANSA GRID {nid}")
    return entity


def _separate_connector_points(
    endpoint_a: tuple[float, float, float],
    endpoint_b: tuple[float, float, float],
    connection: dict,
    part_by_uid: dict[str, dict],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if _distance(endpoint_a, endpoint_b) > 1.0e-6:
        return endpoint_a, endpoint_b
    part_a = part_by_uid.get(str(connection.get("part_uid_a")))
    part_b = part_by_uid.get(str(connection.get("part_uid_b")))
    if part_a and part_b:
        center_a = _point(part_a["geometry_box"]["center"])
        center_b = _point(part_b["geometry_box"]["center"])
        direction = _unit((center_b[0] - center_a[0], center_b[1] - center_a[1], center_b[2] - center_a[2]))
    else:
        direction = (1.0, 0.0, 0.0)
    gap = 0.1
    return (
        (endpoint_a[0] - direction[0] * gap, endpoint_a[1] - direction[1] * gap, endpoint_a[2] - direction[2] * gap),
        (endpoint_b[0] + direction[0] * gap, endpoint_b[1] + direction[1] * gap, endpoint_b[2] + direction[2] * gap),
    )


def _connector_orientation(
    endpoint_a: tuple[float, float, float], endpoint_b: tuple[float, float, float]
) -> tuple[float, float, float]:
    axis = _unit((endpoint_b[0] - endpoint_a[0], endpoint_b[1] - endpoint_a[1], endpoint_b[2] - endpoint_a[2]))
    candidates = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    return min(candidates, key=lambda candidate: abs(_dot(axis, candidate)))


def _repair_mesh_parameters(parameters: dict[str, str]) -> dict[str, str]:
    repaired = dict(parameters)
    if "perimeter_length" in repaired:
        try:
            repaired["perimeter_length"] = f"{max(0.25, float(repaired['perimeter_length']) * 0.85):.8g}"
        except (TypeError, ValueError):
            repaired["perimeter_length"] = "1."
    repaired["distortion-angle"] = "3."
    return repaired


def _mass_for_part(part: dict, plan: dict) -> float:
    dims = _point(part["geometry_box"]["dimensions"])
    scale = float(plan.get("mass_properties", {}).get("density_scale", 1.0e-6))
    minimum = float(plan.get("mass_properties", {}).get("minimum_mass", 0.1))
    return max(minimum, dims[0] * dims[1] * dims[2] * scale)


def _point(values) -> tuple[float, float, float]:
    seq = list(values)
    return (float(seq[0]), float(seq[1]), float(seq[2]))


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = _distance((0.0, 0.0, 0.0), vector)
    if length <= 1.0e-9:
        return (1.0, 0.0, 0.0)
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _call_optional(module, name: str, *args):
    func = getattr(module, name, None)
    if not func:
        return None
    try:
        return func(*args)
    except Exception as exc:
        return {"error": str(exc)}


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool, dict, list)):
        return value
    return str(value)


def _get_entity_card_values(base, constants, entity, fields: tuple[str, ...]) -> dict[str, object]:
    try:
        values = base.GetEntityCardValues(constants.NASTRAN, entity, fields)
    except Exception:
        return {}
    return values if isinstance(values, dict) else {}


def _sample_entity_card_values(base, constants, entities, fields: tuple[str, ...], limit: int = 5) -> list[dict[str, object]]:
    samples = []
    for entity in list(entities)[:limit]:
        values = _get_entity_card_values(base, constants, entity, fields)
        values["_id"] = int(getattr(entity, "_id", 0) or 0)
        samples.append({key: _jsonable(value) for key, value in values.items()})
    return samples


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _card_name(line: str) -> str:
    clean = line.split("$", 1)[0].strip()
    if not clean:
        return ""
    return clean.split(",", 1)[0].split()[0].upper()


def _write_include_cards(bdf_path: Path, solver_dir: Path) -> None:
    grouped = {
        "materials.inc": [],
        "properties.inc": [],
        "connections.inc": [],
        "sets.inc": [],
    }
    for line in bdf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        card = line.split("$", 1)[0].strip()
        if not card:
            continue
        name = card.split(",", 1)[0].split()[0].upper()
        if name == "MAT1":
            grouped["materials.inc"].append(card)
        elif name in {"PSHELL", "PSOLID", "PBUSH"}:
            grouped["properties.inc"].append(card)
        elif name in {"CBUSH", "RBE2", "RBE3", "CONM2"}:
            grouped["connections.inc"].append(card)
        elif name == "SET":
            grouped["sets.inc"].append(card)
    for filename, cards in grouped.items():
        (solver_dir / filename).write_text("\n".join(cards) + ("\n" if cards else ""), encoding="utf-8")
