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
        boss_radius = rng.uniform(5.0, 8.0)
        rib_height = rng.uniform(7.0, 12.0)
        features = []
        ports = []
        boss_points = [
            (0, length * 0.16, width * 0.18),
            (1, length * 0.84, width * 0.18),
            (2, length * 0.16, width * 0.82),
            (3, length * 0.84, width * 0.82),
        ]
        for index, x, y in boss_points:
            features.append(FeatureRecord(f"{part_uid}_boss_{index}", "screw_boss", f"{part_uid}_face_top", boss_radius, True))
            features.append(FeatureRecord(f"{part_uid}_hole_{index}", "mounting_hole", f"{part_uid}_face_top", boss_radius * 0.46, True))
            ports.append(AssemblyPort(f"{part_uid}_port_{index}", part_uid, "screw", (x, y, height), (0.0, 0.0, 1.0)))
        for index in range(3):
            features.append(FeatureRecord(f"{part_uid}_rib_{index}", "rib", f"{part_uid}_face_top", rib_height, True))
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, 2.2, features, labels, ports, signatures)
