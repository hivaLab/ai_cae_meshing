"""ANSA API adapter layer for the CDF oracle script.

All direct ANSA imports stay in this module so normal Python tests can import
the CDF package without requiring an ANSA installation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any


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


def ansa_apply_hole_control(feature_ref: Any, control: Any) -> dict[str, Any]:
    return _record_control(feature_ref, "ansa_apply_hole_control", control)


def ansa_apply_slot_control(feature_ref: Any, control: Any) -> dict[str, Any]:
    return _record_control(feature_ref, "ansa_apply_slot_control", control)


def ansa_apply_cutout_control(feature_ref: Any, control: Any) -> dict[str, Any]:
    return _record_control(feature_ref, "ansa_apply_cutout_control", control)


def ansa_apply_bend_control(feature_ref: Any, control: Any) -> dict[str, Any]:
    return _record_control(feature_ref, "ansa_apply_bend_control", control)


def ansa_apply_flange_control(feature_ref: Any, control: Any) -> dict[str, Any]:
    return _record_control(feature_ref, "ansa_apply_flange_control", control)


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
    metrics: dict[str, Any] = {}
    for index, cell in enumerate(cells):
        if cell == "TOTAL" and index + 4 < len(cells):
            avg_length = _float_or_none(cells[index + 1])
            unmeshed = _float_or_none(cells[index + 2])
            triangles = _float_or_none(cells[index + 3])
            violating = _float_or_none(cells[index + 4])
            if avg_length is not None:
                metrics["average_shell_length_mm"] = avg_length
            if unmeshed is not None:
                metrics["unmeshed_shell_count"] = int(unmeshed)
            if triangles is not None:
                metrics["triangles_percent"] = triangles
            if violating is not None:
                metrics["violating_shell_elements_total"] = int(violating)
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
