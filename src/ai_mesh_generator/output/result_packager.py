from __future__ import annotations

import json
import zipfile
from pathlib import Path

from cae_mesh_common.bdf.bdf_reader import read_bdf_text
from cae_mesh_common.bdf.bdf_validator import validate_model
from cae_mesh_common.io.package_writer import zip_directory


def package_result(result_dir: Path | str, output_zip: Path | str) -> Path:
    result_dir = Path(result_dir)
    manifest = {
        "package_type": "MESH_RESULT",
        "solver_deck": "solver_deck/model_final.bdf",
        "mesh_recipe": "metadata/mesh_recipe_final.json",
        "qa_report": "report/qa_report.html",
        "qa_metrics": "report/qa_metrics_global.json",
        "viewer": "viewer/mesh_preview.vtk",
    }
    (result_dir / "result_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return zip_directory(result_dir, output_zip)


def validate_result_package(output_zip: Path | str) -> dict:
    required = {
        "solver_deck/model_final.bdf",
        "solver_deck/materials.inc",
        "solver_deck/properties.inc",
        "solver_deck/connections.inc",
        "solver_deck/sets.inc",
        "native/model_final.ansa",
        "metadata/mesh_recipe_final.json",
        "metadata/ai_prediction.json",
        "metadata/engineering_guard_log.json",
        "metadata/repair_history.json",
        "metadata/mesh_meta.json",
        "metadata/cad_to_mesh_mapping.parquet",
        "report/qa_report.html",
        "report/qa_metrics_global.json",
        "report/qa_metrics_part.csv",
        "report/qa_metrics_element.parquet",
        "report/failed_regions.csv",
        "report/manual_review_list.csv",
        "report/bdf_validation.json",
        "viewer/mesh_preview.vtk",
        "result_manifest.json",
    }
    with zipfile.ZipFile(output_zip, "r") as archive:
        names = set(archive.namelist())
        bdf_result = {"bdf_parse_success": False, "missing_property_count": 0, "missing_material_count": 0}
        if "solver_deck/model_final.bdf" in names:
            bdf_text = archive.read("solver_deck/model_final.bdf").decode("utf-8")
            validation = validate_model(read_bdf_text(bdf_text))
            bdf_result = validation.to_dict()
        qa_metrics = {}
        if "report/qa_metrics_global.json" in names:
            qa_metrics = json.loads(archive.read("report/qa_metrics_global.json").decode("utf-8"))
        qa_report_valid = False
        if "report/qa_report.html" in names:
            qa_report_text = archive.read("report/qa_report.html").decode("utf-8", errors="replace").lower()
            qa_report_valid = "placeholder qa reports are disabled" not in qa_report_text and "<h1>ansa qa report</h1>" not in qa_report_text
    missing = sorted(required - names)
    passed = (
        not missing
        and qa_report_valid
        and bool(bdf_result.get("bdf_parse_success"))
        and int(bdf_result.get("missing_property_count", 0)) == 0
        and int(bdf_result.get("missing_material_count", 0)) == 0
        and bool(qa_metrics.get("accepted", False))
    )
    return {
        "output_zip": str(output_zip),
        "missing": missing,
        "bdf_validation": bdf_result,
        "qa_metrics": qa_metrics,
        "qa_report_valid": qa_report_valid,
        "passed": passed,
    }
