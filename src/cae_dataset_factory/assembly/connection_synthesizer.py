from __future__ import annotations


def synthesize_screw_connections(parts: list[dict]) -> list[dict]:
    base = parts[0]["part_uid"]
    connections: list[dict] = []
    for index, part in enumerate(parts[1:], start=1):
        if index % 2 == 0 or "screw" in part["name"] or "cover" in part["name"]:
            connections.append(
                {
                    "connection_uid": f"conn_{base}_{part['part_uid']}",
                    "type": "screw" if "screw" in part["name"] or index % 3 == 0 else "tied",
                    "part_uid_a": base,
                    "part_uid_b": part["part_uid"],
                    "preserve_hole": True,
                    "confidence": 1.0,
                }
            )
    return connections
