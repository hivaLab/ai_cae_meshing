from __future__ import annotations

import random
from typing import Any

from .defect_types import SLIVER_FACE, SMALL_HOLE


def inject_defects(assembly: dict[str, Any], seed: int, defect_rate: float) -> dict[str, Any]:
    rng = random.Random(seed)
    defects = []
    for part in assembly["parts"]:
        if rng.random() < defect_rate:
            defect_type = SMALL_HOLE if rng.random() < 0.65 else SLIVER_FACE
            defects.append(
                {
                    "defect_uid": f"defect_{part['part_uid']}",
                    "part_uid": part["part_uid"],
                    "defect_type": defect_type,
                    "severity": round(rng.uniform(0.05, 0.3), 4),
                    "repair_action": "preserve_connection_hole" if defect_type == SMALL_HOLE else "local_remesh",
                }
            )
    assembly["defects"] = defects
    return assembly
