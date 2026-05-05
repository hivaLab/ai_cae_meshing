"""AMG diagnostic helpers for real quality-evidence analysis."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AmgQualityCandidateDiagnosticError",
    "QualityCandidateDiagnosticConfig",
    "build_quality_candidate_diagnostics",
    "write_quality_candidate_diagnostics",
    "main",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from ai_mesh_generator.amg.diagnostics import quality_candidates

        return getattr(quality_candidates, name)
    raise AttributeError(name)
