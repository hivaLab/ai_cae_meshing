from __future__ import annotations

from pathlib import Path

from cae_mesh_common.cad.step_io import write_procedural_step


def export_assembly_step(path: Path | str, sample_id: str, parts: list[dict]) -> Path:
    return write_procedural_step(path, sample_id, [part["name"] for part in parts])
