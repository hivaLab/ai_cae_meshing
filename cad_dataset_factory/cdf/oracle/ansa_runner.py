"""Pure Python command runner boundary for CDF ANSA oracle execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import Field

from cad_dataset_factory.cdf.domain import CdfBaseModel

DEFAULT_BATCH_SCRIPT = "cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_oracle.py"


class AnsaRunnerError(ValueError):
    """Raised when an ANSA command cannot be built or validated safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class AnsaRunnerConfig(CdfBaseModel):
    enabled: bool = True
    ansa_executable: str | None = "${ANSA_EXECUTABLE}"
    batch_script: str = DEFAULT_BATCH_SCRIPT
    batch_mesh_session: str = "AMG_SHELL_CONST_THICKNESS_V1"
    quality_profile: str = "AMG_QA_SHELL_V1"
    solver_deck: str = "NASTRAN"
    save_ansa_database: bool = True
    timeout_sec_per_sample: int = Field(default=180, gt=0)


class AnsaRunRequest(CdfBaseModel):
    sample_dir: Path
    config: AnsaRunnerConfig
    repo_root: Path | None = None
    manifest_path: Path | None = None
    execution_report_path: Path | None = None
    quality_report_path: Path | None = None
    env: dict[str, str] | None = None


class AnsaRunResult(CdfBaseModel):
    status: Literal["READY", "SKIPPED", "DRY_RUN", "COMPLETED", "FAILED", "TIMEOUT"]
    command: list[str] = Field(default_factory=list)
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    error_code: str | None = None
    message: str | None = None
    timeout_sec: int | None = None
    paths: dict[str, str] = Field(default_factory=dict)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def _resolve_path(path: Path | str, repo_root: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate


def _request_paths(request: AnsaRunRequest) -> dict[str, Path]:
    repo_root = request.repo_root if request.repo_root is not None else _repo_root()
    sample_dir = _resolve_path(request.sample_dir, repo_root)
    manifest = (
        _resolve_path(request.manifest_path, repo_root)
        if request.manifest_path is not None
        else sample_dir / "labels" / "amg_manifest.json"
    )
    execution_report = (
        _resolve_path(request.execution_report_path, repo_root)
        if request.execution_report_path is not None
        else sample_dir / "reports" / "ansa_execution_report.json"
    )
    quality_report = (
        _resolve_path(request.quality_report_path, repo_root)
        if request.quality_report_path is not None
        else sample_dir / "reports" / "ansa_quality_report.json"
    )
    batch_script = _resolve_path(request.config.batch_script, repo_root)
    return {
        "repo_root": repo_root,
        "sample_dir": sample_dir,
        "manifest": manifest,
        "execution_report": execution_report,
        "quality_report": quality_report,
        "batch_script": batch_script,
    }


def _result_paths(paths: Mapping[str, Path], executable: Path | None = None) -> dict[str, str]:
    result = {key: _path_arg(path) for key, path in paths.items() if key != "repo_root"}
    if executable is not None:
        result["ansa_executable"] = _path_arg(executable)
    return result


def _validate_sample_inputs(paths: Mapping[str, Path]) -> None:
    if not paths["sample_dir"].is_dir():
        raise AnsaRunnerError("missing_sample_dir", f"sample_dir does not exist: {paths['sample_dir']}")
    if not paths["manifest"].is_file():
        raise AnsaRunnerError("missing_manifest", f"manifest does not exist: {paths['manifest']}")


def build_ansa_batch_command(request: AnsaRunRequest) -> list[str]:
    """Build a deterministic ANSA batch command without executing it."""

    paths = _request_paths(request)
    executable = resolve_ansa_executable(request.config.ansa_executable, request.env)
    return [
        _path_arg(executable),
        "-b",
        "-exec",
        _path_arg(paths["batch_script"]),
        "--sample-dir",
        _path_arg(paths["sample_dir"]),
        "--manifest",
        _path_arg(paths["manifest"]),
        "--execution-report",
        _path_arg(paths["execution_report"]),
        "--quality-report",
        _path_arg(paths["quality_report"]),
        "--batch-mesh-session",
        request.config.batch_mesh_session,
        "--quality-profile",
        request.config.quality_profile,
        "--solver-deck",
        request.config.solver_deck,
        "--save-ansa-database",
        "true" if request.config.save_ansa_database else "false",
    ]


def preflight_ansa_run(request: AnsaRunRequest) -> AnsaRunResult:
    """Validate ANSA oracle command inputs without launching ANSA."""

    paths = _request_paths(request)
    if not request.config.enabled:
        return AnsaRunResult(
            status="SKIPPED",
            error_code="ansa_oracle_disabled",
            message="ANSA oracle is disabled in configuration",
            timeout_sec=request.config.timeout_sec_per_sample,
            paths=_result_paths(paths),
        )
    _validate_sample_inputs(paths)

    try:
        executable = resolve_ansa_executable(request.config.ansa_executable, request.env)
    except AnsaRunnerError as exc:
        if exc.code == "missing_ansa_executable":
            return AnsaRunResult(
                status="SKIPPED",
                error_code=exc.code,
                message=str(exc),
                timeout_sec=request.config.timeout_sec_per_sample,
                paths=_result_paths(paths),
            )
        raise

    if not executable.exists():
        return AnsaRunResult(
            status="SKIPPED",
            error_code="ansa_executable_not_found",
            message=f"ANSA executable does not exist: {executable}",
            timeout_sec=request.config.timeout_sec_per_sample,
            paths=_result_paths(paths, executable),
        )

    return AnsaRunResult(
        status="READY",
        command=build_ansa_batch_command(request),
        timeout_sec=request.config.timeout_sec_per_sample,
        paths=_result_paths(paths, executable),
    )


def run_ansa_oracle(request: AnsaRunRequest, execute: bool = False) -> AnsaRunResult:
    """Run or dry-run the ANSA oracle subprocess boundary."""

    preflight = preflight_ansa_run(request)
    if preflight.status != "READY":
        return preflight
    if not execute:
        return preflight.model_copy(update={"status": "DRY_RUN"})

    try:
        completed = subprocess.run(
            preflight.command,
            capture_output=True,
            text=True,
            timeout=request.config.timeout_sec_per_sample,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return preflight.model_copy(
            update={
                "status": "TIMEOUT",
                "error_code": "ansa_timeout",
                "message": f"ANSA command timed out after {request.config.timeout_sec_per_sample} seconds",
                "stdout": exc.stdout if isinstance(exc.stdout, str) else None,
                "stderr": exc.stderr if isinstance(exc.stderr, str) else None,
            }
        )

    return preflight.model_copy(
        update={
            "status": "COMPLETED" if completed.returncode == 0 else "FAILED",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "error_code": None if completed.returncode == 0 else "ansa_process_failed",
        }
    )
