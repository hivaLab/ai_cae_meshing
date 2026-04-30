from __future__ import annotations

from pathlib import Path

from cae_mesh_common.bdf.bdf_validator import validate_bdf


VALID_BDF = """BEGIN BULK
MAT1,1,210000,,0.3,7.85e-9
GRID,1,,0,0,0
GRID,2,,1,0,0
GRID,3,,1,1,0
GRID,4,,0,1,0
PSHELL,1,1,1.0
CQUAD4,1,1,1,2,3,4
ENDDATA
"""


def test_valid_bdf_parse_pass(tmp_path: Path):
    path = tmp_path / "valid.bdf"
    path.write_text(VALID_BDF, encoding="utf-8")
    assert validate_bdf(path).passed


def test_missing_property_detected(tmp_path: Path):
    path = tmp_path / "missing_prop.bdf"
    path.write_text(VALID_BDF.replace("CQUAD4,1,1", "CQUAD4,1,99"), encoding="utf-8")
    assert validate_bdf(path).missing_property_count == 1


def test_missing_material_detected(tmp_path: Path):
    path = tmp_path / "missing_mat.bdf"
    path.write_text(VALID_BDF.replace("PSHELL,1,1", "PSHELL,1,99"), encoding="utf-8")
    assert validate_bdf(path).missing_material_count == 1


def test_duplicate_id_detected(tmp_path: Path):
    path = tmp_path / "dup.bdf"
    path.write_text(VALID_BDF.replace("GRID,2", "GRID,1"), encoding="utf-8")
    assert validate_bdf(path).duplicate_id_count >= 1
