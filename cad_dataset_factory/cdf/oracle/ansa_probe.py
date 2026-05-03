"""Runtime probe for installed ANSA batch/script capability."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from cad_dataset_factory.cdf.domain import CdfBaseModel
from cad_dataset_factory.cdf.oracle.ansa_runner import build_ansa_script_command, resolve_ansa_executable

DEFAULT_PROBE_SCRIPT = "cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_probe.py"


class AnsaProbeError(ValueError):
    """Raised when the ANSA probe cannot be launched safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class AnsaProbeResult(CdfBaseModel):
    status: str
    output_path: Path
    command: list[str]
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    report: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_probe_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_ansa_probe(
    *,
    ansa_executable: str | Path,
    out: str | Path,
    timeout_sec: int = 90,
    env: Mapping[str, str] | None = None,
) -> AnsaProbeResult:
    """Launch ANSA in no-GUI mode and ask it to report Python API availability."""

    repo_root = _repo_root()
    output_path = Path(out)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    script_path = repo_root / DEFAULT_PROBE_SCRIPT
    executable = resolve_ansa_executable(str(ansa_executable), env)
    if not executable.exists():
        report = {
            "schema": "CDF_ANSA_RUNTIME_PROBE_SM_V1",
            "status": "FAILED",
            "error_code": "ansa_executable_not_found",
            "ansa_executable": executable.as_posix(),
        }
        _write_probe_report(output_path, report)
        return AnsaProbeResult(status="FAILED", output_path=output_path, command=[], report=report, error_code="ansa_executable_not_found")

    command = build_ansa_script_command(
        executable=executable,
        script_path=script_path,
        payload={"output_path": output_path.as_posix(), "ansa_executable": executable.as_posix()},
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        report = {
            "schema": "CDF_ANSA_RUNTIME_PROBE_SM_V1",
            "status": "TIMEOUT",
            "error_code": "ansa_probe_timeout",
            "ansa_executable": executable.as_posix(),
            "timeout_sec": timeout_sec,
        }
        _write_probe_report(output_path, report)
        return AnsaProbeResult(
            status="TIMEOUT",
            output_path=output_path,
            command=command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else None,
            stderr=exc.stderr if isinstance(exc.stderr, str) else None,
            report=report,
            error_code="ansa_probe_timeout",
        )

    if output_path.is_file():
        report = json.loads(output_path.read_text(encoding="utf-8"))
    else:
        report = {
            "schema": "CDF_ANSA_RUNTIME_PROBE_SM_V1",
            "status": "FAILED",
            "error_code": "ansa_probe_report_missing",
            "ansa_executable": executable.as_posix(),
        }
        _write_probe_report(output_path, report)

    status = "OK" if completed.returncode == 0 and report.get("status") == "OK" else "FAILED"
    return AnsaProbeResult(
        status=status,
        output_path=output_path,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        report=report,
        error_code=None if status == "OK" else str(report.get("error_code", "ansa_probe_failed")),
    )
