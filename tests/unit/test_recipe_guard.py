from __future__ import annotations

from ai_mesh_generator.recipe.guard import apply_recipe_guard


def test_recipe_guard_preserves_boundaries_and_holes():
    prediction = {
        "part_strategies": [{"part_uid": "p0", "strategy": "shell", "confidence": 0.4}],
        "size_fields": [{"part_uid": "p0", "target_size": 5.0, "confidence": 0.4}],
        "connections": [{"connection_uid": "c0", "part_uid_a": "p0", "part_uid_b": "p1", "preserve_hole": True}],
    }
    guarded = apply_recipe_guard(prediction, {"boundary_named_sets": {"fixed": ["p0"]}}, min_confidence=0.55)
    assert guarded["part_strategies"][0]["defeature_allowed"] is False
    assert guarded["connections"][0]["delete_hole_allowed"] is False
    assert guarded["guard"]["manual_review"]


def test_recipe_guard_clamps_tiny_solid_fastener_size_for_ansa_stability():
    prediction = {
        "part_strategies": [{"part_uid": "s0", "strategy": "solid", "confidence": 0.9}],
        "size_fields": [{"part_uid": "s0", "target_size": 2.1, "confidence": 0.9}],
        "connections": [],
    }
    assembly = {"parts": [{"part_uid": "s0", "cad_template": "screw", "strategy": "solid"}], "boundary_named_sets": {}}

    guarded = apply_recipe_guard(prediction, assembly)

    assert guarded["size_fields"][0]["target_size"] == 4.0
    assert guarded["size_fields"][0]["guard_adjustment"] == "minimum_feature_solid_size"
