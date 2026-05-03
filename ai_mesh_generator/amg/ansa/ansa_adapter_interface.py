"""AMG-side ANSA adapter interface and deterministic mock implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class AnsaAdapterError(RuntimeError):
    """Raised when an ANSA adapter operation fails."""

    def __init__(self, code: str, message: str, operation: str | None = None) -> None:
        self.code = code
        self.operation = operation
        prefix = code if operation is None else f"{code} [{operation}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class AdapterOperation:
    """A deterministic description of one adapter call."""

    name: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


class AnsaAdapter(Protocol):
    """Stable AMG adapter boundary for ANSA implementations."""

    def import_step(self, path: str) -> None: ...
    def run_geometry_cleanup(self) -> None: ...
    def build_entity_index(self) -> dict[str, Any]: ...
    def match_entities(self, manifest: dict[str, Any]) -> dict[str, Any]: ...
    def create_sets(self, entity_map: dict[str, Any]) -> None: ...
    def extract_midsurface(self, part_spec: dict[str, Any]) -> None: ...
    def assign_thickness(self, thickness_mm: float) -> None: ...
    def assign_batch_session(self, session_name: str) -> None: ...
    def apply_edge_length(self, edge_set: str, h_mm: float) -> None: ...
    def apply_hole_washer(self, feature_set: str, controls: dict[str, Any]) -> None: ...
    def fill_hole(self, feature_set: str) -> None: ...
    def apply_bend_rows(self, feature_set: str, controls: dict[str, Any]) -> None: ...
    def apply_flange_size(self, feature_set: str, controls: dict[str, Any]) -> None: ...
    def run_batch_mesh(self, quality_template: str) -> None: ...
    def export_quality_report(self, path: str) -> None: ...
    def export_solver_deck(self, solver: str, path: str) -> None: ...


class MockAnsaAdapter:
    """Deterministic test adapter that records operations and writes placeholder outputs."""

    def __init__(
        self,
        *,
        fail_on_operation: str | None = None,
        quality_outcomes: tuple[bool, ...] = (True,),
        retry_cases: tuple[str, ...] = ("global_growth_fail",),
        sample_id: str = "amg_mock_sample",
    ) -> None:
        self.fail_on_operation = fail_on_operation
        self.quality_outcomes = quality_outcomes or (True,)
        self.retry_cases = retry_cases or ("global_growth_fail",)
        self.sample_id = sample_id
        self.operation_log: list[AdapterOperation] = []
        self._quality_index = 0

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.operation_log.append(AdapterOperation(name=name, args=tuple(args), kwargs=dict(kwargs)))
        if name == self.fail_on_operation:
            raise AnsaAdapterError("mock_operation_failed", "configured mock failure", name)

    def import_step(self, path: str) -> None:
        self._record("import_step", path)

    def run_geometry_cleanup(self) -> None:
        self._record("run_geometry_cleanup")

    def build_entity_index(self) -> dict[str, Any]:
        self._record("build_entity_index")
        return {"features": {}}

    def match_entities(self, manifest: dict[str, Any]) -> dict[str, Any]:
        self._record("match_entities")
        return {
            "features": {
                feature["feature_id"]: f"FEATURE_SET_{feature['feature_id']}"
                for feature in manifest.get("features", [])
            }
        }

    def create_sets(self, entity_map: dict[str, Any]) -> None:
        self._record("create_sets", entity_map)

    def extract_midsurface(self, part_spec: dict[str, Any]) -> None:
        self._record("extract_midsurface", part_spec)

    def assign_thickness(self, thickness_mm: float) -> None:
        self._record("assign_thickness", thickness_mm)

    def assign_batch_session(self, session_name: str) -> None:
        self._record("assign_batch_session", session_name)

    def apply_edge_length(self, edge_set: str, h_mm: float) -> None:
        self._record("apply_edge_length", edge_set, h_mm)

    def apply_hole_washer(self, feature_set: str, controls: dict[str, Any]) -> None:
        self._record("apply_hole_washer", feature_set, controls)

    def fill_hole(self, feature_set: str) -> None:
        self._record("fill_hole", feature_set)

    def apply_bend_rows(self, feature_set: str, controls: dict[str, Any]) -> None:
        self._record("apply_bend_rows", feature_set, controls)

    def apply_flange_size(self, feature_set: str, controls: dict[str, Any]) -> None:
        self._record("apply_flange_size", feature_set, controls)

    def run_batch_mesh(self, quality_template: str) -> None:
        self._record("run_batch_mesh", quality_template)

    def export_quality_report(self, path: str) -> None:
        self._record("export_quality_report", path)
        accepted = self.quality_outcomes[min(self._quality_index, len(self.quality_outcomes) - 1)]
        retry_case = self.retry_cases[min(self._quality_index, len(self.retry_cases) - 1)]
        self._quality_index += 1
        report = {
            "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
            "sample_id": self.sample_id,
            "accepted": bool(accepted),
            "mesh_stats": {"num_nodes": 0, "num_elements": 0},
            "quality": {
                "num_hard_failed_elements": 0 if accepted else 1,
                "retry_case": retry_case,
            },
            "feature_checks": [],
        }
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def export_solver_deck(self, solver: str, path: str) -> None:
        self._record("export_solver_deck", solver, path)
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"mock solver deck: {solver}\n", encoding="utf-8")
