from __future__ import annotations

import random

from .base import AssemblyPort, FeatureRecord, GeneratedPart, PartTemplate, box_faces


class PlasticBaseTemplate(PartTemplate):
    name = "plastic_base"
    strategy = "shell"
    material_id = "MAT_ABS"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        length = rng.uniform(240.0, 320.0)
        width = rng.uniform(120.0, 180.0)
        height = rng.uniform(28.0, 48.0)
        labels, signatures = box_faces(part_uid, length, width, height)
        features = [
            FeatureRecord(f"{part_uid}_boss_{i}", "screw_boss", f"{part_uid}_face_top", rng.uniform(5.0, 9.0), True)
            for i in range(4)
        ]
        ports = [
            AssemblyPort(f"{part_uid}_port_{i}", part_uid, "screw", (20.0 + i * 40.0, 20.0, height), (0.0, 0.0, 1.0))
            for i in range(4)
        ]
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, 2.2, features, labels, ports, signatures)
