"""Placeholder ANSA API adapter layer for the CDF oracle script.

The real ANSA bindings are intentionally deferred. This module is inside
``ansa_scripts`` so future ANSA-only imports remain inside the allowed boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AnsaApiUnavailable(RuntimeError):
    """Raised until the installed ANSA Python API is bound to this layer."""

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"ANSA API operation is unavailable in skeleton mode: {operation}")


@dataclass(frozen=True)
class AnsaModelRef:
    """Opaque placeholder for a future ANSA model reference."""

    handle: Any


def load_ansa_modules() -> Any:
    """Lazily load ANSA modules in real ANSA runtime only."""

    try:
        import ansa  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise AnsaApiUnavailable("load_ansa_modules") from exc
    return ansa


def _unavailable(operation: str) -> None:
    raise AnsaApiUnavailable(operation)


def ansa_import_step(step_path: str) -> AnsaModelRef:
    _unavailable("ansa_import_step")


def ansa_run_geometry_cleanup(model: AnsaModelRef, cleanup_profile: str) -> Any:
    _unavailable("ansa_run_geometry_cleanup")


def ansa_extract_midsurface(model: AnsaModelRef, thickness_mm: float) -> Any:
    _unavailable("ansa_extract_midsurface")


def ansa_match_entities(model: AnsaModelRef, signatures: dict[str, Any], tolerances: dict[str, Any]) -> Any:
    _unavailable("ansa_match_entities")


def ansa_assign_batch_session(model: AnsaModelRef, session_name: str, entity_set: Any) -> None:
    _unavailable("ansa_assign_batch_session")


def ansa_apply_hole_control(feature_ref: Any, control: Any) -> None:
    _unavailable("ansa_apply_hole_control")


def ansa_apply_slot_control(feature_ref: Any, control: Any) -> None:
    _unavailable("ansa_apply_slot_control")


def ansa_apply_cutout_control(feature_ref: Any, control: Any) -> None:
    _unavailable("ansa_apply_cutout_control")


def ansa_apply_bend_control(feature_ref: Any, control: Any) -> None:
    _unavailable("ansa_apply_bend_control")


def ansa_apply_flange_control(feature_ref: Any, control: Any) -> None:
    _unavailable("ansa_apply_flange_control")


def ansa_run_batch_mesh(model: AnsaModelRef, session_name: str) -> Any:
    _unavailable("ansa_run_batch_mesh")


def ansa_run_quality_checks(model: AnsaModelRef, quality_profile: str) -> Any:
    _unavailable("ansa_run_quality_checks")


def ansa_export_solver_deck(model: AnsaModelRef, deck: str, out_path: str) -> None:
    _unavailable("ansa_export_solver_deck")
