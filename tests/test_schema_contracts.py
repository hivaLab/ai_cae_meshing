from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v2_schema_files_are_valid_json() -> None:
    expected = {
        "AMG_BREP_ENTITY_GRAPH_SM_V2.schema.json",
        "AMG_SIZE_FIELD_SM_V2.schema.json",
        "CDF_PART_CLASS_LABEL_SM_V2.schema.json",
        "CDF_FACE_SEGMENTATION_SM_V2.schema.json",
        "CDF_EDGE_SEGMENTATION_SM_V2.schema.json",
        "CDF_MESH_SIZE_FIELD_SM_V2.schema.json",
        "CDF_ENTITY_QUALITY_EVALUATION_SM_V2.schema.json",
    }
    paths = {path.name: path for path in (ROOT / "contracts").glob("*.schema.json")}
    assert expected <= set(paths)
    for path in paths.values():
        Draft202012Validator.check_schema(load_json(path))


def test_size_field_example_validates() -> None:
    schema = load_json(ROOT / "contracts" / "AMG_SIZE_FIELD_SM_V2.schema.json")
    Draft202012Validator(schema).validate(
        {
            "schema_version": "AMG_SIZE_FIELD_SM_V2",
            "sample_id": "sample_000001",
            "cad_file": "cad/input.step",
            "unit": "mm",
            "global_mesh": {
                "h0_mm": 3.0,
                "h_min_mm": 0.5,
                "h_max_mm": 8.0,
                "growth_rate": 1.25,
                "quality_profile": "AMG_QA_SHELL_V2",
            },
            "edge_sizes": [
                {
                    "edge_signature_id": "EDGE_SIG_000001",
                    "target_size_mm": 0.75,
                    "source": "entity_quality_surrogate_optimizer",
                }
            ],
            "face_sizes": [],
        }
    )


def test_entity_label_enums_match_primary_contract() -> None:
    part = load_json(ROOT / "contracts" / "CDF_PART_CLASS_LABEL_SM_V2.schema.json")
    edge = load_json(ROOT / "contracts" / "CDF_EDGE_SEGMENTATION_SM_V2.schema.json")
    face = load_json(ROOT / "contracts" / "CDF_FACE_SEGMENTATION_SM_V2.schema.json")
    assert part["properties"]["part_class"]["enum"] == [
        "SM_FLAT_PANEL",
        "SM_SINGLE_FLANGE",
        "SM_L_BRACKET",
        "SM_U_CHANNEL",
        "SM_HAT_CHANNEL",
        "OTHER",
    ]
    assert "HOLE_BOUNDARY" in edge["properties"]["labels"]["items"]["properties"]["semantic_label"]["enum"]
    assert "BEND" in face["properties"]["labels"]["items"]["properties"]["semantic_label"]["enum"]
