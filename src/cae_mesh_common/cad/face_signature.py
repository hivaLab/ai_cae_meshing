from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class FaceSignature:
    face_uid: str
    area: float
    centroid: tuple[float, float, float]
    normal: tuple[float, float, float]
    perimeter: float

    def distance(self, other: "FaceSignature") -> float:
        area_term = abs(self.area - other.area) / max(self.area, other.area, 1.0)
        perim_term = abs(self.perimeter - other.perimeter) / max(self.perimeter, other.perimeter, 1.0)
        centroid_term = sqrt(sum((a - b) ** 2 for a, b in zip(self.centroid, other.centroid))) / 1000.0
        normal_term = sum(abs(a - b) for a, b in zip(self.normal, other.normal)) / 3.0
        return area_term + perim_term + centroid_term + normal_term


def match_faces(
    source: list[FaceSignature], target: list[FaceSignature], max_distance: float = 0.05
) -> dict[str, str]:
    remaining = {face.face_uid: face for face in target}
    mapping: dict[str, str] = {}
    for face in source:
        if not remaining:
            break
        best_uid, best_face = min(remaining.items(), key=lambda item: face.distance(item[1]))
        if face.distance(best_face) <= max_distance:
            mapping[face.face_uid] = best_uid
            del remaining[best_uid]
    return mapping
