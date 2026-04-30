from __future__ import annotations


def build_connector_cards(connections: list[dict]) -> list[str]:
    return [f"$ connector {item['connection_uid']} {item['type']}" for item in connections]
