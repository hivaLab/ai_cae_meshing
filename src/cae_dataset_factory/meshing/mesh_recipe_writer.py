from __future__ import annotations

import json
from pathlib import Path


def write_mesh_recipe(recipe: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True), encoding="utf-8")
    return path
