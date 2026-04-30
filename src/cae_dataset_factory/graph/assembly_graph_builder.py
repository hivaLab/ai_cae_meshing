from __future__ import annotations


def build_assembly_edges(assembly: dict) -> list[tuple[int, int]]:
    index = {part["part_uid"]: i for i, part in enumerate(assembly["parts"])}
    edges: list[tuple[int, int]] = []
    for connection in assembly.get("connections", []):
        if connection["part_uid_a"] not in index or connection["part_uid_b"] not in index:
            raise ValueError(f"connection references unknown part: {connection}")
        a_index = index[connection["part_uid_a"]]
        b_index = index[connection["part_uid_b"]]
        edges.append((a_index, b_index))
        edges.append((b_index, a_index))
    return edges
