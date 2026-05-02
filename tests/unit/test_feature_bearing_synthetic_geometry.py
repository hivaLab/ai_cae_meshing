from __future__ import annotations

import random
from pathlib import Path

import pytest

from cae_mesh_common.cad.step_io import validate_feature_bearing_step, write_ap242_brep_step
from cae_dataset_factory.cad.templates.bracket import BracketTemplate
from cae_dataset_factory.cad.templates.motor_dummy import MotorDummyTemplate
from cae_dataset_factory.cad.templates.pcb_dummy import PcbDummyTemplate
from cae_dataset_factory.cad.templates.plastic_base import PlasticBaseTemplate
from cae_dataset_factory.cad.templates.ribbed_cover import RibbedCoverTemplate
from cae_dataset_factory.cad.templates.screw import ScrewTemplate
from cae_dataset_factory.cad.templates.sheet_metal_box import SheetMetalBoxTemplate


@pytest.mark.parametrize(
    "template_cls",
    [
        PlasticBaseTemplate,
        RibbedCoverTemplate,
        SheetMetalBoxTemplate,
        BracketTemplate,
        ScrewTemplate,
        MotorDummyTemplate,
        PcbDummyTemplate,
    ],
)
def test_each_synthetic_template_exports_feature_bearing_step(template_cls: type, tmp_path: Path):
    part = template_cls().generate("part_000", random.Random(13)).to_dict()
    step_path = write_ap242_brep_step(tmp_path / f"{part['cad_template']}.step", "template_check", [part])

    evidence = validate_feature_bearing_step(step_path, [part])

    assert evidence["feature_bearing"], evidence
    if template_cls is not ScrewTemplate:
        assert evidence["advanced_face_count"] > 6
    assert evidence["cylindrical_surface_count"] > 0


def test_missing_template_builder_is_not_replaced_by_box_fallback(tmp_path: Path):
    part = {
        "part_uid": "part_missing_builder",
        "name": "unknown_family_00",
        "cad_template": "unknown_family",
        "dimensions": {"length": 20.0, "width": 10.0, "height": 5.0},
        "features": [],
    }

    with pytest.raises(ValueError, match="no feature-bearing CAD builder"):
        write_ap242_brep_step(tmp_path / "missing_builder.step", "missing_builder", [part])


def test_box_only_step_is_rejected_by_feature_validator(tmp_path: Path):
    import cadquery as cq
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Controller

    step_path = tmp_path / "box_only.step"
    STEPControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    assembly = cq.Assembly(name="box_only")
    assembly.add(cq.Workplane("XY").box(20.0, 10.0, 5.0, centered=(False, False, False)), name="part_000")
    assembly.save(str(step_path), exportType="STEP")
    part = {
        "part_uid": "part_000",
        "name": "plastic_base_00",
        "cad_template": "plastic_base",
        "dimensions": {"length": 20.0, "width": 10.0, "height": 5.0},
        "features": [{"feature_type": "screw_boss"}],
    }

    evidence = validate_feature_bearing_step(step_path, [part])

    assert not evidence["feature_bearing"]
    assert "box_only_or_underfeatured_face_count" in evidence["failures"]
