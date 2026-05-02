from __future__ import annotations

from pathlib import Path

from ai_mesh_generator.validation.traceability import validate_bdf_traceability


def _write_traceable_bdf(path: Path, solid_mid: int = 1) -> None:
    path.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,10.,0.,0.",
                "GRID,3,,0.,10.,0.",
                "GRID,4,,0.,0.,10.",
                "GRID,5,,20.,0.,0.",
                "CTETRA,100,801000,1,2,3,4",
                f"PSOLID,801000,{solid_mid}",
                "MAT1,1,210000.,,0.3,7.85-9",
                "PBUSH,9001,K,100000.,100000.,100000.",
                "CBUSH,200,9001,1,5,1.,0.,0.",
                "CONM2,300,5,0,0.2",
                "ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _plan() -> dict:
    return {
        "materials": [{"material_id": "MAT_STEP_GENERIC", "mid": 1}],
        "connections": [{"connection_uid": "step_conn_0001"}],
        "connector_property": {"property_id": 9001},
        "summary": {"mass_only_part_count": 1},
        "parts": [{"part_uid": "step_part_000", "source_product_name": "STEP_PART"}],
    }


def _application() -> dict:
    return {
        "native_entity_generation": {
            "solid_tetra": {
                "solver_card_assignment": {
                    "records": [
                        {
                            "part_uid": "step_part_000",
                            "new_property_id": 801000,
                            "material_numeric_id": 1,
                            "solid_type_counts": {"CTETRA": 1},
                        }
                    ]
                }
            },
            "masses": {
                "records": [
                    {
                        "part_uid": "step_mass_000",
                        "element_id": 300,
                        "grid_id": 5,
                    }
                ]
            },
        }
    }


def test_bdf_traceability_passes_source_part_material_property_mapping(tmp_path: Path):
    bdf = tmp_path / "model.bdf"
    _write_traceable_bdf(bdf)

    result = validate_bdf_traceability(bdf, _plan(), _application())

    assert result["passed"] is True
    assert result["mapped_part_uids"] == ["step_mass_000", "step_part_000"]
    assert result["failure_count"] == 0


def test_bdf_traceability_rejects_wrong_solid_material_mapping(tmp_path: Path):
    bdf = tmp_path / "model.bdf"
    _write_traceable_bdf(bdf, solid_mid=2)

    result = validate_bdf_traceability(bdf, _plan(), _application())

    assert result["passed"] is False
    assert result["failure_count"] >= 1
    assert any(item["kind"] == "solid_property" for item in result["failures"])


def test_bdf_traceability_rejects_silent_cad_part_omission(tmp_path: Path):
    bdf = tmp_path / "model.bdf"
    bdf.write_text(
        "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,10.,0.,0.",
                "GRID,3,,10.,10.,0.",
                "GRID,4,,0.,10.,0.",
                "CQUAD4,10,20,1,2,3,4",
                "PSHELL,20,1,1.2",
                "MAT1,1,210000.,,0.3,7.85-9",
                "ENDDATA",
                "",
            ]
        ),
        encoding="utf-8",
    )
    plan = {
        "materials": [{"material_id": "MAT", "mid": 1}],
        "parts": [
            {"part_uid": "shell_part", "strategy": "shell"},
            {"part_uid": "missing_part", "strategy": "shell"},
        ],
        "connections": [],
        "summary": {"mass_only_part_count": 0},
    }
    application = {
        "property_application": {"assignments": [{"part_uid": "shell_part", "pshell_id": 20, "mid": 1}]}
    }

    result = validate_bdf_traceability(bdf, plan, application)

    assert result["passed"] is False
    assert any(item.get("reason") == "missing_representation_failure" for item in result["failures"])


def test_bdf_traceability_rejects_unapproved_exclude(tmp_path: Path):
    bdf = tmp_path / "model.bdf"
    bdf.write_text("BEGIN BULK\nMAT1,1,210000.,,0.3,7.85-9\nENDDATA\n", encoding="utf-8")
    plan = {
        "materials": [{"material_id": "MAT", "mid": 1}],
        "parts": [{"part_uid": "cosmetic_part", "strategy": "approved_exclude"}],
        "connections": [],
        "summary": {"mass_only_part_count": 0},
    }

    result = validate_bdf_traceability(bdf, plan, {})

    assert result["passed"] is False
    assert any(item.get("reason") == "CAD part is excluded without explicit approval" for item in result["failures"])
