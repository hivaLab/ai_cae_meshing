from __future__ import annotations


EDGE_LOCAL_SPECS = [
    ("x_y0_z0", ("bottom", "front")),
    ("x_yw_z0", ("bottom", "back")),
    ("x_y0_zh", ("top", "front")),
    ("x_yw_zh", ("top", "back")),
    ("y_x0_z0", ("bottom", "left")),
    ("y_xl_z0", ("bottom", "right")),
    ("y_x0_zh", ("top", "left")),
    ("y_xl_zh", ("top", "right")),
    ("z_x0_y0", ("front", "left")),
    ("z_xl_y0", ("front", "right")),
    ("z_x0_yw", ("back", "left")),
    ("z_xl_yw", ("back", "right")),
]


def edge_labels(part: dict) -> list[dict]:
    feature_face_names = {_face_local_name(feature["face_uid"]) for feature in part.get("features", [])}
    labels = []
    for local_uid, incident_faces in EDGE_LOCAL_SPECS:
        if any(face_name in feature_face_names for face_name in incident_faces):
            semantic = "feature_edge"
        elif local_uid.startswith("z_"):
            semantic = "boundary_edge"
        else:
            semantic = "boundary_edge"
        labels.append({"edge_uid": f"{part['part_uid']}_edge_{local_uid}", "semantic": semantic})
    return labels


def _face_local_name(face_uid: str) -> str:
    return face_uid.rsplit("_face_", 1)[1]
