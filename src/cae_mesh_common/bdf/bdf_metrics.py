from __future__ import annotations

from .bdf_reader import BDFModel


def element_type_counts(model: BDFModel) -> dict[str, int]:
    counts: dict[str, int] = {}
    for element in model.elements.values():
        etype = str(element["type"])
        counts[etype] = counts.get(etype, 0) + 1
    return counts
