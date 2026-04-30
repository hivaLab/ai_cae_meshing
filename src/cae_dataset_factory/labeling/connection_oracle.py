from __future__ import annotations


def connection_labels(connections: list[dict]) -> list[dict]:
    return [{"connection_uid": item["connection_uid"], "type": item["type"], "keep": True} for item in connections]
