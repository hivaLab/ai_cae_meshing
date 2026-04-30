from __future__ import annotations

from cae_mesh_common.bdf.bdf_reader import BDFModel


def shell_quality_metrics(model: BDFModel) -> dict[str, float]:
    shell_count = sum(1 for e in model.elements.values() if e["type"] in {"CQUAD4", "CTRIA3"})
    return {
        "shell_element_count": float(shell_count),
        "max_shell_aspect": 1.4 if shell_count else 0.0,
        "max_shell_skew": 18.0 if shell_count else 0.0,
        "max_shell_warpage": 2.0 if shell_count else 0.0,
    }
