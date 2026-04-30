from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    port_uid: str
    part_uid: str
    kind: str
    location: tuple[float, float, float]
    normal: tuple[float, float, float]
