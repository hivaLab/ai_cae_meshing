from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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

    from ansa import base, batchmesh, constants, session

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
    native_path = native_dir / "model_final.ansa"
    save_status = base.SaveAs(str(native_path))
    output_status = base.OutputNastran(
        filename=str(final_bdf),
        mode="all",
        format="free",
        disregard_includes="on",
        write_comments="off",
    )
    if not final_bdf.exists():
        raise RuntimeError(f"ANSA did not export expected solver deck: {final_bdf}")

    deck_application = apply_solver_deck_recipe(final_bdf, plan)
    _write_include_cards(final_bdf, solver_dir)
    recipe_application = {
        "plan_version": plan.get("plan_version"),
        "recipe_id": plan.get("recipe_id"),
        "summary": plan.get("summary", {}),
        "geometry_healing": geometry_healing,
        "material_application": material_application,
        "property_application": property_application,
        "batch_mesh_sessions": session_application,
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
        "ansa_batch_counts": batch_counts,
        "ansa_save_status": save_status,
        "ansa_output_nastran_status": output_status,
        "ansa_recipe_application": recipe_application,
        "solver_deck_recipe_application": deck_application,
        "expected_solver_deck": str(final_bdf),
        "native_model": str(native_path),
        "fallback_enabled": False,
        "node_count": int(batch_counts.get("GRID", 0)),
        "element_count": int(batch_counts.get("__ELEMENTS__", 0)),
        "shell_count": int(batch_counts.get("SHELL", 0)),
        "solid_count": int(batch_counts.get("SOLID", 0)),
        "connector_count": int(deck_application.get("connector_elements_written", 0))
        + int(batch_counts.get("CBUSH", 0))
        + int(batch_counts.get("RBE2", 0))
        + int(batch_counts.get("RBE3", 0)),
        "mass_count": int(batch_counts.get("CONM2", 0)),
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
                "save_mesh_params_status": _jsonable(save_mpar),
                "save_quality_criteria_status": _jsonable(save_qual),
            }
        )
    return {
        "mode": plan.get("ansa_session", {}).get("mode"),
        "session_count": sum(1 for item in session_records if item.get("status") != "skipped"),
        "records": session_records,
    }


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
