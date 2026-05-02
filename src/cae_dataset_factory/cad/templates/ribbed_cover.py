from __future__ import annotations

import random

from .base import AssemblyPort, FeatureRecord, GeneratedPart, PartTemplate, box_faces


class RibbedCoverTemplate(PartTemplate):
    name = "ribbed_cover"
    strategy = "shell"
    material_id = "MAT_ABS"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        length = rng.uniform(230.0, 310.0)
        width = rng.uniform(115.0, 175.0)
        height = rng.uniform(12.0, 24.0)
        labels, signatures = box_faces(part_uid, length, width, height)
        hole_radius = rng.uniform(2.2, 3.8)
        features = [
            FeatureRecord(f"{part_uid}_lip_front", "flange", f"{part_uid}_face_front", rng.uniform(5.0, 9.0), False),
            FeatureRecord(f"{part_uid}_lip_back", "flange", f"{part_uid}_face_back", rng.uniform(5.0, 9.0), False),
        ]
        for index in range(4):
            features.append(FeatureRecord(f"{part_uid}_rib_{index}", "rib", f"{part_uid}_face_bottom", rng.uniform(5.0, 10.0), True))
        ports = []
        hole_points = [
            (0, length * 0.12, width * 0.16),
            (1, length * 0.88, width * 0.16),
            (2, length * 0.12, width * 0.84),
            (3, length * 0.88, width * 0.84),
        ]
        for index, x, y in hole_points:
            features.append(FeatureRecord(f"{part_uid}_hole_{index}", "mounting_hole", f"{part_uid}_face_top", hole_radius, True))
            ports.append(AssemblyPort(f"{part_uid}_port_{index}", part_uid, "screw", (x, y, 0.0), (0.0, 0.0, -1.0)))
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, 2.0, features, labels, ports, signatures)
