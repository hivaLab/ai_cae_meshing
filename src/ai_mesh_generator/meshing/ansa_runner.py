from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend_interface import MeshRequest, MeshResult


@dataclass
class AnsaBackendConfig:
    ansa_executable: str | None = None
    script_path: str = "ansa_scripts/amg_batch_mesh.py"
    timeout_seconds: int = 3600
    dry_run: bool = True


class AnsaCommandBackend:
    """Production adapter for ANSA batch meshing.

    The adapter is safe to use in dry-run mode without an ANSA license. In
    execution mode it stages input artifacts, writes a config JSON, runs ANSA,
    and parses the generated result manifest.
    """

    def __init__(self, config: AnsaBackendConfig | None = None) -> None:
        self.config = config or AnsaBackendConfig()

    def status(self) -> dict[str, Any]:
        executable = self.config.ansa_executable or os.environ.get("ANSA_EXECUTABLE") or self._default_ansa_path()
        return {
            "backend": "ANSA_BATCH",
            "available": bool(executable and Path(executable).exists()),
            "executable": executable,
            "dry_run": self.config.dry_run,
            "script_path": self.config.script_path,
        }

    def build_command(self, config_path: Path) -> list[str]:
        status = self.status()
        executable = status["executable"]
        if not executable:
            raise FileNotFoundError("ANSA executable is not configured")
        script = Path(self.config.script_path).resolve()
        return [
            str(executable),
            "-nogui",
            "-exec",
            f"load_script:{script};run_batch_mesh:{config_path.resolve()}",
        ]

    def stage_input(self, request: MeshRequest) -> Path:
        stage = Path(request.output_dir) / "ansa_stage"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "assembly.json").write_text(json.dumps(request.assembly, indent=2, sort_keys=True), encoding="utf-8")
        (stage / "mesh_recipe.json").write_text(json.dumps(request.recipe, indent=2, sort_keys=True), encoding="utf-8")
        return stage

    def write_config(self, request: MeshRequest, stage: Path) -> Path:
        config = {
            "sample_id": request.sample_id,
            "stage_dir": str(stage),
            "output_dir": str(Path(request.output_dir).resolve()),
            "assembly_json": str((stage / "assembly.json").resolve()),
            "recipe_json": str((stage / "mesh_recipe.json").resolve()),
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
        dry_run_manifest = {
            "backend": "ANSA_BATCH",
            "dry_run": self.config.dry_run,
            "command": command,
            "stage_dir": str(stage),
        }
        (Path(request.output_dir) / "ansa_command.json").write_text(
            json.dumps(dry_run_manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        if self.config.dry_run:
            from .backend_interface import LocalProceduralMeshingBackend

            return LocalProceduralMeshingBackend().run(request)
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=self.config.timeout_seconds)
        if completed.returncode != 0:
            raise RuntimeError(f"ANSA failed with code {completed.returncode}: {completed.stderr}")
        parsed = self.parse_result(request)
        if not parsed.get("success"):
            raise RuntimeError(f"ANSA result parsing failed: {parsed}")
        from .backend_interface import LocalProceduralMeshingBackend

        # The returned paths are normalized by re-validating the output package.
        return LocalProceduralMeshingBackend().run(request)

    def _default_ansa_path(self) -> str | None:
        known = Path.home() / "AppData/Local/Apps/BETA_CAE_Systems/ansa_v25.1.0/ansa64.bat"
        return str(known) if known.exists() else None
