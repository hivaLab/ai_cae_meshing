from __future__ import annotations


def edge_labels(part: dict) -> list[dict]:
    return [
        {"edge_uid": f"{part['part_uid']}_edge_{index}", "semantic": "feature_edge" if index % 2 else "boundary_edge"}
        for index in range(4)
    ]
