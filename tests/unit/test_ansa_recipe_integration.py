from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    assert plan["summary"]["refinement_zone_count"] == len(recipe["refinement_zones"])
    assert plan["summary"]["required_refinement_zone_count"] > 0
    assert plan["summary"]["parts_with_refinement_zones"] > 0
    assert plan["summary"]["connection_count"] == len(assembly["connections"])
    assert plan["materials"]
    assert all("perimeter_length" in part["mesh_session_keywords"] for part in plan["parts"])
    assert any(part["refinement_zone_count"] > 0 and part["target_size"] <= part["part_level_target_size"] for part in plan["parts"])
    assert plan["native_entity_generation"]["solid_tetra"]["entity_type"] == "SOLID"
    assert plan["native_entity_generation"]["solid_tetra"]["element_type"] == "CTETRA"
    assert plan["native_entity_generation"]["solid_tetra"]["method"] == "batchmesh_volume_scenario"
    assert plan["native_entity_generation"]["connector"]["entity_type"] == "CBUSH"
    assert plan["native_entity_generation"]["mass"]["entity_type"] == "CONM2"
    assert {part["material_id"] for part in plan["parts"]} <= {material["material_id"] for material in plan["materials"]}
    assert all("endpoint_a" in connection and "endpoint_b" in connection for connection in plan["connections"])


def test_apply_solver_deck_recipe_writes_only_material_properties_for_native_ansa_flow(tmp_path: Path):
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
    assert stats["connector_elements_written"] == 0
    assert stats["connector_elements_skipped"] == len(plan["connections"])
    assert stats["mass_elements_written"] == 0
    assert "PBUSH" in text
    assert "MAT1" in text
    json.dumps(stats)


def test_solver_deck_recipe_can_disable_element_creation_for_native_ansa_flow(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    recipe = build_oracle_recipe(assembly, build_oracle_labels(assembly))
    plan = build_ansa_recipe_plan(assembly, recipe)
    bdf = tmp_path / "model_final.bdf"
    bdf.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,10.,0.,0.",
                "GRID,3,,0.,10.,0.",
                "GRID,4,,0.,0.,10.",
                "CTETRA,800001,800001,1,2,3,4",
                "PSOLID,800001,1",
                "PBUSH,9001,K,100000.,100000.,100000.",
                "CBUSH,800002,9001,1,2,0.,1.,0.",
                "CONM2,800003,3,0,0.2",
                "ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )

    stats = apply_solver_deck_recipe(bdf, plan, create_missing_elements=False)
    text = bdf.read_text(encoding="utf-8")

    assert stats["element_creation_enabled"] is False
    assert stats["connector_elements_written"] == 0
    assert stats["mass_elements_written"] == 0
    assert stats["connector_property_id"] == 9001
    assert "CTETRA,800001" in text
    assert "CBUSH,800002" in text
    assert "CONM2,800003" in text

    stats_second = apply_solver_deck_recipe(bdf, plan, create_missing_elements=False)
    text_second = bdf.read_text(encoding="utf-8")

    assert stats_second["pshell_cards_seen"] == stats["pshell_cards_seen"]
    assert "CTETRA,800001" in text_second
    assert "CBUSH,800002" in text_second


def test_solver_deck_recipe_removes_native_pbush_orphan_continuations(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    recipe = build_oracle_recipe(assembly, build_oracle_labels(assembly))
    plan = build_ansa_recipe_plan(assembly, recipe)
    bdf = tmp_path / "model_final.bdf"
    bdf.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,10.,0.,0.",
                "GRID,3,,0.,10.,0.",
                "GRID,4,,0.,0.,10.",
                "CTETRA,100,801000,1,2,3,4",
                "PSOLID,801000,1,,,,,SMECH",
                "$AI_NATIVE_CONNECTOR_PBUSH",
                "+A,,B,0.,0.,0.,0.,0.,0.,+B",
                "+B,,GE,0.,0.,0.,0.,0.,0.,+C",
                "+C,,RCV,1.,1.,1.,1.",
                "CBUSH,200,9001,1,2,0.,1.,0.",
                "ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )

    apply_solver_deck_recipe(bdf, plan, create_missing_elements=False)
    text = bdf.read_text(encoding="utf-8")
    validation = validate_bdf(bdf)

    assert validation.passed
    assert "RCV" not in text
    assert "AI_NATIVE_CONNECTOR_PBUSH" not in text
    assert "PBUSH,9001" in text


def test_solver_deck_element_creation_fallback_is_rejected(tmp_path: Path):
    assembly = generate_sample(0, 123, 0.2)
    recipe = build_oracle_recipe(assembly, build_oracle_labels(assembly))
    plan = build_ansa_recipe_plan(assembly, recipe)
    bdf = tmp_path / "model_final.bdf"
    bdf.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,10.,0.,0.",
                "PSHELL,1,,",
                "CQUAD4,1,1,1,2,2,1",
                "ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="solver-deck element creation fallback is disabled"):
        apply_solver_deck_recipe(bdf, plan, create_missing_elements=True)
