from __future__ import annotations

import random

from .base import FeatureRecord, GeneratedPart, PartTemplate, box_faces


class MotorDummyTemplate(PartTemplate):
    name = "motor_dummy"
    strategy = "solid"
    material_id = "MAT_ALUMINUM"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        diameter = rng.uniform(48.0, 82.0)
        body_height = rng.uniform(70.0, 125.0)
        length = diameter
        width = diameter
        labels, signatures = box_faces(part_uid, length, width, body_height)
        features = [
            FeatureRecord(f"{part_uid}_body", "cylindrical_body", f"{part_uid}_face_top", diameter / 2.0, True),
            FeatureRecord(f"{part_uid}_shaft", "shaft", f"{part_uid}_face_right", rng.uniform(4.0, 8.0), True),
            FeatureRecord(f"{part_uid}_endcap", "endcap", f"{part_uid}_face_left", rng.uniform(2.0, 4.0), False),
        ]
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": body_height}, 0.0, features, labels, [], signatures)
