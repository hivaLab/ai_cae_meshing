"""ANSA-internal runtime probe for CDF real-oracle integration."""

from __future__ import annotations

import base64
import json
import sys
import traceback
from pathlib import Path
from typing import Any


def _decode_payload(encoded: str) -> dict[str, Any]:
    padded = encoded + "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def _payload_from_program_arguments() -> dict[str, Any]:
    try:
        from ansa import session  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return {}
    for item in session.ProgramArguments():
        if isinstance(item, str) and item.startswith("-process_string:"):
            return _decode_payload(item[len("-process_string:") :])
    return {}


def _write(path: str | Path, document: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _module_probe() -> dict[str, Any]:
    import ansa  # type: ignore[import-not-found]
    from ansa import base, batchmesh, constants, mesh, session, utils  # type: ignore[import-not-found]

    modules = {
        "ansa": ansa,
        "base": base,
        "batchmesh": batchmesh,
        "constants": constants,
        "mesh": mesh,
        "session": session,
        "utils": utils,
    }
    required_functions = {
        "base": ["Open", "SaveAs", "CollectEntities", "CheckAndFixGeometry", "Skin", "OutputNastran"],
        "batchmesh": ["GetNewSession", "AddPartToSession", "RunSession", "WriteStatistics"],
        "session": ["ProgramArguments"],
        "mesh": ["ReshapeViolatingShells"],
    }
    return {
        "modules": {name: True for name in modules},
        "functions": {
            module_name: {func: hasattr(modules[module_name], func) for func in function_names}
            for module_name, function_names in required_functions.items()
        },
        "ansa_version": str(getattr(constants, "version", getattr(constants, "VERSION", "unknown"))),
        "app_root_dir": str(getattr(constants, "app_root_dir", "")),
        "program_arguments": [str(item) for item in session.ProgramArguments()],
    }


def main() -> int:
    payload = _payload_from_program_arguments()
    output_path = payload.get("output_path", "ansa_runtime_probe.json")
    try:
        probe = _module_probe()
        document = {
            "schema": "CDF_ANSA_RUNTIME_PROBE_SM_V1",
            "status": "OK",
            "ansa_executable": payload.get("ansa_executable"),
            **probe,
        }
        _write(output_path, document)
        return 0
    except Exception as exc:  # pragma: no cover - exercised only inside ANSA
        document = {
            "schema": "CDF_ANSA_RUNTIME_PROBE_SM_V1",
            "status": "FAILED",
            "error_code": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "ansa_executable": payload.get("ansa_executable"),
        }
        _write(output_path, document)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
