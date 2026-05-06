"""ANSA oracle subprocess boundary for CDF."""

from cad_dataset_factory.cdf.oracle.ansa_report_parser import (
    AnsaOracleSummary,
    AnsaReportParseError,
    FeatureBoundaryError,
    ParsedAnsaExecutionReport,
    ParsedAnsaQualityReport,
    parse_ansa_execution_report,
    parse_ansa_quality_report,
    summarize_ansa_reports,
)
from cad_dataset_factory.cdf.oracle.ansa_runner import (
    AnsaRunRequest,
    AnsaRunResult,
    AnsaRunnerConfig,
    AnsaRunnerError,
    build_ansa_batch_command,
    preflight_ansa_run,
    resolve_ansa_executable,
    run_ansa_oracle,
)
from cad_dataset_factory.cdf.oracle.ansa_size_field import (
    AnsaSizeFieldEvaluationError,
    AnsaSizeFieldEvaluationRequest,
    AnsaSizeFieldEvaluationResult,
    build_ansa_size_field_command,
    build_size_field_payload,
    run_ansa_size_field_evaluation,
)
from cad_dataset_factory.cdf.oracle.ansa_probe import AnsaProbeError, AnsaProbeResult, run_ansa_probe

__all__ = [
    "AnsaOracleSummary",
    "AnsaProbeError",
    "AnsaProbeResult",
    "AnsaReportParseError",
    "AnsaRunRequest",
    "AnsaRunResult",
    "AnsaRunnerConfig",
    "AnsaRunnerError",
    "AnsaSizeFieldEvaluationError",
    "AnsaSizeFieldEvaluationRequest",
    "AnsaSizeFieldEvaluationResult",
    "FeatureBoundaryError",
    "ParsedAnsaExecutionReport",
    "ParsedAnsaQualityReport",
    "build_ansa_batch_command",
    "build_ansa_size_field_command",
    "build_size_field_payload",
    "parse_ansa_execution_report",
    "parse_ansa_quality_report",
    "preflight_ansa_run",
    "resolve_ansa_executable",
    "run_ansa_oracle",
    "run_ansa_probe",
    "run_ansa_size_field_evaluation",
    "summarize_ansa_reports",
]
