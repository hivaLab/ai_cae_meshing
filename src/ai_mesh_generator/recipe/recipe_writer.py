from __future__ import annotations

import json
from pathlib import Path


def build_mesh_recipe(sample_id: str, prediction: dict, guarded: dict, backend: str = "ANSA_BATCH") -> dict:
    return {
        "recipe_id": f"amg_recipe_{sample_id}",
        "sample_id": sample_id,
        "backend": backend,
        "base_size": prediction["base_size"],
        "part_strategies": guarded["part_strategies"],
        "size_fields": guarded["size_fields"],
        "connections": guarded["connections"],
        "guard": guarded["guard"],
        "ai_prediction": prediction,
        "repair_history": [
            {
                "iteration": 0,
                "action": "initial_ai_recipe_guarded",
                "status": "accepted_for_meshing",
            }
        ],
    }


def write_recipe(recipe: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True), encoding="utf-8")
    return path
