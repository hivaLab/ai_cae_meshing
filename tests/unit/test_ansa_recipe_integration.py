from __future__ import annotations

import json
from pathlib import Path

from ai_mesh_generator.meshing.ansa_recipe import apply_solver_deck_recipe, build_ansa_recipe_plan
from cae_dataset_factory.dataset.sample_writer import build_oracle_labels, build_oracle_recipe
from cae_dataset_factory.workflow.generate_sample import generate_sample
from cae_mesh_common.bdf.bdf_validator import validate_bdf


def test_ansa_recipe_plan_carries_ai_size_material_and_connector_controls():
    assembly = generate_sample(0, 123, 0.2)
    recipe = build_oracle_recipe(assembly, build_oracle_labels(assembly))

    plan = build_ansa_recipe_plan(assembly, recipe)

    assert plan["backend"] == "ANSA_BATCH"
    assert plan["fallback_enabled"] is False
    assert plan["summary"]["part_count"] == len(assembly["parts"])
    assert plan["summary"]["per_part_size_field_count"] == len(recipe["size_fields"])
    assert plan["summary"]["connection_count"] == len(assembly["connections"])
    assert plan["materials"]
    assert all("perimeter_length" in part["mesh_session_keywords"] for part in plan["parts"])
    assert {part["material_id"] for part in plan["parts"]} <= {material["material_id"] for material in plan["materials"]}
    assert all("endpoint_a" in connection and "endpoint_b" in connection for connection in plan["connections"])


def test_apply_solver_deck_recipe_writes_valid_material_property_and_connectors(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    recipe = build_oracle_recipe(assembly, build_oracle_labels(assembly))
    plan = build_ansa_recipe_plan(assembly, recipe)
    bdf = tmp_path / "model_final.bdf"
    bdf.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,250.,0.,0.",
                "GRID,3,,0.,150.,0.",
                "GRID,4,,250.,150.,0.",
                "PSHELL,1,,",
                "CQUAD4,1,1,1,2,4,3",
                "ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )

    stats = apply_solver_deck_recipe(bdf, plan)
    validation = validate_bdf(bdf)
    text = bdf.read_text(encoding="utf-8")

    assert validation.passed
    assert stats["material_cards_written"] == len(plan["materials"])
    assert stats["pshell_cards_updated"] == 1
    assert stats["connector_elements_written"] == len(plan["connections"])
    assert stats["mass_elements_written"] == plan["summary"]["mass_only_part_count"]
    assert "AI_CAE_RECIPE_CONNECTOR" in text
    assert "PBUSH" in text
    assert "MAT1" in text
    json.dumps(stats)
