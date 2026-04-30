from __future__ import annotations

from pathlib import Path

from cae_mesh_common.cad.step_io import inspect_step_brep


def reimport_step_metadata(path: Path | str) -> dict[str, object]:
    return inspect_step_brep(Path(path))
