from __future__ import annotations

import random

from cae_dataset_factory.cad.templates.plastic_base import PlasticBaseTemplate
from cae_dataset_factory.cad.templates.sheet_metal_box import SheetMetalBoxTemplate


def test_templates_generate_features_and_faces():
    rng = random.Random(1)
    plastic = PlasticBaseTemplate().generate("part_a", rng)
    sheet = SheetMetalBoxTemplate().generate("part_b", rng)
    assert plastic.features
    assert plastic.face_labels
    assert sheet.face_signatures
    assert plastic.to_dict()["part_uid"] == "part_a"
