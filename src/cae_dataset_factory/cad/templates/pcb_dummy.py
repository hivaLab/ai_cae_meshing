from __future__ import annotations

import random

from .base import AssemblyPort, FeatureRecord, GeneratedPart, PartTemplate, box_faces


class PcbDummyTemplate(PartTemplate):
    name = "pcb_dummy"
    strategy = "mass_only"
    material_id = "MAT_PCB"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        length = rng.uniform(95.0, 155.0)
        width = rng.uniform(55.0, 95.0)
        height = rng.uniform(1.2, 2.4)
        labels, signatures = box_faces(part_uid, length, width, height)
        features = [FeatureRecord(f"{part_uid}_board", "thin_board", f"{part_uid}_face_top", height, True)]
        ports = []
        for index, (x, y) in enumerate(
            [
                (length * 0.12, width * 0.14),
                (length * 0.88, width * 0.14),
                (length * 0.12, width * 0.86),
                (length * 0.88, width * 0.86),
            ]
        ):
            features.append(FeatureRecord(f"{part_uid}_hole_{index}", "mounting_hole", f"{part_uid}_face_top", rng.uniform(1.8, 3.2), True))
            ports.append(AssemblyPort(f"{part_uid}_port_{index}", part_uid, "standoff", (x, y, 0.0), (0.0, 0.0, -1.0)))
        return GeneratedPart(part_uid, self.name, self.material_id, self.strategy, {"length": length, "width": width, "height": height}, height, features, labels, ports, signatures)
