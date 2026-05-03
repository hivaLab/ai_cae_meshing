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

__all__ = [
    "AnsaOracleSummary",
    "AnsaReportParseError",
    "AnsaRunRequest",
    "AnsaRunResult",
    "AnsaRunnerConfig",
    "AnsaRunnerError",
    "FeatureBoundaryError",
    "ParsedAnsaExecutionReport",
    "ParsedAnsaQualityReport",
    "build_ansa_batch_command",
    "parse_ansa_execution_report",
    "parse_ansa_quality_report",
    "preflight_ansa_run",
    "resolve_ansa_executable",
    "run_ansa_oracle",
    "summarize_ansa_reports",
]
