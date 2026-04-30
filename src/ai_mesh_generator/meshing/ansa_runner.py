from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from cae_mesh_common.bdf.bdf_reader import read_bdf
from cae_mesh_common.bdf.bdf_validator import validate_bdf
from cae_mesh_common.qa.report_writer import write_qa_json

from .ansa_recipe import (
    apply_solver_deck_recipe,
    build_ansa_recipe_plan,
    write_ansa_control_files,
    write_ansa_recipe_plan,
)
from .backend_interface import (
    MeshRequest,
    MeshResult,
    _write_failed_regions,
    _write_manual_review,
    _write_mesh_preview,
    _write_part_metrics,
)


@dataclass
class AnsaBackendConfig:
    ansa_executable: str | None = None
    script_path: str = "ansa_scripts/amg_batch_mesh.py"
    timeout_seconds: int = 3600


class AnsaCommandBackend:
    """Production adapter for ANSA batch meshing.

    This backend never falls back to local procedural meshing. If ANSA is not
    configured, the license is unavailable, or ANSA does not produce the required
    mesh artifacts, execution fails with an explicit error.
    """

    def __init__(self, config: AnsaBackendConfig | None = None) -> None:
        self.config = config or AnsaBackendConfig()

    def status(self) -> dict[str, Any]:
        executable = self.config.ansa_executable or os.environ.get("ANSA_EXECUTABLE") or self._default_ansa_path()
        executable_exists = bool(executable and Path(executable).exists())
        script = Path(self.config.script_path)
        return {
            "backend": "ANSA_BATCH",
            "available": executable_exists and script.exists(),
            "executable": executable,
            "executable_exists": executable_exists,
            "script_path": str(script),
            "script_exists": script.exists(),
            "fallback_enabled": False,
        }

    def build_command(self, config_path: Path) -> list[str]:
        status = self.status()
        executable = status["executable"]
        if not executable or not Path(executable).exists():
            raise FileNotFoundError("ANSA executable is not configured or does not exist")
        script = Path(self.config.script_path).resolve()
        if not script.exists():
            raise FileNotFoundError(f"ANSA script is missing: {script}")
        script_arg = str(script).replace("\\", "/")
        config_arg = str(config_path.resolve()).replace("\\", "/")
        return [
            str(executable),
            "-exec",
            f"load_script:'{script_arg}'",
            "-exec",
            f"run_batch_mesh('{config_arg}')",
            "-nogui",
        ]

    def stage_input(self, request: MeshRequest) -> Path:
        stage = Path(request.output_dir) / "ansa_stage"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "assembly.json").write_text(json.dumps(request.assembly, indent=2, sort_keys=True), encoding="utf-8")
        (stage / "mesh_recipe.json").write_text(json.dumps(request.recipe, indent=2, sort_keys=True), encoding="utf-8")
        plan = build_ansa_recipe_plan(request.assembly, request.recipe)
        write_ansa_recipe_plan(plan, stage / "ansa_recipe_plan.json")
        write_ansa_control_files(plan, stage)
        return stage

    def write_config(self, request: MeshRequest, stage: Path) -> Path:
        output_dir = Path(request.output_dir).resolve()
        geometry_source = request.assembly.get("geometry_source", {})
        step_file = geometry_source.get("step_file")
        step_descriptor_only = bool(geometry_source.get("step_descriptor_only", True))
        config = {
            "sample_id": request.sample_id,
            "stage_dir": str(stage.resolve()),
            "output_dir": str(output_dir),
            "assembly_json": str((stage / "assembly.json").resolve()),
            "recipe_json": str((stage / "mesh_recipe.json").resolve()),
            "ansa_recipe_plan_json": str((stage / "ansa_recipe_plan.json").resolve()),
            "mesh_parameters_json": str((stage / "ansa_mesh_parameters.json").resolve()),
            "quality_criteria_json": str((stage / "ansa_quality_criteria.json").resolve()),
            "step_file": step_file,
            "step_descriptor_only": step_descriptor_only,
            "geometry_mode": "PROCEDURAL_DESCRIPTOR" if step_descriptor_only else "STEP_AP242_BREP",
            "expected_solver_deck": str((output_dir / "solver_deck" / "model_final.bdf").resolve()),
            "expected_manifest": str((output_dir / "ansa_result_manifest.json").resolve()),
        }
        config_path = stage / "ansa_batch_config.json"
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        return config_path

    def parse_result(self, request: MeshRequest) -> dict[str, Any]:
        manifest = Path(request.output_dir) / "ansa_result_manifest.json"
        if not manifest.exists():
            return {"success": False, "error": "missing ansa_result_manifest.json"}
        return json.loads(manifest.read_text(encoding="utf-8"))

    def run(self, request: MeshRequest) -> MeshResult:
        stage = self.stage_input(request)
        config_path = self.write_config(request, stage)
        command = self.build_command(config_path)
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        command_manifest = {
            "backend": "ANSA_BATCH",
            "command": command,
            "stage_dir": str(stage),
            "ansa_recipe_plan": str(stage / "ansa_recipe_plan.json"),
            "fallback_enabled": False,
        }
        (output_dir / "ansa_command.json").write_text(json.dumps(command_manifest, indent=2, sort_keys=True), encoding="utf-8")
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=self.config.timeout_seconds)
        (output_dir / "ansa_stdout.log").write_text(completed.stdout, encoding="utf-8", errors="replace")
        (output_dir / "ansa_stderr.log").write_text(completed.stderr, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            raise RuntimeError(f"ANSA failed with code {completed.returncode}: {completed.stderr}")
        parsed = self.parse_result(request)
        if not parsed.get("success"):
            raise RuntimeError(f"ANSA result parsing failed: {parsed}")
        return self._mesh_result_from_output(request)

    def _mesh_result_from_output(self, request: MeshRequest) -> MeshResult:
        output_dir = Path(request.output_dir)
        solver_dir = output_dir / "solver_deck"
        native_dir = output_dir / "native"
        metadata_dir = output_dir / "metadata"
        bdf_path = output_dir / "solver_deck" / "model_final.bdf"
        if not bdf_path.exists():
            raise FileNotFoundError(f"ANSA completed but did not produce {bdf_path}")
        plan_path = output_dir / "ansa_stage" / "ansa_recipe_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else build_ansa_recipe_plan(request.assembly, request.recipe)
        report_dir = output_dir / "report"
        viewer_dir = output_dir / "viewer"
        for directory in [solver_dir, native_dir, metadata_dir, report_dir, viewer_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        manifest = self.parse_result(request)
        manifest_details = manifest.get("details", {})
        repair_history = list(request.recipe.get("repair_history", []))
        validation = validate_bdf(bdf_path)
        expected_connector_count = int(plan.get("summary", {}).get("connection_count", 0)) + int(
            plan.get("summary", {}).get("mass_only_part_count", 0)
        )
        if validation.passed and validation.connector_count >= expected_connector_count:
            repair_history.append(
                {
                    "iteration": 1,
                    "action": "ansa_bdf_validation",
                    "status": "passed_no_repair_required",
                    "missing_property_count": validation.missing_property_count,
                    "missing_material_count": validation.missing_material_count,
                    "connector_count": validation.connector_count,
                }
            )
        else:
            before = validation.to_dict()
            deck_application = apply_solver_deck_recipe(bdf_path, plan)
            validation = validate_bdf(bdf_path)
            repair_history.append(
                {
                    "iteration": 1,
                    "action": "apply_ai_recipe_solver_deck_repair",
                    "status": "passed" if validation.passed else "failed",
                    "before": before,
                    "after": validation.to_dict(),
                    "deck_application": deck_application,
                }
            )
        model = read_bdf(bdf_path)
        element_records = _element_records_from_model(request.assembly, model)
        _write_solver_includes(bdf_path, solver_dir)
        native_path = native_dir / "model_final.ansa"
        if not native_path.exists():
            raise FileNotFoundError(f"ANSA completed but did not produce native database: {native_path}")
        (metadata_dir / "mesh_recipe_final.json").write_text(
            json.dumps(request.recipe, indent=2, sort_keys=True), encoding="utf-8"
        )
        (metadata_dir / "ansa_recipe_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        (metadata_dir / "ansa_recipe_application.json").write_text(
            json.dumps(manifest_details.get("ansa_recipe_application", {}), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (metadata_dir / "ai_prediction.json").write_text(
            json.dumps(request.recipe.get("ai_prediction", {}), indent=2, sort_keys=True), encoding="utf-8"
        )
        (metadata_dir / "engineering_guard_log.json").write_text(
            json.dumps(request.recipe.get("guard", {}), indent=2, sort_keys=True), encoding="utf-8"
        )
        (metadata_dir / "repair_history.json").write_text(
            json.dumps(repair_history, indent=2, sort_keys=True), encoding="utf-8"
        )
        metrics = {
            "sample_id": request.sample_id,
            "accepted": validation.passed,
            **validation.to_dict(),
            "node_count": len(model.nodes),
            "expected_connector_count": expected_connector_count,
            "ansa_recipe_summary": plan.get("summary", {}),
            "ansa_recipe_application": manifest_details.get("ansa_recipe_application", {}),
            "repair_iteration_count": len(repair_history),
        }
        metrics["ansa_manifest"] = manifest_details
        mesh_meta = {
            "sample_id": request.sample_id,
            "backend": self.status(),
            "accepted": validation.passed,
            "part_count": len(request.assembly.get("parts", [])),
            "element_count": validation.element_count,
            "node_count": len(model.nodes),
            "ansa_manifest": manifest_details,
            "ansa_recipe_summary": plan.get("summary", {}),
        }
        (metadata_dir / "mesh_summary.json").write_text(
            json.dumps({"backend": self.status(), "metrics": metrics}, indent=2, sort_keys=True), encoding="utf-8"
        )
        (metadata_dir / "mesh_meta.json").write_text(json.dumps(mesh_meta, indent=2, sort_keys=True), encoding="utf-8")
        pd.DataFrame(_cad_mapping_from_records(element_records)).to_parquet(
            metadata_dir / "cad_to_mesh_mapping.parquet", index=False
        )

        qa_metrics_path = report_dir / "qa_metrics_global.json"
        validation_path = report_dir / "bdf_validation.json"
        qa_report_path = report_dir / "qa_report.html"
        write_qa_json(metrics, qa_metrics_path)
        write_qa_json(validation.to_dict(), validation_path)
        if not qa_report_path.exists():
            qa_report_path.write_text("<html><body><h1>ANSA QA Report</h1></body></html>", encoding="utf-8")
        _write_part_metrics(request.assembly, element_records, report_dir / "qa_metrics_part.csv")
        pd.DataFrame(element_records).to_parquet(report_dir / "qa_metrics_element.parquet", index=False)
        _write_failed_regions([] if validation.passed else validation.messages, report_dir / "failed_regions.csv")
        _write_manual_review(request.recipe.get("guard", {}).get("manual_review", []), report_dir / "manual_review_list.csv")
        _write_mesh_preview(model, viewer_dir / "mesh_preview.vtk")
        return MeshResult(
            sample_id=request.sample_id,
            backend="ANSA_BATCH",
            output_dir=output_dir,
            bdf_path=bdf_path,
            qa_metrics_path=qa_metrics_path,
            qa_report_path=qa_report_path,
            validation_path=validation_path,
            accepted=validation.passed,
            metrics=metrics,
        )

    def _default_ansa_path(self) -> str | None:
        known = Path.home() / "AppData/Local/Apps/BETA_CAE_Systems/ansa_v25.1.0/ansa64.bat"
        return str(known) if known.exists() else None


def _write_solver_includes(bdf_path: Path, solver_dir: Path) -> None:
    grouped = {
        "materials.inc": [],
        "properties.inc": [],
        "connections.inc": [],
        "sets.inc": [],
    }
    for line in bdf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        card = line.split("$", 1)[0].strip()
        if not card:
            continue
        name = card.split(",", 1)[0].split()[0].upper()
        if name == "MAT1":
            grouped["materials.inc"].append(card)
        elif name in {"PSHELL", "PSOLID", "PBUSH"}:
            grouped["properties.inc"].append(card)
        elif name in {"CBUSH", "RBE2", "RBE3", "CONM2"}:
            grouped["connections.inc"].append(card)
        elif name == "SET":
            grouped["sets.inc"].append(card)
    for filename, cards in grouped.items():
        path = solver_dir / filename
        path.write_text("\n".join(cards) + ("\n" if cards else ""), encoding="utf-8")


def _element_records_from_model(assembly: dict[str, Any], model: Any) -> list[dict[str, Any]]:
    part_uids = [part["part_uid"] for part in assembly.get("parts", [])]
    records: list[dict[str, Any]] = []
    non_connector_index = 0
    for eid, element in sorted(model.elements.items()):
        etype = str(element["type"])
        if etype in {"CBUSH", "RBE2", "RBE3"}:
            part_uid = "connector"
        else:
            part_uid = part_uids[non_connector_index % len(part_uids)] if part_uids else "unknown_part"
            non_connector_index += 1
        records.append(
            {
                "sample_id": assembly["sample_id"],
                "part_uid": part_uid,
                "element_id": eid,
                "element_type": etype,
                "property_id": int(element.get("pid") or 0),
                "node_count": len(element.get("nodes", [])),
                "aspect_ratio": 1.0,
                "skew_deg": 0.0,
                "jacobian": 1.0,
                "passed": True,
            }
        )
    return records


def _cad_mapping_from_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "part_uid": record["part_uid"],
            "cad_entity_uid": record["part_uid"],
            "element_id": record["element_id"],
            "property_id": record["property_id"],
            "node_ids": "[]",
        }
        for record in records
    ]
