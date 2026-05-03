from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

PART_CLASSES = [
    "SM_FLAT_PANEL",
    "SM_SINGLE_FLANGE",
    "SM_L_BRACKET",
    "SM_U_CHANNEL",
    "SM_HAT_CHANNEL",
]
FEATURE_TYPES = ["HOLE", "SLOT", "CUTOUT", "BEND", "FLANGE", "OUTER_BOUNDARY"]
FEATURE_ROLES = ["BOLT", "MOUNT", "RELIEF", "DRAIN", "VENT", "PASSAGE", "STRUCTURAL", "UNKNOWN"]
MANIFEST_ACTIONS = [
    "KEEP_REFINED",
    "KEEP_WITH_WASHER",
    "SUPPRESS",
    "KEEP_WITH_BEND_ROWS",
    "KEEP_WITH_FLANGE_SIZE",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_files_are_valid_json() -> None:
    expected = {
        "AMG_MANIFEST_SM_V1.schema.json",
        "AMG_BREP_GRAPH_SM_V1.schema.json",
        "AMG_CONFIG_SM_V1.schema.json",
        "AMG_FEATURE_OVERRIDES_SM_V1.schema.json",
        "CDF_CONFIG_SM_ANSA_V1.schema.json",
        "CDF_FEATURE_TRUTH_SM_V1.schema.json",
        "CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json",
        "CDF_ANSA_QUALITY_REPORT_SM_V1.schema.json",
    }
    paths = {path.name: path for path in (ROOT / "contracts").glob("*.schema.json")}
    assert expected <= set(paths)
    assert "CDF_ANSA_ORACLE_REPORT_SM_V1.schema.json" not in paths
    for path in paths.values():
        Draft202012Validator.check_schema(load_json(path))


def test_manifest_schema_enums_match_contract() -> None:
    schema = load_json(ROOT / "contracts" / "AMG_MANIFEST_SM_V1.schema.json")
    feature_props = schema["properties"]["features"]["items"]["properties"]
    assert schema["properties"]["status"]["enum"] == ["VALID", "OUT_OF_SCOPE", "MESH_FAILED"]
    assert schema["properties"]["part"]["properties"]["part_class"]["enum"] == PART_CLASSES
    assert feature_props["type"]["enum"] == FEATURE_TYPES
    assert feature_props["role"]["enum"] == FEATURE_ROLES
    assert feature_props["action"]["enum"] == MANIFEST_ACTIONS


def test_manifest_example_validates() -> None:
    schema = load_json(ROOT / "contracts" / "AMG_MANIFEST_SM_V1.schema.json")
    manifest = {
        "schema_version": "AMG_MANIFEST_SM_V1",
        "status": "VALID",
        "cad_file": "input.step",
        "unit": "mm",
        "part": {
            "part_name": "SMT_SM_L_BRACKET_W160_H90_T1p2_A83F",
            "part_class": "SM_L_BRACKET",
            "idealization": "midsurface_shell",
            "thickness_mm": 1.2,
            "element_type": "quad_dominant_shell",
            "batch_session": "AMG_SHELL_CONST_THICKNESS_V1",
        },
        "global_mesh": {
            "h0_mm": 4.0,
            "h_min_mm": 0.6,
            "h_max_mm": 8.0,
            "growth_rate_max": 1.3,
            "quality_profile": "AMG_QA_SHELL_V1",
        },
        "features": [
            {
                "feature_id": "HOLE_BOLT_0001",
                "type": "HOLE",
                "role": "BOLT",
                "action": "KEEP_WITH_WASHER",
                "geometry_signature": {
                    "center_mm": [42.0, 30.0, 0.0],
                    "axis": [0.0, 0.0, 1.0],
                    "radius_mm": 3.2,
                },
                "controls": {
                    "edge_target_length_mm": 0.84,
                    "circumferential_divisions": 24,
                    "washer_rings": 2,
                    "washer_outer_radius_mm": 7.5,
                    "radial_growth_rate": 1.25,
                },
            },
            {
                "feature_id": "BEND_STRUCTURAL_0005",
                "type": "BEND",
                "role": "STRUCTURAL",
                "action": "KEEP_WITH_BEND_ROWS",
                "controls": {
                    "bend_rows": 3,
                    "bend_target_length_mm": 1.8,
                    "growth_rate": 1.25,
                },
            },
        ],
        "entity_matching": {
            "position_tolerance_mm": 0.05,
            "angle_tolerance_deg": 2.0,
            "radius_tolerance_mm": 0.03,
            "use_geometry_signature": True,
            "use_topology_signature": True,
        },
    }
    Draft202012Validator(schema).validate(manifest)


def test_out_of_scope_manifest_validates() -> None:
    schema = load_json(ROOT / "contracts" / "AMG_MANIFEST_SM_V1.schema.json")
    Draft202012Validator(schema).validate(
        {
            "schema_version": "AMG_MANIFEST_SM_V1",
            "status": "OUT_OF_SCOPE",
            "reason": "non_constant_thickness",
        }
    )
