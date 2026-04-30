from __future__ import annotations

from cae_mesh_common.graph.hetero_graph import HeteroGraph


def build_brep_graph(assembly: dict) -> HeteroGraph:
    parts = assembly["parts"]
    face_nodes = []
    edge_nodes = []
    for part_index, part in enumerate(parts):
        for face in part.get("face_signatures", []):
            face_nodes.append(
                {
                    "uid": face["face_uid"],
                    "part_index": part_index,
                    "area": float(face["area"]),
                    "perimeter": float(face["perimeter"]),
                    "preserve": 1.0 if "top" in face["face_uid"] or "bottom" in face["face_uid"] else 0.0,
                }
            )
        for edge_index in range(4):
            edge_nodes.append({"uid": f"{part['part_uid']}_edge_{edge_index}", "part_index": part_index, "length": part["dimensions"]["length"] / 4.0})
    graph = HeteroGraph(sample_id=assembly["sample_id"])
    graph.node_sets["part"] = [
        {
            "uid": part["part_uid"],
            "strategy_hint": part["strategy"],
            "length": part["dimensions"]["length"],
            "width": part["dimensions"]["width"],
            "height": part["dimensions"]["height"],
            "thickness": part["nominal_thickness"],
        }
        for part in parts
    ]
    graph.node_sets["face"] = face_nodes
    graph.node_sets["edge"] = edge_nodes
    graph.edge_sets["part_to_face"] = [(face["part_index"], index) for index, face in enumerate(face_nodes)]
    graph.edge_sets["part_to_edge"] = [(edge["part_index"], index) for index, edge in enumerate(edge_nodes)]
    graph.graph_features = graph_feature_vector(assembly)
    return graph


def graph_feature_vector(assembly: dict) -> dict[str, float]:
    parts = assembly["parts"]
    connections = assembly.get("connections", [])
    defects = assembly.get("defects", [])
    mean_length = sum(float(part["dimensions"]["length"]) for part in parts) / len(parts)
    mean_width = sum(float(part["dimensions"]["width"]) for part in parts) / len(parts)
    mean_height = sum(float(part["dimensions"]["height"]) for part in parts) / len(parts)
    return {
        "part_count": float(len(parts)),
        "face_count": float(sum(len(part.get("face_labels", [])) for part in parts)),
        "connection_count": float(len(connections)),
        "defect_count": float(len(defects)),
        "mean_length": mean_length,
        "mean_width": mean_width,
        "mean_height": mean_height,
    }
