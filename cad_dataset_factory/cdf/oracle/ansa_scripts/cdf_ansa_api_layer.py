"""ANSA API adapter layer for the CDF oracle script.

All direct ANSA imports stay in this module so normal Python tests can import
the CDF package without requiring an ANSA installation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


class AnsaApiUnavailable(RuntimeError):
    """Raised when an ANSA operation cannot be executed in the current runtime."""

    def __init__(self, operation: str, message: str | None = None) -> None:
        self.operation = operation
        detail = message or "ANSA Python API is unavailable outside ANSA runtime"
        super().__init__(f"{operation}: {detail}")


@dataclass
class AnsaModelRef:
    """Opaque reference to an ANSA model plus runtime state used by the oracle."""

    handle: Any
    modules: Any | None = None
    session: Any | None = None
    reports: dict[str, Any] = field(default_factory=dict)


def load_ansa_modules() -> Any:
    """Lazily load ANSA modules in real ANSA runtime only."""

    try:
        import ansa  # type: ignore[import-not-found]
        from ansa import base, batchmesh, constants, mesh, session, utils  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise AnsaApiUnavailable("load_ansa_modules") from exc
    return SimpleNamespace(
        ansa=ansa,
        base=base,
        batchmesh=batchmesh,
        constants=constants,
        mesh=mesh,
        session=session,
        utils=utils,
    )


def _modules(model: AnsaModelRef | None = None) -> Any:
    if model is not None and model.modules is not None:
        return model.modules
    return load_ansa_modules()


def _require_modules(operation: str, model: AnsaModelRef | None = None) -> Any:
    try:
        return _modules(model)
    except AnsaApiUnavailable as exc:
        raise AnsaApiUnavailable(operation) from exc


def _deck(modules: Any) -> Any:
    return getattr(modules.constants, "NASTRAN")


def _collect(modules: Any, entity_type: str, container: Any = None) -> list[Any]:
    try:
        return list(modules.base.CollectEntities(_deck(modules), container, entity_type) or [])
    except Exception:
        return []


def _count_elements(modules: Any) -> dict[str, int]:
    shells = _collect(modules, "SHELL")
    trias = _collect(modules, "TRIA")
    quads = _collect(modules, "QUAD")
    grids = _collect(modules, "GRID")
    return {
        "num_shell_elements": len(shells) or len(trias) + len(quads),
        "num_trias": len(trias),
        "num_quads": len(quads),
        "num_nodes": len(grids),
    }


def ansa_import_step(step_path: str) -> AnsaModelRef:
    modules = _require_modules("ansa_import_step")
    try:
        modules.session.New("discard")
    except Exception:
        pass
    try:
        modules.base.SetCurrentDeck(_deck(modules))
    except Exception:
        pass
    result = modules.base.Open(step_path)
    if result not in (None, 0):
        raise AnsaApiUnavailable("ansa_import_step", f"base.Open returned {result}")
    faces = _collect(modules, "FACE")
    parts = _collect(modules, "ANSAPART")
    if not faces and not parts:
        raise AnsaApiUnavailable("ansa_import_step", "STEP import produced no ANSA geometry")
    return AnsaModelRef(
        handle={"step_path": step_path, "faces": faces, "parts": parts},
        modules=modules,
        reports={"step_import": {"num_faces": len(faces), "num_parts": len(parts)}},
    )


def ansa_run_geometry_cleanup(model: AnsaModelRef, cleanup_profile: str) -> dict[str, Any]:
    modules = _require_modules("ansa_run_geometry_cleanup", model)
    faces = _collect(modules, "FACE")
    report: dict[str, Any] = {"cleanup_profile": cleanup_profile, "num_faces": len(faces), "remaining_errors": 0}
    if faces:
        try:
            result = modules.base.CheckAndFixGeometry(
                faces,
                ["CRACKS", "TRIPLE CONS", "OVERLAPS", "NEEDLE FACES", "COLLAPSED CONS"],
                [1, 1, 1, 1, 1],
            )
            if isinstance(result, dict):
                report["remaining_errors"] = len(result.get("failed", []))
        except Exception as exc:
            raise AnsaApiUnavailable("ansa_run_geometry_cleanup", str(exc)) from exc
    model.reports["geometry_cleanup"] = report
    return report


def ansa_extract_midsurface(model: AnsaModelRef, thickness_mm: float) -> dict[str, Any]:
    modules = _require_modules("ansa_extract_midsurface", model)
    faces = _collect(modules, "FACE")
    before = len(_collect(modules, "PSHELL"))
    if faces:
        try:
            modules.base.Skin(
                apply_thickness=True,
                new_pid=False,
                offset_type=2,
                ok_to_offset=True,
                max_thickness=max(6.0, float(thickness_mm) * 6.0),
                delete=True,
                entities=faces,
            )
        except Exception as exc:
            raise AnsaApiUnavailable("ansa_extract_midsurface", str(exc)) from exc
    try:
        modules.base.Compress({"Geometry": 1})
    except Exception:
        pass
    shell_properties = _collect(modules, "PSHELL")
    report = {
        "thickness_mm": float(thickness_mm),
        "num_shell_properties_before": before,
        "num_shell_properties": len(shell_properties),
        "success": bool(shell_properties),
    }
    if not report["success"]:
        raise AnsaApiUnavailable("ansa_extract_midsurface", "Skin produced no PSHELL entities")
    model.handle["shell_properties"] = shell_properties
    model.reports["midsurface"] = report
    return report


def ansa_match_entities(model: AnsaModelRef, signatures: dict[str, Any], tolerances: dict[str, Any]) -> dict[str, Any]:
    features = signatures.get("features", []) if isinstance(signatures, dict) else []
    matched = [item.get("feature_id") for item in features if isinstance(item, dict) and item.get("signature")]
    report = {
        "requested_feature_count": len(features),
        "matched_feature_count": len(matched),
        "matched_feature_ids": matched,
        "tolerances": dict(tolerances or {}),
    }
    if len(matched) != len(features):
        raise AnsaApiUnavailable("ansa_match_entities", "not all manifest features include signatures")
    model.reports["entity_matching"] = report
    return report


def ansa_assign_batch_session(model: AnsaModelRef, session_name: str, entity_set: Any) -> dict[str, Any]:
    modules = _require_modules("ansa_assign_batch_session", model)
    try:
        session = modules.batchmesh.GetNewSession("Name", session_name)
    except Exception:
        session = modules.batchmesh.GetNewSession()
    shell_properties = model.handle.get("shell_properties") or _collect(modules, "PSHELL")
    added = 0
    for prop in shell_properties:
        try:
            modules.batchmesh.AddPartToSession(prop, session)
            added += 1
        except Exception:
            continue
    if added == 0:
        for part in _collect(modules, "ANSAPART"):
            try:
                modules.batchmesh.AddPartToSession(part, session)
                added += 1
            except Exception:
                continue
    if added == 0:
        raise AnsaApiUnavailable("ansa_assign_batch_session", "no ANSA parts/properties could be added to batch session")
    model.session = session
    report = {"session_name": session_name, "num_session_parts": added}
    model.reports["batch_session"] = report
    return report


def _record_control(model_or_feature_ref: Any, operation: str, control: Any) -> dict[str, Any]:
    if isinstance(model_or_feature_ref, AnsaModelRef):
        reports = model_or_feature_ref.reports.setdefault("controls", [])
        report = {"operation": operation, "control": control}
        reports.append(report)
        return report
    return {"operation": operation, "control": control}


def _control_mapping(control: Any) -> Mapping[str, Any]:
    return control if isinstance(control, Mapping) else {}


def _feature_mapping(feature: Any) -> Mapping[str, Any]:
    return feature if isinstance(feature, Mapping) else {}


def _first_numeric(control: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[str, float] | None:
    for key in keys:
        value = control.get(key)
        if isinstance(value, (int, float)) and float(value) > 0.0:
            return key, float(value)
    return None


def _first_int(control: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[str, int] | None:
    for key in keys:
        value = control.get(key)
        if isinstance(value, (int, float)) and int(value) > 0:
            return key, int(value)
    return None


def _call_control_api(report: dict[str, Any], module: Any, function_name: str, *args: Any, **kwargs: Any) -> bool:
    function = getattr(module, function_name, None)
    if not callable(function):
        report.setdefault("unavailable_api", []).append(function_name)
        return False
    try:
        result = function(*args, **kwargs)
    except TypeError as exc:
        report.setdefault("failed_api", []).append({"function": function_name, "error": str(exc)})
        return False
    except Exception as exc:
        report.setdefault("failed_api", []).append({"function": function_name, "error": str(exc)})
        return False
    report.setdefault("applied_api", []).append({"function": function_name, "result": _jsonable_api_result(result)})
    return result not in (0, False, None) or function_name in {
        "ApplyNewLengthToMacros",
        "BCSettingsSetValues",
        "FillHoleGeom",
        "SetANSAdefaultsValues",
        "SetSessionParameters",
    }


def _jsonable_api_result(result: Any) -> Any:
    if result is None or isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, (list, tuple)):
        return [_jsonable_api_result(item) for item in result[:10]]
    if isinstance(result, dict):
        return {str(key): _jsonable_api_result(value) for key, value in list(result.items())[:20]}
    if hasattr(result, "_id"):
        return {"entity_id": getattr(result, "_id", None), "entity_type": getattr(result, "_ansa_type", type(result).__name__)}
    if hasattr(result, "meshed_ents"):
        return {"meshed_ents_count": len(getattr(result, "meshed_ents", []) or [])}
    return repr(result)


def _set_global_mesh_length(model: AnsaModelRef, report: dict[str, Any], target_length_mm: float) -> bool:
    modules = _require_modules(str(report["operation"]), model)
    success = False
    if _call_control_api(report, modules.mesh, "SetMeshParamTargetLength", "absolute", float(target_length_mm)):
        success = True
    if _call_control_api(report, modules.mesh, "ApplyNewLengthToMacros", f"{float(target_length_mm):.9g}", 0, False):
        success = True
    defaults = {
        "target_element_length": f"{float(target_length_mm):.9g}",
        "perimeter_length": f"{float(target_length_mm):.9g}",
    }
    if hasattr(modules.base, "BCSettingsSetValues") and _call_control_api(report, modules.base, "BCSettingsSetValues", defaults):
        success = True
    elif _call_control_api(report, modules.base, "SetANSAdefaultsValues", defaults):
        success = True
    if model.session is not None:
        session_fields = {
            "target_element_length": f"{float(target_length_mm):.9g}",
            "perimeter_length": f"{float(target_length_mm):.9g}",
        }
        if _call_control_api(report, modules.batchmesh, "SetSessionParameters", model.session, session_fields):
            success = True
    report["target_length_mm"] = float(target_length_mm)
    return success


def _apply_perimeter_divisions(model: AnsaModelRef, report: dict[str, Any], divisions: int) -> bool:
    modules = _require_modules(str(report["operation"]), model)
    report["perimeter_divisions"] = int(divisions)
    return _call_control_api(report, modules.mesh, "NumberPerimeters", 0, str(int(divisions)), False, False, "edges", False)


def _apply_circular_washer(model: AnsaModelRef, report: dict[str, Any], control: Mapping[str, Any]) -> bool:
    modules = _require_modules(str(report["operation"]), model)
    rings = int(control.get("washer_rings", 1) or 1)
    target = float(control.get("edge_target_length_mm", 1.0) or 1.0)
    growth = float(control.get("radial_growth_rate", control.get("growth_rate", 1.2)) or 1.2)
    report["washer_rings"] = rings
    return _call_control_api(
        report,
        modules.mesh,
        "CreateCircularMesh",
        0,
        True,
        True,
        10.0,
        "o-grid",
        max(1, rings),
        max(1, rings),
        target,
        growth,
        10.0,
    )


def _apply_fill_or_suppression(model: AnsaModelRef, report: dict[str, Any], feature: Mapping[str, Any], control: Mapping[str, Any]) -> bool:
    modules = _require_modules(str(report["operation"]), model)
    feature_diameter = _diameter_from_geometry_signature(feature.get("geometry_signature"))
    scale = float(control.get("suppression_max_diameter_scale", 1.25) or 1.25)
    scale = max(1.01, min(3.0, scale))
    max_diameter = 1.0e9 if feature_diameter is None else max(1.0e-6, scale * feature_diameter)
    report["suppression_feature_diameter_mm"] = feature_diameter
    report["suppression_max_diameter_scale"] = scale
    report["suppression_max_diameter_mm"] = max_diameter
    attempts = (
        ("planar", "expand_existing_faces", 2),
        ("planar", "create_new_faces", 2),
        ("draft", "create_new_faces", 2),
        ("bridge", "create_new_faces", 0),
    )
    for fill_method, geom_fill_method, reshape_zones in attempts:
        report["suppression_fill_method"] = fill_method
        report["suppression_geom_fill_method"] = geom_fill_method
        if _call_control_api(
            report,
            modules.mesh,
            "FillSingleBoundHoles",
            max_diameter,
            False,
            True,
            "pid",
            True,
            reshape_zones,
            None,
            None,
            False,
            fill_method,
            None,
            geom_fill_method,
        ):
            return True
    if hasattr(modules.base, "FillHoleGeom") and _call_control_api(
        report,
        modules.base,
        "FillHoleGeom",
        max_diameter,
        False,
        False,
        True,
        True,
        True,
        0,
        0,
    ):
        report["suppression_geom_api_return_is_uninformative"] = True
        return True
    return False


def _diameter_from_geometry_signature(signature: Any) -> float | None:
    if isinstance(signature, Mapping):
        raw = signature.get("geometry_signature")
    else:
        raw = signature
    if not isinstance(raw, str):
        return None
    values = [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?", raw)]
    if len(values) >= 4:
        return max(values[-2], values[-1])
    return None


def _apply_mesh_control(
    model_or_feature_ref: Any,
    operation: str,
    control: Any,
    *,
    feature: Any = None,
    length_keys: tuple[str, ...] = ("edge_target_length_mm",),
    division_keys: tuple[str, ...] = (),
    washer: bool = False,
    suppress: bool = False,
) -> dict[str, Any]:
    report = _record_control(model_or_feature_ref, operation, control)
    feature_map = _feature_mapping(feature)
    if feature_map:
        report["feature_id"] = feature_map.get("feature_id")
        report["type"] = feature_map.get("type")
        report["action"] = feature_map.get("action")
    if not isinstance(model_or_feature_ref, AnsaModelRef):
        return report

    control_map = _control_mapping(control)
    successes: list[str] = []
    numeric = _first_numeric(control_map, length_keys)
    if numeric is not None and _set_global_mesh_length(model_or_feature_ref, report, numeric[1]):
        report["target_length_key"] = numeric[0]
        successes.append("mesh_length")
    divisions = _first_int(control_map, division_keys)
    if divisions is not None and _apply_perimeter_divisions(model_or_feature_ref, report, divisions[1]):
        report["division_key"] = divisions[0]
        successes.append("perimeter_divisions")
    if washer and _apply_circular_washer(model_or_feature_ref, report, control_map):
        successes.append("washer")
    if suppress and _apply_fill_or_suppression(model_or_feature_ref, report, feature_map, control_map):
        successes.append("suppression")

    report["bound_to_real_ansa_api"] = bool(successes)
    report["successful_control_paths"] = successes
    if not successes:
        raise AnsaApiUnavailable(operation, f"no ANSA mesh-control API accepted control {control_map!r}")
    return report


def ansa_apply_hole_control(feature_ref: Any, control: Any, feature: Any = None) -> dict[str, Any]:
    feature_map = _feature_mapping(feature)
    action = feature_map.get("action")
    control_map = _control_mapping(control)
    return _apply_mesh_control(
        feature_ref,
        "ansa_apply_hole_control",
        control,
        feature=feature,
        length_keys=("edge_target_length_mm",),
        division_keys=("circumferential_divisions",),
        washer=action == "KEEP_WITH_WASHER" or "washer_rings" in control_map,
        suppress=action == "SUPPRESS" or "suppression_rule" in control_map,
    )


def ansa_apply_slot_control(feature_ref: Any, control: Any, feature: Any = None) -> dict[str, Any]:
    feature_map = _feature_mapping(feature)
    return _apply_mesh_control(
        feature_ref,
        "ansa_apply_slot_control",
        control,
        feature=feature,
        length_keys=("edge_target_length_mm",),
        division_keys=("end_arc_divisions", "straight_edge_divisions"),
        suppress=feature_map.get("action") == "SUPPRESS" or "suppression_rule" in _control_mapping(control),
    )


def ansa_apply_cutout_control(feature_ref: Any, control: Any, feature: Any = None) -> dict[str, Any]:
    feature_map = _feature_mapping(feature)
    return _apply_mesh_control(
        feature_ref,
        "ansa_apply_cutout_control",
        control,
        feature=feature,
        length_keys=("edge_target_length_mm",),
        division_keys=(),
        suppress=feature_map.get("action") == "SUPPRESS" or "suppression_rule" in _control_mapping(control),
    )


def ansa_apply_bend_control(feature_ref: Any, control: Any, feature: Any = None) -> dict[str, Any]:
    return _apply_mesh_control(
        feature_ref,
        "ansa_apply_bend_control",
        control,
        feature=feature,
        length_keys=("bend_target_length_mm", "edge_target_length_mm"),
        division_keys=("bend_rows",),
    )


def ansa_apply_flange_control(feature_ref: Any, control: Any, feature: Any = None) -> dict[str, Any]:
    return _apply_mesh_control(
        feature_ref,
        "ansa_apply_flange_control",
        control,
        feature=feature,
        length_keys=("flange_target_length_mm", "free_edge_target_length_mm", "edge_target_length_mm"),
        division_keys=("min_elements_across_width",),
    )


def ansa_run_batch_mesh(model: AnsaModelRef, session_name: str) -> dict[str, Any]:
    modules = _require_modules("ansa_run_batch_mesh", model)
    if model.session is None:
        ansa_assign_batch_session(model, session_name, None)
    try:
        status = modules.batchmesh.RunSession(model.session)
    except Exception as exc:
        raise AnsaApiUnavailable("ansa_run_batch_mesh", str(exc)) from exc
    element_counts = _count_elements(modules)
    report = {"session_name": session_name, "session_status": status, **element_counts}
    if status != 1 or element_counts["num_shell_elements"] <= 0:
        raise AnsaApiUnavailable("ansa_run_batch_mesh", f"RunSession status={status}, shell_elements={element_counts['num_shell_elements']}")
    model.reports["batch_mesh"] = report
    return report


def ansa_run_quality_checks(model: AnsaModelRef, quality_profile: str) -> dict[str, Any]:
    modules = _require_modules("ansa_run_quality_checks", model)
    stats_path = model.handle.get("statistics_report_path")
    statistics_status = None
    if stats_path and model.session is not None:
        try:
            statistics_status = modules.batchmesh.WriteStatistics(model.session, str(stats_path))
        except Exception:
            statistics_status = None
    counts = _count_elements(modules)
    hard_failed = 1 if statistics_status == 1 else 0
    if counts["num_shell_elements"] <= 0:
        hard_failed += 1
    continuous_metrics = _parse_statistics_report(Path(stats_path)) if stats_path else {"quality_metric_unavailable": True}
    report = {
        "quality_profile": quality_profile,
        "statistics_status": statistics_status,
        "num_hard_failed_elements": hard_failed,
        **counts,
        **continuous_metrics,
    }
    model.reports["quality"] = report
    return report


def _cell_texts(html: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell)).strip()
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", html, flags=re.IGNORECASE | re.DOTALL)
    ]


def _float_or_none(value: str) -> float | None:
    cleaned = value.strip().replace("%", "")
    if cleaned in {"", "-"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_statistics_report(path: Path) -> dict[str, Any]:
    try:
        html = path.read_text(encoding="iso-8859-1", errors="ignore")
    except OSError:
        return {"quality_metric_unavailable": True}
    cells = _cell_texts(html)
    session_table = re.search(
        r"<table[^>]*summary=[\"']Session-Parts Report Table[\"'][^>]*>(.*?)</table>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    session_cells = _cell_texts(session_table.group(0)) if session_table is not None else cells
    metrics: dict[str, Any] = {}
    for index, cell in enumerate(session_cells):
        if cell == "TOTAL" and index + 4 < len(session_cells):
            avg_length = _float_or_none(session_cells[index + 1])
            unmeshed = _float_or_none(session_cells[index + 2])
            triangles = _float_or_none(session_cells[index + 3])
            violating = _float_or_none(session_cells[index + 4])
            if avg_length is not None:
                metrics["average_shell_length_mm"] = avg_length
            if unmeshed is not None:
                metrics["unmeshed_shell_count"] = int(unmeshed)
            if triangles is not None:
                metrics["triangles_percent"] = triangles
            if violating is not None:
                metrics["violating_shell_elements_total"] = int(violating)
            break
    for index, cell in enumerate(cells):
        if cell == "MIN" and index + 3 < len(cells):
            value = _float_or_none(cells[index + 3])
            if value is not None:
                metrics["min_shell_side_length_mm"] = value
        if cell == "AVERAGE" and index + 3 < len(cells):
            value = _float_or_none(cells[index + 3])
            if value is not None:
                metrics["average_shell_side_length_mm"] = value
        if cell == "MAX" and index + 3 < len(cells):
            value = _float_or_none(cells[index + 3])
            if value is not None:
                metrics["max_shell_side_length_mm"] = value
    min_side = metrics.get("min_shell_side_length_mm")
    max_side = metrics.get("max_shell_side_length_mm")
    avg_side = metrics.get("average_shell_side_length_mm")
    if isinstance(min_side, (int, float)) and isinstance(max_side, (int, float)) and isinstance(avg_side, (int, float)) and avg_side > 0:
        metrics["side_length_spread_ratio"] = max(0.0, float(max_side - min_side) / float(avg_side))
        metrics["aspect_ratio_proxy_max"] = float(max_side) / max(float(min_side), 1.0e-9)
    if not metrics:
        metrics["quality_metric_unavailable"] = True
    return metrics


def ansa_export_solver_deck(model: AnsaModelRef, deck: str, out_path: str) -> dict[str, Any]:
    modules = _require_modules("ansa_export_solver_deck", model)
    try:
        if deck.upper() == "NASTRAN":
            result = modules.base.OutputNastran(filename=out_path)
        else:
            raise AnsaApiUnavailable("ansa_export_solver_deck", f"unsupported solver deck: {deck}")
    except AnsaApiUnavailable:
        raise
    except Exception as exc:
        raise AnsaApiUnavailable("ansa_export_solver_deck", str(exc)) from exc
    report = {"solver_deck": deck, "path": out_path, "result": result}
    model.reports["solver_export"] = report
    return report


def ansa_save_database(model: AnsaModelRef, out_path: str) -> dict[str, Any]:
    modules = _require_modules("ansa_save_database", model)
    try:
        result = modules.base.SaveAs(out_path)
    except Exception as exc:
        raise AnsaApiUnavailable("ansa_save_database", str(exc)) from exc
    report = {"path": out_path, "result": result}
    model.reports["ansa_database"] = report
    return report
