from __future__ import annotations

import random

from .base import FeatureRecord, GeneratedPart, PartTemplate, box_faces


class ScrewTemplate(PartTemplate):
    name = "screw"
    strategy = "connector"
    material_id = "MAT_STEEL"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        shank_diameter = rng.uniform(5.0, 8.0)
        head_diameter = rng.uniform(10.0, 16.0)
        shank_length = rng.uniform(24.0, 40.0)
        head_thickness = rng.uniform(3.2, 5.5)
        length = head_diameter
        width = head_diameter
        height = shank_length + head_thickness
        labels, signatures = box_faces(part_uid, length, width, height)
        features = [
            FeatureRecord(f"{part_uid}_shank", "cylindrical_shank", f"{part_uid}_face_right", shank_diameter / 2.0, True),
            FeatureRecord(f"{part_uid}_head", "screw_head", f"{part_uid}_face_left", head_diameter / 2.0, True),
        ]
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, 1.0, features, labels, [], signatures)
