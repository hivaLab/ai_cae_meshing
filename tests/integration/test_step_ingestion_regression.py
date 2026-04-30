from __future__ import annotations

from pathlib import Path

from ai_mesh_generator.validation.step_ingestion_regression import run_step_ingestion_regression
from cae_mesh_common.cad.step_io import cad_kernel_status


def test_step_ingestion_regression_uses_real_ap242_brep(tmp_path: Path):
    status = cad_kernel_status()
    assert status["step_ap242_brep_export"], status

    report = run_step_ingestion_regression(tmp_path, sample_count=1)

    assert report["accepted"] is True
    assert report["passed_count"] == 1
    record = report["records"][0]
    assert record["geometry_source"]["cad_kernel"] == "STEP_AP242_BREP"
    assert record["step_validation"]["is_brep"] is True
    assert record["step_validation"]["descriptor_only"] is False
    assert record["node_counts"]["part"] > 0
    assert record["node_counts"]["face"] > 0
