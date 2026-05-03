"""Parse CDF ANSA execution and quality reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

EXECUTION_REPORT_SCHEMA = "CDF_ANSA_EXECUTION_REPORT_SM_V1"
QUALITY_REPORT_SCHEMA = "CDF_ANSA_QUALITY_REPORT_SM_V1"


class AnsaReportParseError(ValueError):
    """Raised when ANSA reports cannot be parsed without guessing."""

    def __init__(self, code: str, message: str, sample_id: str | None = None) -> None:
        self.code = code
        self.sample_id = sample_id
        prefix = code if sample_id is None else f"{code} [{sample_id}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class FeatureBoundaryError:
    feature_id: str
    feature_type: str | None
    boundary_size_error: float
    target_edge_length_mm: float | None = None
    measured_boundary_length_mm: float | None = None


@dataclass(frozen=True)
class ParsedAnsaExecutionReport:
    sample_id: str
    accepted: bool
    step_import_success: bool
    geometry_cleanup_success: bool | None
    midsurface_extraction_success: bool
    feature_matching_success: bool
    batch_mesh_success: bool
    solver_export_success: bool
    runtime_sec: float | None
    outputs: dict[str, Any]
    document: dict[str, Any]
    ansa_version: str | None = None


@dataclass(frozen=True)
class ParsedAnsaQualityReport:
    sample_id: str
    accepted: bool
    mesh_stats: dict[str, Any]
    quality: dict[str, Any]
    feature_checks: list[dict[str, Any]]
    num_hard_failed_elements: int
    feature_boundary_errors: list[FeatureBoundaryError]
    max_boundary_size_error: float | None
    document: dict[str, Any]


@dataclass(frozen=True)
class AnsaOracleSummary:
    sample_id: str
    accepted: bool
    execution_accepted: bool
    quality_accepted: bool
    num_hard_failed_elements: int
    max_boundary_size_error: float | None
    feature_boundary_errors: list[FeatureBoundaryError]
    failed_phases: list[str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_path(schema_name: str) -> Path:
    return _repo_root() / "contracts" / f"{schema_name}.schema.json"


def _load_schema(schema_name: str) -> dict[str, Any]:
    return json.loads(_schema_path(schema_name).read_text(encoding="utf-8"))


def _read_document(value: str | Path | Mapping[str, Any], *, code: str) -> dict[str, Any]:
    if isinstance(value, str | Path):
        try:
            raw = json.loads(Path(value).read_text(encoding="utf-8"))
        except OSError as exc:
            raise AnsaReportParseError("report_read_failed", f"could not read report: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AnsaReportParseError("report_json_invalid", f"could not parse JSON: {exc}") from exc
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise AnsaReportParseError(code, "report must be a path or mapping")

    try:
        normalized = json.loads(json.dumps(raw, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AnsaReportParseError(code, "report must be JSON-compatible") from exc
    if not isinstance(normalized, dict):
        raise AnsaReportParseError(code, "report must be a JSON object")
    return normalized


def _validate_schema(document: dict[str, Any], schema_name: str) -> None:
    validator = Draft202012Validator(_load_schema(schema_name))
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        sample_id = document.get("sample_id") if isinstance(document.get("sample_id"), str) else None
        raise AnsaReportParseError(
            "schema_validation_failed",
            f"{schema_name} {location}: {first.message}",
            sample_id,
        )


def _optional_float(value: Any, *, code: str, sample_id: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise AnsaReportParseError(code, "expected a numeric value", sample_id)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AnsaReportParseError(code, "expected a numeric value", sample_id) from exc


def _required_int_metric(quality: Mapping[str, Any], key: str, sample_id: str) -> int:
    if key not in quality:
        raise AnsaReportParseError("missing_quality_metric", f"quality.{key} is required by the parser", sample_id)
    value = quality[key]
    if isinstance(value, bool):
        raise AnsaReportParseError("malformed_quality_metric", f"quality.{key} must be an integer", sample_id)
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise AnsaReportParseError("malformed_quality_metric", f"quality.{key} must be an integer", sample_id) from exc
    if numeric != value and not (isinstance(value, float) and value.is_integer()):
        raise AnsaReportParseError("malformed_quality_metric", f"quality.{key} must be an integer", sample_id)
    if numeric < 0:
        raise AnsaReportParseError("malformed_quality_metric", f"quality.{key} must be non-negative", sample_id)
    return numeric


def _feature_boundary_errors(feature_checks: list[dict[str, Any]], sample_id: str) -> list[FeatureBoundaryError]:
    errors: list[FeatureBoundaryError] = []
    for index, check in enumerate(feature_checks):
        if "boundary_size_error" not in check:
            continue
        feature_id = check.get("feature_id")
        if not isinstance(feature_id, str) or not feature_id:
            raise AnsaReportParseError("malformed_feature_check", "feature_checks with boundary_size_error require feature_id", sample_id)
        boundary_error = _optional_float(
            check.get("boundary_size_error"),
            code="malformed_feature_check",
            sample_id=sample_id,
        )
        if boundary_error is None:
            raise AnsaReportParseError("malformed_feature_check", "boundary_size_error must be numeric", sample_id)
        feature_type = check.get("type")
        if feature_type is not None and not isinstance(feature_type, str):
            raise AnsaReportParseError("malformed_feature_check", f"feature_checks[{index}].type must be a string", sample_id)
        errors.append(
            FeatureBoundaryError(
                feature_id=feature_id,
                feature_type=feature_type,
                boundary_size_error=boundary_error,
                target_edge_length_mm=_optional_float(
                    check.get("target_edge_length_mm"),
                    code="malformed_feature_check",
                    sample_id=sample_id,
                ),
                measured_boundary_length_mm=_optional_float(
                    check.get("measured_boundary_length_mm"),
                    code="malformed_feature_check",
                    sample_id=sample_id,
                ),
            )
        )
    return errors


def parse_ansa_execution_report(path_or_mapping: str | Path | Mapping[str, Any]) -> ParsedAnsaExecutionReport:
    """Validate and parse a CDF ANSA execution report."""

    document = _read_document(path_or_mapping, code="malformed_execution_report")
    _validate_schema(document, EXECUTION_REPORT_SCHEMA)
    sample_id = document["sample_id"]
    outputs = document.get("outputs", {})
    if not isinstance(outputs, dict):
        raise AnsaReportParseError("malformed_execution_report", "outputs must be an object", sample_id)
    return ParsedAnsaExecutionReport(
        sample_id=sample_id,
        accepted=document["accepted"],
        step_import_success=document["step_import_success"],
        geometry_cleanup_success=document.get("geometry_cleanup_success"),
        midsurface_extraction_success=document["midsurface_extraction_success"],
        feature_matching_success=document["feature_matching_success"],
        batch_mesh_success=document["batch_mesh_success"],
        solver_export_success=document["solver_export_success"],
        runtime_sec=_optional_float(document.get("runtime_sec"), code="malformed_execution_report", sample_id=sample_id),
        outputs=outputs,
        document=document,
        ansa_version=document.get("ansa_version"),
    )


def parse_ansa_quality_report(path_or_mapping: str | Path | Mapping[str, Any]) -> ParsedAnsaQualityReport:
    """Validate and parse a CDF ANSA quality report."""

    document = _read_document(path_or_mapping, code="malformed_quality_report")
    _validate_schema(document, QUALITY_REPORT_SCHEMA)
    sample_id = document["sample_id"]
    quality = document["quality"]
    mesh_stats = document["mesh_stats"]
    feature_checks = document.get("feature_checks", [])
    if not isinstance(quality, dict) or not isinstance(mesh_stats, dict):
        raise AnsaReportParseError("malformed_quality_report", "mesh_stats and quality must be objects", sample_id)
    if not isinstance(feature_checks, list) or not all(isinstance(item, dict) for item in feature_checks):
        raise AnsaReportParseError("malformed_quality_report", "feature_checks must be a list of objects", sample_id)

    num_hard_failed_elements = _required_int_metric(quality, "num_hard_failed_elements", sample_id)
    boundary_errors = _feature_boundary_errors(feature_checks, sample_id)
    max_boundary_error = max((abs(item.boundary_size_error) for item in boundary_errors), default=None)
    return ParsedAnsaQualityReport(
        sample_id=sample_id,
        accepted=document["accepted"],
        mesh_stats=mesh_stats,
        quality=quality,
        feature_checks=feature_checks,
        num_hard_failed_elements=num_hard_failed_elements,
        feature_boundary_errors=boundary_errors,
        max_boundary_size_error=max_boundary_error,
        document=document,
    )


def summarize_ansa_reports(
    execution_report: ParsedAnsaExecutionReport,
    quality_report: ParsedAnsaQualityReport,
) -> AnsaOracleSummary:
    """Combine parsed ANSA reports without recomputing quality acceptance thresholds."""

    if execution_report.sample_id != quality_report.sample_id:
        raise AnsaReportParseError(
            "sample_id_mismatch",
            f"execution sample_id {execution_report.sample_id} does not match quality sample_id {quality_report.sample_id}",
        )

    failed_phases: list[str] = []
    phase_values = {
        "step_import": execution_report.step_import_success,
        "geometry_cleanup": execution_report.geometry_cleanup_success,
        "midsurface_extraction": execution_report.midsurface_extraction_success,
        "feature_matching": execution_report.feature_matching_success,
        "batch_mesh": execution_report.batch_mesh_success,
        "solver_export": execution_report.solver_export_success,
    }
    for phase, value in phase_values.items():
        if value is False:
            failed_phases.append(phase)
    if not quality_report.accepted:
        failed_phases.append("quality_report")

    return AnsaOracleSummary(
        sample_id=execution_report.sample_id,
        accepted=execution_report.accepted and quality_report.accepted,
        execution_accepted=execution_report.accepted,
        quality_accepted=quality_report.accepted,
        num_hard_failed_elements=quality_report.num_hard_failed_elements,
        max_boundary_size_error=quality_report.max_boundary_size_error,
        feature_boundary_errors=quality_report.feature_boundary_errors,
        failed_phases=failed_phases,
    )
