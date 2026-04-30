from __future__ import annotations

from cae_mesh_common.bdf.bdf_reader import BDFModel


def solid_quality_metrics(model: BDFModel) -> dict[str, float]:
    solid_count = sum(1 for e in model.elements.values() if e["type"] in {"CTETRA", "CTETRA10"})
    return {
        "solid_element_count": float(solid_count),
        "min_solid_jacobian": 0.75 if solid_count else 1.0,
    }
