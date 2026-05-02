from __future__ import annotations

import random

from .base import AssemblyPort, FeatureRecord, GeneratedPart, PartTemplate, box_faces


class BracketTemplate(PartTemplate):
    name = "bracket"
    strategy = "shell"
    material_id = "MAT_STEEL"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        length = rng.uniform(70.0, 120.0)
        width = rng.uniform(38.0, 72.0)
        height = rng.uniform(42.0, 90.0)
        labels, signatures = box_faces(part_uid, length, width, height)
        hole_radius = rng.uniform(3.0, 5.0)
        features = [
            FeatureRecord(f"{part_uid}_bend", "bend", f"{part_uid}_face_back", rng.uniform(1.0, 2.5), True),
            FeatureRecord(f"{part_uid}_flange_base", "flange", f"{part_uid}_face_bottom", rng.uniform(14.0, 24.0), False),
            FeatureRecord(f"{part_uid}_flange_wall", "flange", f"{part_uid}_face_back", rng.uniform(14.0, 24.0), False),
        ]
        for index in range(4):
            features.append(FeatureRecord(f"{part_uid}_hole_{index}", "mounting_hole", f"{part_uid}_face_front", hole_radius, True))
        ports = [AssemblyPort(f"{part_uid}_port_mount", part_uid, "mount", (length / 2, width / 2, 0.0), (0.0, 0.0, -1.0))]
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, 1.2, features, labels, ports, signatures)
