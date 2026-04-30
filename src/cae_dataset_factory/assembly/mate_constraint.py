from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MateConstraint:
    constraint_uid: str
    port_a: str
    port_b: str
    constraint_type: str = "coincident"
