from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from cae_mesh_common.cad.face_signature import FaceSignature


@dataclass
class FeatureRecord:
    feature_uid: str
    feature_type: str
    face_uid: str
    size: float
    preserve: bool = False


@dataclass
class FaceLabel:
    face_uid: str
    semantic: str
    midsurface: bool
    preserve: bool


@dataclass
class AssemblyPort:
    port_uid: str
    part_uid: str
    kind: str
    location: tuple[float, float, float]
    normal: tuple[float, float, float]


@dataclass
class GeneratedPart:
    part_uid: str
    name: str
    material_id: str
    strategy: str
    dimensions: dict[str, float]
    nominal_thickness: float
    features: list[FeatureRecord] = field(default_factory=list)
    face_labels: list[FaceLabel] = field(default_factory=list)
    ports: list[AssemblyPort] = field(default_factory=list)
    face_signatures: list[FaceSignature] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "part_uid": self.part_uid,
            "name": self.name,
            "cad_template": self.name,
            "material_id": self.material_id,
            "strategy": self.strategy,
            "dimensions": self.dimensions,
            "nominal_thickness": self.nominal_thickness,
            "features": [feature.__dict__ for feature in self.features],
            "face_labels": [label.__dict__ for label in self.face_labels],
            "ports": [
                {
                    "port_uid": port.port_uid,
                    "part_uid": port.part_uid,
                    "kind": port.kind,
                    "location": list(port.location),
                    "normal": list(port.normal),
                }
                for port in self.ports
            ],
            "face_signatures": [
                {
                    "face_uid": face.face_uid,
                    "area": face.area,
                    "centroid": list(face.centroid),
                    "normal": list(face.normal),
                    "perimeter": face.perimeter,
                }
                for face in self.face_signatures
            ],
        }


class PartTemplate:
    name = "part"
    strategy = "shell"
    material_id = "MAT_STEEL"

    def generate(self, part_uid: str, rng: random.Random) -> GeneratedPart:
        raise NotImplementedError


def box_faces(part_uid: str, length: float, width: float, height: float) -> tuple[list[FaceLabel], list[FaceSignature]]:
    labels: list[FaceLabel] = []
    signatures: list[FaceSignature] = []
    specs = [
        ("top", length * width, (length / 2, width / 2, height), (0, 0, 1), 2 * (length + width), True),
        ("bottom", length * width, (length / 2, width / 2, 0), (0, 0, -1), 2 * (length + width), True),
        ("front", length * height, (length / 2, 0, height / 2), (0, -1, 0), 2 * (length + height), False),
        ("back", length * height, (length / 2, width, height / 2), (0, 1, 0), 2 * (length + height), False),
        ("left", width * height, (0, width / 2, height / 2), (-1, 0, 0), 2 * (width + height), False),
        ("right", width * height, (length, width / 2, height / 2), (1, 0, 0), 2 * (width + height), False),
    ]
    for name, area, centroid, normal, perimeter, midsurface in specs:
        uid = f"{part_uid}_face_{name}"
        labels.append(FaceLabel(uid, "structural" if midsurface else "side_wall", midsurface, name in {"top", "bottom"}))
        signatures.append(FaceSignature(uid, area, centroid, normal, perimeter))
    return labels, signatures
