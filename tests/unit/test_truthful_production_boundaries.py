from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ai_mesh_generator.cad.healer import heal_geometry
from ai_mesh_generator.input.training_submission import validate_training_submission_dir
from ai_mesh_generator.output.result_packager import validate_result_package


def test_heal_geometry_does_not_fake_pass():
    healed = heal_geometry({"sample_id": "s0"})

    assert healed["healing"]["status"] == "not_performed"
    assert healed["healing"]["requires_manual_review"] is True
    assert healed["healing"]["operations"] == []


def test_result_package_rejects_placeholder_qa_report(tmp_path: Path):
    result_zip = tmp_path / "result.zip"
    required_text_files = {
        "solver_deck/model_final.bdf": "\n".join(
            [
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,1.,0.,0.",
                "GRID,3,,1.,1.,0.",
                "GRID,4,,0.,1.,0.",
                "CQUAD4,1,1,1,2,3,4",
                "PSHELL,1,1,1.0",
                "MAT1,1,210000.,,0.3,7.85-9",
                "ENDDATA",
                "",
            ]
        ),
        "solver_deck/materials.inc": "MAT1,1,210000.,,0.3,7.85-9\n",
        "solver_deck/properties.inc": "PSHELL,1,1,1.0\n",
        "solver_deck/connections.inc": "",
        "solver_deck/sets.inc": "",
        "native/model_final.ansa": "{}",
        "metadata/mesh_recipe_final.json": "{}",
        "metadata/ai_prediction.json": "{}",
        "metadata/engineering_guard_log.json": "{}",
        "metadata/repair_history.json": "[]",
        "metadata/mesh_meta.json": "{}",
        "metadata/cad_to_mesh_mapping.parquet": "not-read-by-validator",
        "report/qa_report.html": "<html><body><h1>ANSA QA Report</h1></body></html>",
        "report/qa_metrics_global.json": json.dumps({"accepted": True}),
        "report/qa_metrics_part.csv": "",
        "report/qa_metrics_element.parquet": "not-read-by-validator",
        "report/failed_regions.csv": "",
        "report/manual_review_list.csv": "",
        "report/bdf_validation.json": "{}",
        "viewer/mesh_preview.vtk": "",
        "result_manifest.json": "{}",
    }
    with zipfile.ZipFile(result_zip, "w") as archive:
        for name, content in required_text_files.items():
            archive.writestr(name, content)

    result = validate_result_package(result_zip)

    assert result["qa_report_valid"] is False
    assert result["passed"] is False


def test_real_training_submission_schema_requires_acceptance_and_quality(tmp_path: Path):
    root = tmp_path / "submission"
    (root / "cad").mkdir(parents=True)
    (root / "ansa").mkdir()
    (root / "metadata").mkdir()
    (root / "cad" / "raw.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    (root / "ansa" / "final.ansa").write_text("ansa-db-placeholder", encoding="utf-8")
    (root / "metadata" / "acceptance.csv").write_text(
        "sample_id,acceptance_status,reviewer,review_date,use_for_training,reject_reason,notes\n"
        "AC_0001,accepted,kim,2026-05-02,true,,pilot\n",
        encoding="utf-8",
    )
    (root / "metadata" / "quality_criteria.yaml").write_text(
        "shell:\n  max_aspect_ratio: 8.0\n  max_skew_deg: 60.0\n  min_jacobian: 0.2\n",
        encoding="utf-8",
    )

    result = validate_training_submission_dir(root)

    assert result["valid"] is True
    assert result["material_constants_required"] is False
    assert result["acceptance_rows"][0]["acceptance_status"] == "accepted"
