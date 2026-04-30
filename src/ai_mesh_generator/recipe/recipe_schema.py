from __future__ import annotations

from cae_mesh_common.schema.validators import validate_object


def validate_mesh_recipe(recipe: dict) -> None:
    validate_object(recipe, "mesh_recipe.schema.json")
