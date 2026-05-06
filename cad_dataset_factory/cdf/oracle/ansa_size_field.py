"""Run the CDF v2 ANSA size-field evaluation boundary."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from cad_dataset_factory.cdf.oracle.ansa_runner import (
    AnsaRunnerError,
    build_ansa_script_command,
    resolve_ansa_executable,
)

DEFAULT_SIZE_FIELD_SCRIPT = "cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_size_field.py"


class AnsaSizeFieldEvaluationError(ValueError):
    """Raised when a size-field ANSA evaluation cannot be launched safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class AnsaSizeFieldEvaluationRequest:
    sample_dir: Path
    size_field_path: Path
    ansa_executable: str
    out_dir: Path
    repo_root: Path | None = None
    execution_report_path: Path | None = None
    quality_report_path: Path | None = None
    entity_quality_path: Path | None = None
    mesh_path: Path | None = None
    diagnostics_path: Path | None = None
    script_path: Path | None = None
    evaluation_id: str = "evaluation_000001"
    timeout_sec: int = 240
    batch_mesh_session: str = "AMG_SHELL_SIZE_FIELD_V2"
    quality_profile: str = "AMG_QA_SHELL_V2"
    solver_deck: str = "NASTRAN"
    env: Mapping[str, str] | None = None


@dataclass(frozen=True)
class AnsaSizeFieldEvaluationResult:
    status: str
    command: list[str]
    returncode: int | None
    output_dir: Path
    execution_report_path: Path
    quality_report_path: Path
    entity_quality_path: Path
    mesh_path: Path
    diagnostics_path: Path
    stdout: str | None = None
    stderr: str | None = None
    error_code: str | None = None
    message: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema(schema_version: str) -> dict[str, Any]:
    return json.loads((_repo_root() / "contracts" / f"{schema_version}.schema.json").read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AnsaSizeFieldEvaluationError("json_read_failed", f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AnsaSizeFieldEvaluationError("json_parse_failed", f"could not parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnsaSizeFieldEvaluationError("json_not_object", f"{path} must contain a JSON object")
    return value


def _validate_json(path: Path, schema_version: str) -> dict[str, Any]:
    document = _read_json(path)
    if document.get("schema_version") != schema_version:
        raise AnsaSizeFieldEvaluationError("schema_version_mismatch", f"{path} must use {schema_version}")
    errors = sorted(Draft202012Validator(_schema(schema_version)).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise AnsaSizeFieldEvaluationError("schema_validation_failed", f"{path} {location}: {first.message}")
    return document


def _resolve(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _resolve_size_field_path(path: Path, sample_dir: Path, repo_root: Path) -> Path:
    if path.is_absolute():
        return path
    sample_relative = sample_dir / path
    if sample_relative.is_file():
        return sample_relative
    return repo_root / path


def _as_posix(path: Path) -> str:
    return path.resolve().as_posix()


def resolve_size_field_paths(request: AnsaSizeFieldEvaluationRequest) -> dict[str, Path]:
    repo_root = request.repo_root or _repo_root()
    sample_dir = _resolve(request.sample_dir, repo_root)
    out_dir = _resolve(request.out_dir, repo_root)
    return {
        "repo_root": repo_root,
        "sample_dir": sample_dir,
        "cad_path": sample_dir / "cad" / "input.step",
        "graph_npz": sample_dir / "graph" / "brep_graph.npz",
        "graph_schema": sample_dir / "graph" / "graph_schema.json",
        "entity_signatures": sample_dir / "graph" / "entity_signatures.json",
        "size_field": _resolve_size_field_path(request.size_field_path, sample_dir, repo_root),
        "out_dir": out_dir,
        "execution_report": request.execution_report_path or out_dir / "reports" / "ansa_execution_report.json",
        "quality_report": request.quality_report_path or out_dir / "reports" / "ansa_quality_report.json",
        "entity_quality": request.entity_quality_path or out_dir / "quality_evaluations" / "evaluation_000001" / "entity_quality_labels.json",
        "mesh_path": request.mesh_path or out_dir / "meshes" / "ansa_size_field_mesh.bdf",
        "diagnostics": request.diagnostics_path or out_dir / "reports" / "ansa_size_field_diagnostics.json",
        "script": request.script_path or repo_root / DEFAULT_SIZE_FIELD_SCRIPT,
    }


def build_size_field_payload(request: AnsaSizeFieldEvaluationRequest) -> dict[str, Any]:
    paths = resolve_size_field_paths(request)
    sample_dir = paths["sample_dir"]
    if not sample_dir.is_dir():
        raise AnsaSizeFieldEvaluationError("missing_sample_dir", f"sample_dir does not exist: {sample_dir}")
    for key in ("cad_path", "graph_npz", "graph_schema", "entity_signatures", "size_field", "script"):
        if not paths[key].is_file():
            raise AnsaSizeFieldEvaluationError(f"missing_{key}", f"required input does not exist: {paths[key]}")
    size_field = _validate_json(paths["size_field"], "AMG_SIZE_FIELD_SM_V2")
    graph_schema = _read_json(paths["graph_schema"])
    if graph_schema.get("schema_version") != "AMG_BREP_ENTITY_GRAPH_SM_V2":
        raise AnsaSizeFieldEvaluationError("graph_schema_invalid", "graph_schema.json must use AMG_BREP_ENTITY_GRAPH_SM_V2")
    sample_id = sample_dir.name
    if size_field.get("sample_id") != sample_id:
        raise AnsaSizeFieldEvaluationError("sample_id_mismatch", f"size field sample_id must match {sample_id}")
    for key in ("execution_report", "quality_report", "entity_quality", "mesh_path", "diagnostics"):
        paths[key].parent.mkdir(parents=True, exist_ok=True)
    return {
        "sample_id": sample_id,
        "evaluation_id": request.evaluation_id,
        "sample_dir": _as_posix(paths["sample_dir"]),
        "cad_path": _as_posix(paths["cad_path"]),
        "graph_npz": _as_posix(paths["graph_npz"]),
        "graph_schema": _as_posix(paths["graph_schema"]),
        "entity_signatures": _as_posix(paths["entity_signatures"]),
        "size_field": _as_posix(paths["size_field"]),
        "execution_report": _as_posix(paths["execution_report"]),
        "quality_report": _as_posix(paths["quality_report"]),
        "entity_quality": _as_posix(paths["entity_quality"]),
        "mesh_path": _as_posix(paths["mesh_path"]),
        "diagnostics": _as_posix(paths["diagnostics"]),
        "batch_mesh_session": request.batch_mesh_session,
        "quality_profile": request.quality_profile,
        "solver_deck": request.solver_deck,
        "timeout_sec": request.timeout_sec,
    }


def build_ansa_size_field_command(request: AnsaSizeFieldEvaluationRequest) -> list[str]:
    paths = resolve_size_field_paths(request)
    executable = resolve_ansa_executable(request.ansa_executable, request.env)
    payload = build_size_field_payload(request)
    return build_ansa_script_command(executable=executable, script_path=paths["script"], payload=payload)


def _classify_outputs(paths: Mapping[str, Path]) -> tuple[str, str | None, str | None]:
    diagnostics: dict[str, Any] = {}
    if paths["diagnostics"].is_file():
        try:
            diagnostics = _read_json(paths["diagnostics"])
        except AnsaSizeFieldEvaluationError:
            diagnostics = {}
    if not paths["execution_report"].is_file():
        return "FAILED", "missing_execution_report", "ANSA did not write an execution report"
    if not paths["quality_report"].is_file():
        return "FAILED", "missing_quality_report", "ANSA did not write a quality report"
    if not paths["entity_quality"].is_file():
        return "FAILED", "missing_entity_quality", "ANSA did not write entity quality labels"
    execution = _read_json(paths["execution_report"])
    quality = _read_json(paths["quality_report"])
    entity_quality = _read_json(paths["entity_quality"])
    rows = entity_quality.get("entity_quality", [])
    metrics_available = isinstance(rows, list) and bool(rows) and all(isinstance(row, dict) and row.get("metric_available") for row in rows)
    hard_fail = any(isinstance(row, dict) and row.get("hard_fail") for row in rows) if isinstance(rows, list) else True
    hard_failed_elements = quality.get("quality", {}).get("num_hard_failed_elements") if isinstance(quality.get("quality"), dict) else None
    mesh_ok = paths["mesh_path"].is_file() and paths["mesh_path"].stat().st_size > 0
    accepted = (
        execution.get("accepted") is True
        and quality.get("accepted") is True
        and hard_failed_elements == 0
        and metrics_available
        and not hard_fail
        and mesh_ok
    )
    if accepted:
        return "COMPLETED", None, None
    code = diagnostics.get("error_code") if isinstance(diagnostics.get("error_code"), str) else None
    status = "BLOCKED" if diagnostics.get("status") == "BLOCKED" or code else "FAILED"
    if code is None:
        if not mesh_ok:
            code = "missing_or_empty_mesh"
        elif not metrics_available:
            code = "entity_quality_metric_unavailable"
        elif hard_failed_elements != 0 or hard_fail:
            code = "mesh_quality_failed"
        else:
            code = "ansa_reports_not_accepted"
    return status, code, f"ANSA size-field output did not satisfy real success criteria: {code}"


def run_ansa_size_field_evaluation(request: AnsaSizeFieldEvaluationRequest, *, execute: bool = True) -> AnsaSizeFieldEvaluationResult:
    paths = resolve_size_field_paths(request)
    try:
        executable = resolve_ansa_executable(request.ansa_executable, request.env)
        if not executable.exists():
            raise AnsaSizeFieldEvaluationError("ansa_executable_not_found", f"ANSA executable does not exist: {executable}")
        command = build_ansa_size_field_command(request)
    except AnsaRunnerError as exc:
        raise AnsaSizeFieldEvaluationError(exc.code, str(exc)) from exc

    if not execute:
        return AnsaSizeFieldEvaluationResult(
            status="DRY_RUN",
            command=command,
            returncode=None,
            output_dir=paths["out_dir"],
            execution_report_path=paths["execution_report"],
            quality_report_path=paths["quality_report"],
            entity_quality_path=paths["entity_quality"],
            mesh_path=paths["mesh_path"],
            diagnostics_path=paths["diagnostics"],
        )
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=request.timeout_sec, check=False)
    except subprocess.TimeoutExpired as exc:
        return AnsaSizeFieldEvaluationResult(
            status="TIMEOUT",
            command=command,
            returncode=None,
            output_dir=paths["out_dir"],
            execution_report_path=paths["execution_report"],
            quality_report_path=paths["quality_report"],
            entity_quality_path=paths["entity_quality"],
            mesh_path=paths["mesh_path"],
            diagnostics_path=paths["diagnostics"],
            stdout=exc.stdout if isinstance(exc.stdout, str) else None,
            stderr=exc.stderr if isinstance(exc.stderr, str) else None,
            error_code="ansa_timeout",
            message=f"ANSA command timed out after {request.timeout_sec} seconds",
        )
    output_status, output_code, output_message = _classify_outputs(paths)
    if completed.returncode not in {0, None} and output_status == "COMPLETED":
        output_status = "FAILED"
        output_code = "ansa_process_failed"
        output_message = "ANSA process returned a non-zero exit code"
    return AnsaSizeFieldEvaluationResult(
        status=output_status,
        command=command,
        returncode=completed.returncode,
        output_dir=paths["out_dir"],
        execution_report_path=paths["execution_report"],
        quality_report_path=paths["quality_report"],
        entity_quality_path=paths["entity_quality"],
        mesh_path=paths["mesh_path"],
        diagnostics_path=paths["diagnostics"],
        stdout=completed.stdout,
        stderr=completed.stderr,
        error_code=output_code,
        message=output_message,
    )
