from __future__ import annotations


def face_labels(part: dict) -> list[dict]:
    return part.get("face_labels", [])
