from __future__ import annotations

from cae_mesh_common.bdf.bdf_reader import BDFModel


def mass_count(model: BDFModel) -> int:
    return sum(1 for e in model.elements.values() if e["type"] == "CONM2")
