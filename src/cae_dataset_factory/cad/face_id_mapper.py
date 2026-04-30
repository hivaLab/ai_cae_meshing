from __future__ import annotations

from cae_mesh_common.cad.face_signature import FaceSignature, match_faces


def map_reimported_faces(source: list[FaceSignature | dict], target: list[FaceSignature | dict]) -> dict[str, str]:
    return match_faces([_coerce(item) for item in source], [_coerce(item) for item in target], max_distance=0.02)


def _coerce(item: FaceSignature | dict) -> FaceSignature:
    if isinstance(item, FaceSignature):
        return item
    return FaceSignature(
        face_uid=item["face_uid"],
        area=float(item["area"]),
        centroid=tuple(item["centroid"]),
        normal=tuple(item["normal"]),
        perimeter=float(item["perimeter"]),
    )
