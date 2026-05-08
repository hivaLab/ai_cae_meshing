"""Shared ANSA subprocess command helpers for the active entity pipeline."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Mapping


class AnsaRunnerError(ValueError):
    """Raised when an ANSA command cannot be built or validated safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _path_arg(path: Path) -> str:
    return path.resolve().as_posix()


def _env_mapping(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def resolve_ansa_executable(value: str | None = None, env: Mapping[str, str] | None = None) -> Path:
    """Resolve an ANSA executable from a direct path or an environment variable placeholder."""

    raw = value if value is not None else "${ANSA_EXECUTABLE}"
    raw = raw.strip() if isinstance(raw, str) else ""
    if raw in {"", "${ANSA_EXECUTABLE}", "$ANSA_EXECUTABLE"}:
        raw = _env_mapping(env).get("ANSA_EXECUTABLE", "").strip()
    elif raw.startswith("${") and raw.endswith("}"):
        raw = _env_mapping(env).get(raw[2:-1], "").strip()
    else:
        raw = os.path.expandvars(raw)

    if not raw:
        raise AnsaRunnerError("missing_ansa_executable", "ANSA_EXECUTABLE is not configured")
    return Path(raw)


def encode_ansa_process_payload(payload: Mapping[str, Any]) -> str:
    """Encode a small JSON payload for ANSA ``-process_string`` transport."""

    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def build_ansa_script_command(
    *,
    executable: Path,
    script_path: Path,
    payload: Mapping[str, Any],
    entrypoint: str = "main",
) -> list[str]:
    """Build the ANSA v25 no-GUI Python script invocation used by CDF."""

    return [
        _path_arg(executable),
        "-b",
        "-nogui",
        "--confirm-license-agreement",
        "-exec",
        f"load_script:{_path_arg(script_path)}",
        "-exec",
        entrypoint,
        f"-process_string:{encode_ansa_process_payload(payload)}",
    ]
