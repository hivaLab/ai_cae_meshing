from __future__ import annotations


def build_assembly_edges(assembly: dict) -> list[tuple[int, int]]:
    index = {part["part_uid"]: i for i, part in enumerate(assembly["parts"])}
    return [
        (index[connection["part_uid_a"]], index[connection["part_uid_b"]])
        for connection in assembly.get("connections", [])
        if connection["part_uid_a"] in index and connection["part_uid_b"] in index
    ]
