from __future__ import annotations

import json
import zipfile
from pathlib import Path

from cae_mesh_common.io.package_writer import zip_directory


def package_result(result_dir: Path | str, output_zip: Path | str) -> Path:
    result_dir = Path(result_dir)
    manifest = {
        "package_type": "MESH_RESULT",
        "solver_deck": "solver_deck/model_final.bdf",
        "mesh_recipe": "metadata/mesh_recipe_final.json",
        "qa_report": "reports/qa_report.html",
        "qa_metrics": "reports/qa_metrics.json",
    }
    (result_dir / "result_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return zip_directory(result_dir, output_zip)


def validate_result_package(output_zip: Path | str) -> dict:
    required = {
        "solver_deck/model_final.bdf",
        "metadata/mesh_recipe_final.json",
        "reports/qa_report.html",
        "reports/qa_metrics.json",
        "reports/bdf_validation.json",
        "result_manifest.json",
    }
    with zipfile.ZipFile(output_zip, "r") as archive:
        names = set(archive.namelist())
    missing = sorted(required - names)
    return {"output_zip": str(output_zip), "missing": missing, "passed": not missing}
