from __future__ import annotations

import random

from .base import AssemblyPort, FeatureRecord, GeneratedPart, PartTemplate, box_faces


class SheetMetalBoxTemplate(PartTemplate):
    name = "sheet_metal_box"
    strategy = "shell"
    material_id = "MAT_STEEL"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        length = rng.uniform(180.0, 260.0)
        width = rng.uniform(90.0, 150.0)
        height = rng.uniform(40.0, 80.0)
        labels, signatures = box_faces(part_uid, length, width, height)
        features = [
            FeatureRecord(f"{part_uid}_flange_{i}", "flange", f"{part_uid}_face_front", rng.uniform(8.0, 16.0), False)
            for i in range(2)
        ]
        ports = [AssemblyPort(f"{part_uid}_port_mount", part_uid, "mount", (length / 2, width / 2, 0.0), (0.0, 0.0, -1.0))]
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, 1.0, features, labels, ports, signatures)
