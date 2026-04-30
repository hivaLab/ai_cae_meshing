from __future__ import annotations

import pytest

from cae_mesh_common.schema.validators import SchemaValidationError, validate_object


def test_manifest_schema_validation_passes():
    validate_object(
        {
            "job_id": "job_001",
            "schema_version": "0.1.0",
            "units": "mm",
            "geometry": {"assembly_step": "geometry/assembly.step"},
            "metadata": {
                "product_tree": "metadata/product_tree.json",
                "part_attributes": "metadata/part_attributes.csv",
                "material_library": "metadata/material_library.json",
                "connections": "metadata/connections.csv",
                "mesh_profile": "metadata/mesh_profile.yaml",
            },
        },
        "input_package.schema.json",
    )


def test_product_tree_missing_part_uid_fails():
    with pytest.raises(SchemaValidationError):
        validate_object(
            {"assembly_id": "a", "root_part_uid": "p0", "parts": [{"name": "missing", "parent_uid": None, "transform": [1] * 16}]},
            "product_tree.schema.json",
        )


def test_material_missing_required_field_fails():
    with pytest.raises(SchemaValidationError):
        validate_object({"materials": [{"material_id": "MAT", "name": "bad"}]}, "material_library.schema.json")
