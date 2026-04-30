from __future__ import annotations

from cae_mesh_common.bdf.bdf_reader import BDFModel


def connector_quality_metrics(model: BDFModel) -> dict[str, float]:
    connector_count = sum(1 for e in model.elements.values() if e["type"] in {"RBE2", "RBE3", "CBUSH", "CONM2"})
    return {"connector_count": float(connector_count)}
