from __future__ import annotations

from math import sqrt
from typing import Any

from cae_mesh_common.graph.hetero_graph import HeteroGraph


PART_FEATURE_NAMES = [
    "length_mm",
    "width_mm",
    "height_mm",
    "thickness_mm",
    "volume_mm3",
    "surface_area_mm2",
    "aspect_lw",
    "aspect_lh",
    "aspect_wh",
    "port_count",
    "feature_count",
    "material_steel",
    "material_abs",
    "material_aluminum",
    "material_pcb",
    "role_base",
    "role_cover",
    "role_bracket",
    "role_fastener",
    "role_electronic",
    "role_motor",
    "connection_count",
]

FACE_FEATURE_NAMES = [
    "area_mm2",
    "perimeter_mm",
    "centroid_x_mm",
    "centroid_y_mm",
    "centroid_z_mm",
    "normal_x",
    "normal_y",
    "normal_z",
    "area_ratio_to_part",
    "perimeter_ratio_to_part",
    "center_distance_ratio",
    "feature_count",
    "preserved_feature_count",
    "is_top_or_bottom",
    "is_side_face",
]

EDGE_FEATURE_NAMES = [
    "length_mm",
    "midpoint_x_mm",
    "midpoint_y_mm",
    "midpoint_z_mm",
    "tangent_x",
    "tangent_y",
    "tangent_z",
    "length_ratio_to_part_max",
    "feature_touch_count",
    "preserved_feature_touch_count",
    "is_short_edge",
    "is_vertical_edge",
]

CONTACT_FEATURE_NAMES = [
    "type_screw",
    "type_tied",
    "type_adhesive",
    "type_hinge",
    "gap_mm",
    "opposing_normal_dot",
    "overlap_ratio",
    "diameter_mm",
    "washer_radius_mm",
    "preserve_hole",
    "confidence",
    "face_area_ratio",
]

CONNECTION_FEATURE_NAMES = [
    "type_screw",
    "type_tied",
    "type_adhesive",
    "type_hinge",
    "diameter_mm",
    "washer_radius_mm",
    "axis_x",
    "axis_y",
    "axis_z",
    "preserve_hole",
    "confidence",
    "master_part_norm",
    "slave_part_norm",
]

NODE_FEATURE_NAMES = {
    "part": PART_FEATURE_NAMES,
    "face": FACE_FEATURE_NAMES,
    "edge": EDGE_FEATURE_NAMES,
    "contact_candidate": CONTACT_FEATURE_NAMES,
    "connection": CONNECTION_FEATURE_NAMES,
}

BOX_FACE_NAMES = {"top", "bottom", "front", "back", "left", "right"}
MATERIAL_IDS = ["MAT_STEEL", "MAT_ABS", "MAT_ALUMINUM", "MAT_PCB"]
CONNECTION_TYPES = ["screw", "tied", "adhesive", "hinge"]


def build_brep_graph(assembly: dict[str, Any]) -> HeteroGraph:
    parts = assembly.get("parts", [])
    if not parts:
        raise ValueError("assembly must contain at least one part")
    part_index = {part["part_uid"]: index for index, part in enumerate(parts)}
    connection_counts = _connection_counts(parts, assembly.get("connections", []))

    node_sets: dict[str, list[dict[str, Any]]] = {
        "part": [],
        "face": [],
        "edge": [],
        "contact_candidate": [],
        "connection": [],
    }
    node_features: dict[str, list[list[float]]] = {node_type: [] for node_type in NODE_FEATURE_NAMES}
    edge_sets: dict[str, list[tuple[int, int]]] = {
        "part__has_face__face": [],
        "face__belongs_to__part": [],
        "part__has_edge__edge": [],
        "edge__belongs_to__part": [],
        "face__incident_to__edge": [],
        "edge__incident_to__face": [],
        "face__shares_edge__face": [],
        "part__near__part": [],
        "part__has_connection__connection": [],
        "connection__links_part__part": [],
        "contact_candidate__source_face__face": [],
        "contact_candidate__target_face__face": [],
        "face__has_contact_candidate__contact_candidate": [],
        "connection__has_contact_candidate__contact_candidate": [],
        "contact_candidate__belongs_to__connection": [],
        "contact_candidate__connects_part__part": [],
    }

    face_index_by_uid: dict[str, int] = {}
    face_records_by_part: dict[str, list[dict[str, Any]]] = {}
    edge_count = 0

    for p_index, part in enumerate(parts):
        if _uses_extracted_topology(part):
            _validate_extracted_part_topology(part)
        else:
            _validate_part_topology(part)
        node_sets["part"].append({"uid": part["part_uid"], "part_index": p_index, "name": part.get("name", "")})
        node_features["part"].append(_part_features(part, connection_counts.get(part["part_uid"], 0)))

        face_records_by_part[part["part_uid"]] = []
        face_uid_by_name = {} if _uses_extracted_topology(part) else _face_uid_by_name(part)
        feature_counts = _feature_counts_by_face(part)
        for face in part["face_signatures"]:
            f_index = len(node_sets["face"])
            face_index_by_uid[face["face_uid"]] = f_index
            face_record = {
                "uid": face["face_uid"],
                "part_uid": part["part_uid"],
                "part_index": p_index,
                "local_name": str(face.get("local_name") or _safe_face_local_name(face["face_uid"])),
                "centroid": [float(value) for value in face["centroid"]],
                "normal": [float(value) for value in face["normal"]],
                "area": float(face["area"]),
                "perimeter": float(face["perimeter"]),
            }
            node_sets["face"].append(face_record)
            node_features["face"].append(_face_features(part, face, feature_counts))
            face_records_by_part[part["part_uid"]].append(face_record)
            edge_sets["part__has_face__face"].append((p_index, f_index))
            edge_sets["face__belongs_to__part"].append((f_index, p_index))

        edge_records = (
            _topology_edges_for_part(part, feature_counts)
            if _uses_extracted_topology(part)
            else _box_edges_for_part(part, face_uid_by_name, feature_counts)
        )
        for edge in edge_records:
            e_index = len(node_sets["edge"])
            node_sets["edge"].append(
                {
                    "uid": edge["uid"],
                    "part_uid": part["part_uid"],
                    "part_index": p_index,
                    "incident_face_uids": edge["incident_face_uids"],
                    "midpoint": edge["midpoint"],
                    "tangent": edge["tangent"],
                }
            )
            node_features["edge"].append(edge["features"])
            edge_sets["part__has_edge__edge"].append((p_index, e_index))
            edge_sets["edge__belongs_to__part"].append((e_index, p_index))
            incident_face_indices = [face_index_by_uid[uid] for uid in edge["incident_face_uids"]]
            for f_index in incident_face_indices:
                edge_sets["face__incident_to__edge"].append((f_index, e_index))
                edge_sets["edge__incident_to__face"].append((e_index, f_index))
            if len(incident_face_indices) == 2:
                a, b = incident_face_indices
                edge_sets["face__shares_edge__face"].append((a, b))
                edge_sets["face__shares_edge__face"].append((b, a))
            edge_count += 1

    for connection in assembly.get("connections", []):
        if connection["part_uid_a"] not in part_index or connection["part_uid_b"] not in part_index:
            raise ValueError(f"connection references unknown part: {connection}")
        conn_index = len(node_sets["connection"])
        a_index = part_index[connection["part_uid_a"]]
        b_index = part_index[connection["part_uid_b"]]
        contact = _best_contact_candidate(connection, face_records_by_part)
        contact_index = len(node_sets["contact_candidate"])
        node_sets["contact_candidate"].append(contact["node"])
        node_features["contact_candidate"].append(contact["features"])

        axis = contact["axis"]
        node_sets["connection"].append(
            {
                "uid": connection["connection_uid"],
                "type": connection.get("type", "unknown"),
                "part_uid_a": connection["part_uid_a"],
                "part_uid_b": connection["part_uid_b"],
                "contact_candidate_uid": contact["node"]["uid"],
            }
        )
        node_features["connection"].append(_connection_features(connection, axis, a_index, b_index, len(parts)))

        edge_sets["part__near__part"].append((a_index, b_index))
        edge_sets["part__near__part"].append((b_index, a_index))
        edge_sets["part__has_connection__connection"].append((a_index, conn_index))
        edge_sets["part__has_connection__connection"].append((b_index, conn_index))
        edge_sets["connection__links_part__part"].append((conn_index, a_index))
        edge_sets["connection__links_part__part"].append((conn_index, b_index))
        edge_sets["connection__has_contact_candidate__contact_candidate"].append((conn_index, contact_index))
        edge_sets["contact_candidate__belongs_to__connection"].append((contact_index, conn_index))
        edge_sets["contact_candidate__connects_part__part"].append((contact_index, a_index))
        edge_sets["contact_candidate__connects_part__part"].append((contact_index, b_index))

        source_face = face_index_by_uid[contact["node"]["face_uid_a"]]
        target_face = face_index_by_uid[contact["node"]["face_uid_b"]]
        edge_sets["contact_candidate__source_face__face"].append((contact_index, source_face))
        edge_sets["contact_candidate__target_face__face"].append((contact_index, target_face))
        edge_sets["face__has_contact_candidate__contact_candidate"].append((source_face, contact_index))
        edge_sets["face__has_contact_candidate__contact_candidate"].append((target_face, contact_index))

    graph = HeteroGraph(
        sample_id=assembly["sample_id"],
        node_sets=node_sets,
        edge_sets=edge_sets,
        node_features=node_features,
        node_feature_names=NODE_FEATURE_NAMES,
        graph_features=graph_feature_vector(assembly, edge_count=edge_count, contact_count=len(node_sets["contact_candidate"])),
        metadata={
            "graph_format": "cae_hetero_brep_assembly_graph_v1",
            "node_types": list(node_sets),
            "edge_types": list(edge_sets),
            "source_geometry": assembly.get("geometry_source", {}),
        },
    )
    _validate_graph(graph)
    return graph


def graph_feature_vector(assembly: dict[str, Any], edge_count: int | None = None, contact_count: int | None = None) -> dict[str, float]:
    parts = assembly["parts"]
    connections = assembly.get("connections", [])
    defects = assembly.get("defects", [])
    mean_length = sum(float(part["dimensions"]["length"]) for part in parts) / len(parts)
    mean_width = sum(float(part["dimensions"]["width"]) for part in parts) / len(parts)
    mean_height = sum(float(part["dimensions"]["height"]) for part in parts) / len(parts)
    return {
        "part_count": float(len(parts)),
        "face_count": float(sum(len(part.get("face_signatures", [])) for part in parts)),
        "connection_count": float(len(connections)),
        "defect_count": float(len(defects)),
        "mean_length": mean_length,
        "mean_width": mean_width,
        "mean_height": mean_height,
        "edge_count": float(edge_count if edge_count is not None else sum(12 for _ in parts)),
        "contact_candidate_count": float(contact_count if contact_count is not None else len(connections)),
    }


def _validate_part_topology(part: dict[str, Any]) -> None:
    if "dimensions" not in part:
        raise ValueError(f"part is missing dimensions: {part.get('part_uid')}")
    missing_dims = {"length", "width", "height"} - set(part["dimensions"])
    if missing_dims:
        raise ValueError(f"part {part.get('part_uid')} missing dimensions {sorted(missing_dims)}")
    face_names = {_face_local_name(face["face_uid"]) for face in part.get("face_signatures", [])}
    missing_faces = BOX_FACE_NAMES - face_names
    if missing_faces:
        raise ValueError(f"part {part.get('part_uid')} missing B-Rep box faces {sorted(missing_faces)}")


def _uses_extracted_topology(part: dict[str, Any]) -> bool:
    return bool(part.get("topology_edges")) or str(part.get("topology_source", "")).startswith("STEP_AP242_BREP")


def _validate_extracted_part_topology(part: dict[str, Any]) -> None:
    if "dimensions" not in part:
        raise ValueError(f"STEP part is missing dimensions: {part.get('part_uid')}")
    missing_dims = {"length", "width", "height"} - set(part["dimensions"])
    if missing_dims:
        raise ValueError(f"STEP part {part.get('part_uid')} missing dimensions {sorted(missing_dims)}")
    if not part.get("face_signatures"):
        raise ValueError(f"STEP part {part.get('part_uid')} has no extracted faces")
    if not part.get("topology_edges"):
        raise ValueError(f"STEP part {part.get('part_uid')} has no extracted edges")
    face_uids = {face.get("face_uid") for face in part.get("face_signatures", [])}
    for edge in part.get("topology_edges", []):
        missing = set(edge.get("incident_face_uids", [])) - face_uids
        if missing:
            raise ValueError(f"STEP part {part.get('part_uid')} edge references unknown faces {sorted(missing)}")


def _validate_graph(graph: HeteroGraph) -> None:
    for node_type, feature_names in graph.node_feature_names.items():
        rows = graph.node_features.get(node_type, [])
        for row in rows:
            if len(row) != len(feature_names):
                raise ValueError(f"{node_type} feature width {len(row)} != {len(feature_names)}")
    node_counts = {node_type: len(nodes) for node_type, nodes in graph.node_sets.items()}
    for edge_type, edges in graph.edge_sets.items():
        source_type, _, target_type = edge_type.split("__")
        for source, target in edges:
            if source < 0 or source >= node_counts[source_type]:
                raise ValueError(f"{edge_type} source index {source} out of range")
            if target < 0 or target >= node_counts[target_type]:
                raise ValueError(f"{edge_type} target index {target} out of range")


def _connection_counts(parts: list[dict[str, Any]], connections: list[dict[str, Any]]) -> dict[str, int]:
    counts = {part["part_uid"]: 0 for part in parts}
    for connection in connections:
        counts[connection["part_uid_a"]] = counts.get(connection["part_uid_a"], 0) + 1
        counts[connection["part_uid_b"]] = counts.get(connection["part_uid_b"], 0) + 1
    return counts


def _part_features(part: dict[str, Any], connection_count: int) -> list[float]:
    length, width, height = _dims(part)
    thickness = float(part["nominal_thickness"])
    surface_area = 2.0 * (length * width + length * height + width * height)
    role = _role_flags(part.get("name", ""))
    material = [1.0 if part.get("material_id") == material_id else 0.0 for material_id in MATERIAL_IDS]
    return [
        length,
        width,
        height,
        thickness,
        length * width * height,
        surface_area,
        length / max(width, 1e-9),
        length / max(height, 1e-9),
        width / max(height, 1e-9),
        float(len(part.get("ports", []))),
        float(len(part.get("features", []))),
        *material,
        *role,
        float(connection_count),
    ]


def _face_features(part: dict[str, Any], face: dict[str, Any], feature_counts: dict[str, tuple[int, int]]) -> list[float]:
    length, width, height = _dims(part)
    area = float(face["area"])
    perimeter = float(face["perimeter"])
    centroid = [float(value) for value in face["centroid"]]
    normal = [float(value) for value in face["normal"]]
    surface_area = 2.0 * (length * width + length * height + width * height)
    bbox_perimeter = 4.0 * (length + width + height)
    center = [length / 2.0, width / 2.0, height / 2.0]
    diag = sqrt(length * length + width * width + height * height)
    feature_count, preserved_count = feature_counts.get(face["face_uid"], (0, 0))
    is_top_or_bottom = 1.0 if abs(normal[2]) > 0.9 else 0.0
    return [
        area,
        perimeter,
        centroid[0],
        centroid[1],
        centroid[2],
        normal[0],
        normal[1],
        normal[2],
        area / max(surface_area, 1e-9),
        perimeter / max(bbox_perimeter, 1e-9),
        _distance(centroid, center) / max(diag, 1e-9),
        float(feature_count),
        float(preserved_count),
        is_top_or_bottom,
        1.0 - is_top_or_bottom,
    ]


def _box_edges_for_part(
    part: dict[str, Any],
    face_uid_by_name: dict[str, str],
    feature_counts: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    length, width, height = _dims(part)
    max_dim = max(length, width, height, 1e-9)
    specs = [
        ("x_y0_z0", length, (length / 2.0, 0.0, 0.0), (1.0, 0.0, 0.0), ("bottom", "front")),
        ("x_yw_z0", length, (length / 2.0, width, 0.0), (1.0, 0.0, 0.0), ("bottom", "back")),
        ("x_y0_zh", length, (length / 2.0, 0.0, height), (1.0, 0.0, 0.0), ("top", "front")),
        ("x_yw_zh", length, (length / 2.0, width, height), (1.0, 0.0, 0.0), ("top", "back")),
        ("y_x0_z0", width, (0.0, width / 2.0, 0.0), (0.0, 1.0, 0.0), ("bottom", "left")),
        ("y_xl_z0", width, (length, width / 2.0, 0.0), (0.0, 1.0, 0.0), ("bottom", "right")),
        ("y_x0_zh", width, (0.0, width / 2.0, height), (0.0, 1.0, 0.0), ("top", "left")),
        ("y_xl_zh", width, (length, width / 2.0, height), (0.0, 1.0, 0.0), ("top", "right")),
        ("z_x0_y0", height, (0.0, 0.0, height / 2.0), (0.0, 0.0, 1.0), ("front", "left")),
        ("z_xl_y0", height, (length, 0.0, height / 2.0), (0.0, 0.0, 1.0), ("front", "right")),
        ("z_x0_yw", height, (0.0, width, height / 2.0), (0.0, 0.0, 1.0), ("back", "left")),
        ("z_xl_yw", height, (length, width, height / 2.0), (0.0, 0.0, 1.0), ("back", "right")),
    ]
    records = []
    for local_uid, edge_length, midpoint, tangent, incident_face_names in specs:
        face_uids = [face_uid_by_name[name] for name in incident_face_names]
        feature_touch = sum(feature_counts.get(uid, (0, 0))[0] for uid in face_uids)
        preserved_touch = sum(feature_counts.get(uid, (0, 0))[1] for uid in face_uids)
        records.append(
            {
                "uid": f"{part['part_uid']}_edge_{local_uid}",
                "incident_face_uids": face_uids,
                "midpoint": list(midpoint),
                "tangent": list(tangent),
                "features": [
                    edge_length,
                    midpoint[0],
                    midpoint[1],
                    midpoint[2],
                    tangent[0],
                    tangent[1],
                    tangent[2],
                    edge_length / max_dim,
                    float(feature_touch),
                    float(preserved_touch),
                    1.0 if edge_length < 8.0 else 0.0,
                    1.0 if abs(tangent[2]) > 0.9 else 0.0,
                ],
            }
        )
    return records


def _topology_edges_for_part(part: dict[str, Any], feature_counts: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    length, width, height = _dims(part)
    max_dim = max(length, width, height, 1.0e-9)
    records = []
    for edge in part.get("topology_edges", []):
        edge_length = float(edge.get("length", 0.0))
        midpoint = [float(value) for value in edge.get("midpoint", [0.0, 0.0, 0.0])]
        tangent = _unit([float(value) for value in edge.get("tangent", [1.0, 0.0, 0.0])])
        incident_face_uids = [uid for uid in edge.get("incident_face_uids", []) if uid]
        feature_touch = sum(feature_counts.get(uid, (0, 0))[0] for uid in incident_face_uids)
        preserved_touch = sum(feature_counts.get(uid, (0, 0))[1] for uid in incident_face_uids)
        records.append(
            {
                "uid": edge.get("edge_uid") or edge.get("uid") or f"{part['part_uid']}_edge_{len(records):03d}",
                "incident_face_uids": incident_face_uids,
                "midpoint": midpoint,
                "tangent": tangent,
                "features": [
                    edge_length,
                    midpoint[0],
                    midpoint[1],
                    midpoint[2],
                    tangent[0],
                    tangent[1],
                    tangent[2],
                    edge_length / max_dim,
                    float(feature_touch),
                    float(preserved_touch),
                    1.0 if edge_length < 8.0 else 0.0,
                    1.0 if abs(tangent[2]) > 0.9 else 0.0,
                ],
            }
        )
    return records


def _best_contact_candidate(
    connection: dict[str, Any],
    face_records_by_part: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    faces_a = face_records_by_part[connection["part_uid_a"]]
    faces_b = face_records_by_part[connection["part_uid_b"]]
    best: tuple[float, dict[str, Any], dict[str, Any], float, float, float] | None = None
    nearest: tuple[float, dict[str, Any], dict[str, Any], float, float, float] | None = None
    for face_a in faces_a:
        for face_b in faces_b:
            dot = _dot(face_a["normal"], face_b["normal"])
            gap = abs(_dot(_subtract(face_b["centroid"], face_a["centroid"]), face_a["normal"]))
            overlap = _projected_overlap_ratio(face_a, face_b)
            area_ratio = min(face_a["area"], face_b["area"]) / max(face_a["area"], face_b["area"], 1e-9)
            distance = _distance(face_a["centroid"], face_b["centroid"])
            if nearest is None or distance < nearest[0]:
                nearest = (distance, face_a, face_b, gap, overlap, area_ratio)
            if dot > -0.85:
                continue
            score = overlap - gap / 1000.0 - abs(dot + 1.0)
            if best is None or score > best[0]:
                best = (score, face_a, face_b, gap, overlap, area_ratio)
    if best is None:
        if nearest is None:
            raise ValueError(f"no B-Rep faces found for connection {connection['connection_uid']}")
        best = nearest
    _, face_a, face_b, gap, overlap, area_ratio = best
    axis = _unit(_subtract(face_b["centroid"], face_a["centroid"]))
    features = [
        *_one_hot(str(connection.get("type", "unknown")), CONNECTION_TYPES),
        gap,
        _dot(face_a["normal"], face_b["normal"]),
        overlap,
        float(connection.get("diameter_mm", 3.0)),
        float(connection.get("washer_radius_mm", 5.0)),
        1.0 if bool(connection.get("preserve_hole", False)) else 0.0,
        float(connection.get("confidence", 1.0)),
        area_ratio,
    ]
    return {
        "axis": axis,
        "features": features,
        "node": {
            "uid": f"contact_{connection['connection_uid']}",
            "connection_uid": connection["connection_uid"],
            "part_uid_a": connection["part_uid_a"],
            "part_uid_b": connection["part_uid_b"],
            "face_uid_a": face_a["uid"],
            "face_uid_b": face_b["uid"],
            "gap_mm": gap,
            "overlap_ratio": overlap,
        },
    }


def _connection_features(connection: dict[str, Any], axis: list[float], a_index: int, b_index: int, part_count: int) -> list[float]:
    denom = max(part_count - 1, 1)
    return [
        *_one_hot(str(connection.get("type", "unknown")), CONNECTION_TYPES),
        float(connection.get("diameter_mm", 3.0)),
        float(connection.get("washer_radius_mm", 5.0)),
        axis[0],
        axis[1],
        axis[2],
        1.0 if bool(connection.get("preserve_hole", False)) else 0.0,
        float(connection.get("confidence", 1.0)),
        float(a_index) / denom,
        float(b_index) / denom,
    ]


def _face_uid_by_name(part: dict[str, Any]) -> dict[str, str]:
    mapping = {_face_local_name(face["face_uid"]): face["face_uid"] for face in part["face_signatures"]}
    missing = BOX_FACE_NAMES - set(mapping)
    if missing:
        raise ValueError(f"part {part['part_uid']} missing face signatures for {sorted(missing)}")
    return mapping


def _feature_counts_by_face(part: dict[str, Any]) -> dict[str, tuple[int, int]]:
    counts: dict[str, tuple[int, int]] = {}
    for feature in part.get("features", []):
        face_uid = feature["face_uid"]
        current, preserved = counts.get(face_uid, (0, 0))
        counts[face_uid] = (current + 1, preserved + (1 if bool(feature.get("preserve", False)) else 0))
    return counts


def _dims(part: dict[str, Any]) -> tuple[float, float, float]:
    dimensions = part["dimensions"]
    return float(dimensions["length"]), float(dimensions["width"]), float(dimensions["height"])


def _role_flags(name: str) -> list[float]:
    lower = name.lower()
    return [
        1.0 if "base" in lower else 0.0,
        1.0 if "cover" in lower else 0.0,
        1.0 if "bracket" in lower else 0.0,
        1.0 if "screw" in lower or "fastener" in lower else 0.0,
        1.0 if "pcb" in lower else 0.0,
        1.0 if "motor" in lower else 0.0,
    ]


def _one_hot(value: str, classes: list[str]) -> list[float]:
    return [1.0 if value == item else 0.0 for item in classes]


def _face_local_name(face_uid: str) -> str:
    marker = "_face_"
    if marker not in face_uid:
        raise ValueError(f"face uid does not encode local B-Rep face name: {face_uid}")
    return face_uid.rsplit(marker, 1)[1]


def _safe_face_local_name(face_uid: str) -> str:
    try:
        return _face_local_name(face_uid)
    except ValueError:
        return face_uid


def _distance(a: list[float], b: list[float]) -> float:
    return sqrt(sum((left - right) ** 2 for left, right in zip(a, b)))


def _dot(a: list[float], b: list[float]) -> float:
    return sum(left * right for left, right in zip(a, b))


def _subtract(a: list[float], b: list[float]) -> list[float]:
    return [left - right for left, right in zip(a, b)]


def _unit(vector: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise ValueError("cannot normalize zero vector")
    return [value / norm for value in vector]


def _projected_overlap_ratio(face_a: dict[str, Any], face_b: dict[str, Any]) -> float:
    centroid_distance = _distance(face_a["centroid"], face_b["centroid"])
    area_ratio = min(face_a["area"], face_b["area"]) / max(face_a["area"], face_b["area"], 1e-9)
    return max(0.0, min(1.0, area_ratio * (1.0 / (1.0 + centroid_distance / 500.0))))
