from __future__ import annotations

from pathlib import Path

from ai_mesh_generator.validation.step_ingestion_regression import run_step_ingestion_regression
from cae_mesh_common.cad.step_io import cad_kernel_status


def test_step_ingestion_regression_uses_real_ap242_brep(tmp_path: Path):
    status = cad_kernel_status()
    assert status["step_ap242_brep_export"], status

    report = run_step_ingestion_regression(tmp_path, sample_count=1)

    assert report["technical_passed"] is True
    assert report["accepted"] is False
    assert report["passed_count"] == 1
    record = report["records"][0]
    assert record["geometry_source"]["cad_kernel"] == "STEP_AP242_BREP_OCP"
    assert record["step_validation"]["is_brep"] is True
    assert record["step_validation"]["descriptor_only"] is False
    assert record["step_validation"]["advanced_face_count"] > 6 * record["node_counts"]["part"]
    assert record["step_validation"]["cylindrical_surface_count"] > 0
    assert record["feature_synthetic_validation"]["status"] == "FEATURE_SYNTHETIC_STEP"
    assert record["feature_synthetic_validation"]["passed"] is True
    assert record["topology_traceability"]["passed"] is True
    assert record["node_counts"]["part"] > 0
    assert record["node_counts"]["face"] > 0
    assert record["node_counts"]["edge"] > 0
    assert record["node_counts"]["contact_candidate"] > 0
    assert record["temporary_defaults_applied"]["any"] is True
