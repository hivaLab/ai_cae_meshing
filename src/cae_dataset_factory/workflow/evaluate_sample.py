from __future__ import annotations


def is_accepted(row: dict) -> bool:
    return bool(row.get("accepted", False))
