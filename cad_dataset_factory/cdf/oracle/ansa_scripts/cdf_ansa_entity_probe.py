"""ANSA-internal entity descriptor probe for CDF v2.

The probe is diagnostic only. It reports which ANSA entity types expose usable
geometry descriptors for CDF/ANSA identity matching; it does not claim mesh
success.
"""

from __future__ import annotations

import json
import base64
import time
import traceback
from pathlib import Path
from typing import Any


ENTITY_TYPES = ("CONS", "FE PERIMETER", "CURVE", "FACE", "MACRO", "SHELL")
CARD_FIELDS = (
    "ID",
    "__id__",
    "Name",
    "TYPE",
    "Type",
    "Length",
    "LENGTH",
    "Area",
    "AREA",
    "X",
    "Y",
    "Z",
    "X1",
    "Y1",
    "Z1",
    "X2",
    "Y2",
    "Z2",
)


def decode_payload(encoded: str) -> dict[str, Any]:
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("ANSA process payload must be a JSON object")
    return decoded


def payload_from_program_arguments() -> dict[str, Any]:
    from ansa import session  # type: ignore[import-not-found]

    for item in session.ProgramArguments():
        if isinstance(item, str) and item.startswith("-process_string:"):
            return decode_payload(item[len("-process_string:") :])
    raise RuntimeError("ANSA command did not provide -process_string")


def _write_json(path: str | Path, document: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and abs(numeric) != float("inf") else None


def _safe_call(name: str, func: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        value = func(*args, **kwargs)
        return {"name": name, "ok": True, "value": _jsonable(value)}
    except Exception as exc:  # noqa: BLE001 - this probe must survive unknown API calls.
        return {"name": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _jsonable(value: Any, *, depth: int = 0) -> Any:
    if depth > 2:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item, depth=depth + 1) for key, item in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item, depth=depth + 1) for item in list(value)[:50]]
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return {"x": _safe_float(value.x), "y": _safe_float(value.y), "z": _safe_float(value.z)}
    return repr(value)


def _card_values(deck: Any, base: Any, entity: Any) -> dict[str, Any]:
    attempts: dict[str, Any] = {}
    card_fields: list[str] = []
    try:
        raw_fields = entity.card_fields(deck)
        card_fields = [str(item) for item in list(raw_fields or [])]
        attempts["entity.card_fields"] = card_fields[:300]
    except Exception as exc:
        attempts["entity.card_fields_error"] = f"{type(exc).__name__}: {exc}"
    try:
        values = entity.get_entity_values(deck, list(CARD_FIELDS))
        attempts["entity.get_entity_values"] = _jsonable(values)
    except Exception as exc:
        attempts["entity.get_entity_values_error"] = f"{type(exc).__name__}: {exc}"
    if hasattr(base, "GetEntityCardValues"):
        try:
            values = base.GetEntityCardValues(deck, entity, list(CARD_FIELDS))
            attempts["base.GetEntityCardValues"] = _jsonable(values)
        except Exception as exc:
            attempts["base.GetEntityCardValues_error"] = f"{type(exc).__name__}: {exc}"
    if card_fields:
        safe_fields = [field for field in card_fields if field and not field.startswith("_")][:120]
        try:
            attempts["entity.get_all_card_values"] = _jsonable(entity.get_entity_values(deck, safe_fields))
        except Exception as exc:
            attempts["entity.get_all_card_values_error"] = f"{type(exc).__name__}: {exc}"
    return attempts


def _entity_methods(entity: Any) -> list[str]:
    names: list[str] = []
    for name in dir(entity):
        if name.startswith("_"):
            continue
        attr = getattr(entity, name, None)
        if callable(attr):
            names.append(name)
    return sorted(names)[:100]


def _describe_entity(deck: Any, base: Any, entity: Any, entity_type: str, index: int) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    if hasattr(base, "GetCurveLength"):
        calls.append(_safe_call("base.GetCurveLength", base.GetCurveLength, entity))
    if hasattr(base, "GetEntityBoundingBox"):
        calls.append(_safe_call("base.GetEntityBoundingBox", base.GetEntityBoundingBox, entity))
    if hasattr(base, "CalcEntityMiddlePoint"):
        calls.append(_safe_call("base.CalcEntityMiddlePoint", base.CalcEntityMiddlePoint, entity))
    if hasattr(base, "GetEntityArea"):
        calls.append(_safe_call("base.GetEntityArea", base.GetEntityArea, entity))
    related: list[dict[str, Any]] = []
    for related_type in ("FACE", "MACRO", "CONS", "CURVE", "NODE", "SHELL"):
        if hasattr(base, "CollectEntities"):
            try:
                values = base.CollectEntities(deck, entity, related_type)
                related.append({"type": related_type, "count": len(values or []), "values": [_jsonable(item) for item in list(values or [])[:10]]})
            except Exception as exc:
                related.append({"type": related_type, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "entity_type": entity_type,
        "index": index,
        "repr": repr(entity),
        "methods": _entity_methods(entity),
        "card_values": _card_values(deck, base, entity),
        "api_calls": calls,
        "related_entities": related,
    }


def run_entity_probe(payload: dict[str, Any]) -> int:
    started = time.monotonic()
    output_path = str(payload["output_path"])
    report: dict[str, Any] = {
        "schema": "CDF_ANSA_ENTITY_DESCRIPTOR_PROBE_V1",
        "sample_id": payload.get("sample_id"),
        "status": "STARTED",
        "cad_path": payload.get("cad_path"),
        "entity_types": {},
        "runtime_sec": 0.0,
    }
    try:
        from ansa import base, constants, mesh  # type: ignore[import-not-found]

        deck = constants.NASTRAN
        report["ansa_version"] = str(getattr(constants, "version", getattr(constants, "VERSION", "unknown")))
        open_result = base.Open(str(payload["cad_path"]))
        report["step_open_result"] = _jsonable(open_result)
        try:
            faces = base.CollectEntities(deck, None, "FACE")
            if faces:
                try:
                    base.Skin(entities=faces, apply_thickness=True, new_pid=True, offset_type=3, ok_to_offset=True, delete=False)
                except TypeError:
                    base.Skin(True, True, 3, True, 20.0, False, [], 70, False, True)
        except Exception as exc:
            report["skin_error"] = f"{type(exc).__name__}: {exc}"
        report["mesh_api_methods"] = sorted(name for name in dir(mesh) if not name.startswith("_"))[:200]
        report["base_api_methods"] = [
            name
            for name in sorted(dir(base))
            if not name.startswith("_")
            and any(token in name.lower() for token in ("coord", "point", "length", "entity", "cons", "curve", "perimeter", "bound", "area", "center"))
        ][:300]
        for entity_type in ENTITY_TYPES:
            try:
                entities = base.CollectEntities(deck, None, entity_type)
            except Exception as exc:
                report["entity_types"][entity_type] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            report["entity_types"][entity_type] = {
                "count": len(entities or []),
                "entities": [_describe_entity(deck, base, entity, entity_type, index) for index, entity in enumerate(list(entities or [])[:30])],
            }
        report["status"] = "OK"
        return_code = 0
    except Exception as exc:  # noqa: BLE001 - probe must write evidence on failure.
        report.update({"status": "FAILED", "error_code": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
        return_code = 2
    finally:
        report["runtime_sec"] = max(0.0, time.monotonic() - started)
        _write_json(output_path, report)
    return return_code


def main() -> int:
    return run_entity_probe(payload_from_program_arguments())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
