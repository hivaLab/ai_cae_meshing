"""Probe ANSA entity descriptors for CDF v2 identity matching."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from cad_dataset_factory.cdf.oracle.ansa_runner import build_ansa_script_command, resolve_ansa_executable

DEFAULT_ENTITY_PROBE_SCRIPT = "cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_entity_probe.py"


class AnsaEntityProbeError(ValueError):
    """Raised when the ANSA entity probe cannot be launched."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class AnsaEntityProbeRequest:
    sample_dir: Path
    ansa_executable: str
    out: Path
    repo_root: Path | None = None
    timeout_sec: int = 180
    env: Mapping[str, str] | None = None


@dataclass(frozen=True)
class AnsaEntityProbeResult:
    status: str
    output_path: Path
    command: list[str]
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    error_code: str | None = None
    report: dict[str, Any] | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve(path: Path, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def build_ansa_entity_probe_payload(request: AnsaEntityProbeRequest) -> dict[str, Any]:
    root = request.repo_root or _repo_root()
    sample_dir = _resolve(request.sample_dir, root)
    output_path = _resolve(request.out, root)
    cad_path = sample_dir / "cad" / "input.step"
    signatures_path = sample_dir / "graph" / "entity_signatures.json"
    graph_npz = sample_dir / "graph" / "brep_graph.npz"
    for key, path in (("sample_dir", sample_dir), ("cad_path", cad_path), ("entity_signatures", signatures_path), ("graph_npz", graph_npz)):
        exists = path.is_dir() if key == "sample_dir" else path.is_file()
        if not exists:
            raise AnsaEntityProbeError(f"missing_{key}", f"required probe input does not exist: {path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "sample_id": sample_dir.name,
        "sample_dir": sample_dir.resolve().as_posix(),
        "cad_path": cad_path.resolve().as_posix(),
        "entity_signatures": signatures_path.resolve().as_posix(),
        "graph_npz": graph_npz.resolve().as_posix(),
        "output_path": output_path.resolve().as_posix(),
    }


def build_ansa_entity_probe_command(request: AnsaEntityProbeRequest) -> list[str]:
    root = request.repo_root or _repo_root()
    executable = resolve_ansa_executable(request.ansa_executable, request.env)
    script_path = root / DEFAULT_ENTITY_PROBE_SCRIPT
    if not script_path.is_file():
        raise AnsaEntityProbeError("missing_probe_script", f"probe script does not exist: {script_path}")
    payload = build_ansa_entity_probe_payload(request)
    return build_ansa_script_command(executable=executable, script_path=script_path, payload=payload)


def run_ansa_entity_probe(request: AnsaEntityProbeRequest) -> AnsaEntityProbeResult:
    root = request.repo_root or _repo_root()
    output_path = _resolve(request.out, root)
    executable = resolve_ansa_executable(request.ansa_executable, request.env)
    if not executable.exists():
        report = {
            "schema": "CDF_ANSA_ENTITY_DESCRIPTOR_PROBE_V1",
            "status": "FAILED",
            "error_code": "ansa_executable_not_found",
            "ansa_executable": executable.as_posix(),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return AnsaEntityProbeResult("FAILED", output_path, [], error_code="ansa_executable_not_found", report=report)
    command = build_ansa_entity_probe_command(request)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=request.timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        report = {
            "schema": "CDF_ANSA_ENTITY_DESCRIPTOR_PROBE_V1",
            "status": "TIMEOUT",
            "error_code": "ansa_entity_probe_timeout",
            "timeout_sec": request.timeout_sec,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return AnsaEntityProbeResult(
            "TIMEOUT",
            output_path,
            command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else None,
            stderr=exc.stderr if isinstance(exc.stderr, str) else None,
            error_code="ansa_entity_probe_timeout",
            report=report,
        )
    report: dict[str, Any] | None = None
    error_code = None
    if output_path.is_file():
        try:
            loaded = json.loads(output_path.read_text(encoding="utf-8"))
            report = loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            error_code = "probe_report_parse_failed"
    else:
        error_code = "probe_report_missing"
    status = "OK" if completed.returncode == 0 and report and report.get("status") == "OK" else "FAILED"
    if status != "OK" and error_code is None and report is not None:
        error_code = str(report.get("error_code", "ansa_entity_probe_failed"))
    return AnsaEntityProbeResult(
        status=status,
        output_path=output_path,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        error_code=error_code,
        report=report,
    )
