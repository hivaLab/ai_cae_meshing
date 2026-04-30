from __future__ import annotations


def box_face_areas(length: float, width: float, height: float) -> list[float]:
    return [length * width, length * width, length * height, length * height, width * height, width * height]
