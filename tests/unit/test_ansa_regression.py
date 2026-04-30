from __future__ import annotations

from ai_mesh_generator.validation.ansa_regression import (
    expected_counts,
    extract_sample_result,
    sample_failure_reasons,
    sample_passed,
    summarize_regression,
)


def _summary(native=None, recipe_summary=None, deck=None, quality=None):
    native = native or {"solid_tetra": {"created_count": 2}, "connectors": {"created_count": 3}, "masses": {"created_count": 1}}
    recipe_summary = recipe_summary or {
        "strategy_counts": {"shell": 7, "solid": 2, "mass_only": 1},
        "connection_count": 3,
        "mass_only_part_count": 1,
    }
    deck = deck or {"element_creation_enabled": False}
    quality = quality or {"status": "passed_no_repair_required", "iteration_count": 1}
    return {
        "result_package": "MESH_RESULT.zip",
        "mesh_result": {
            "metrics": {
                "ansa_recipe_summary": recipe_summary,
                "native_entity_generation": native,
                "ansa_quality_repair_loop": quality,
                "bdf_traceability": {
                    "passed": True,
                    "failure_count": 0,
                    "mapped_part_uid_count": 2,
                },
                "ansa_manifest": {
                    "solver_deck_recipe_application": deck,
                    "ansa_recipe_application": {
                        "batch_mesh_sessions": {
                            "session_count": 9,
                            "quality_summary": {
                                "passed": True,
                                "issue_record_count": 0,
                                "status_counts": {"completed_without_errors": 9},
                            },
                        }
                    },
                },
            }
        },
    }


def _validation(passed=True):
    return {
        "passed": passed,
        "bdf_validation": {
            "passed": passed,
            "missing_property_count": 0,
            "missing_material_count": 0,
            "missing_nodes_count": 0,
        },
    }


def test_regression_extracts_and_accepts_native_ansa_metadata():
    result = extract_sample_result("sample_000900", _summary(), _validation(), 12.345, "")

    assert result["accepted"] is True
    assert result["native_ctetra_count"] == 2
    assert result["native_cbush_count"] == 3
    assert result["native_conm2_count"] == 1
    assert result["expected_solid_count"] == 2
    assert result["solver_deck_element_fallback_enabled"] is False
    assert sample_passed(result) is True


def test_regression_rejects_solver_deck_element_fallback():
    result = extract_sample_result("sample_000901", _summary(deck={"element_creation_enabled": True}), _validation(), 1.0, "")

    assert result["accepted"] is False
    assert "solver-deck element fallback was enabled" in sample_failure_reasons(result)


def test_regression_rejects_numeric_quality_threshold_violation():
    quality = {
        "status": "completed_with_reported_quality_issues",
        "iteration_count": 1,
        "records": [
            {
                "summary": {
                    "passed": False,
                    "issue_record_count": 1,
                    "status_counts": {"completed_with_quality_issues": 1},
                    "parsed_reports": [
                        {
                            "numeric_metrics": {"session_part_record_count": 1, "session_unmeshed_total": 2.0},
                            "threshold_violations": [{"metric": "session_unmeshed_total"}],
                        }
                    ],
                }
            }
        ],
    }

    result = extract_sample_result("sample_000902", _summary(quality=quality), _validation(), 1.0, "")

    assert result["accepted"] is False
    assert result["quality_threshold_violation_count"] == 1
    assert "ANSA numeric quality thresholds were violated" in sample_failure_reasons(result)


def test_regression_aggregates_sample_results():
    good = extract_sample_result("sample_000900", _summary(), _validation(), 10.0, "")
    bad = extract_sample_result("sample_000901", _summary(deck={"element_creation_enabled": True}), _validation(), 20.0, "")

    summary = summarize_regression([good, bad])

    assert summary["accepted"] is False
    assert summary["sample_count"] == 2
    assert summary["passed_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["native_ctetra_total"] == 4
    assert summary["total_runtime_seconds"] == 30.0


def test_expected_counts_supports_solid_tet_alias():
    assert expected_counts({"strategy_counts": {"solid_tet": 4}, "connection_count": 2, "mass_only_part_count": 1}) == {
        "solid": 4,
        "connector": 2,
        "mass": 1,
    }
