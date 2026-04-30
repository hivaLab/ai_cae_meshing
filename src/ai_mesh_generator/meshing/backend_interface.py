from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from cae_mesh_common.bdf.bdf_reader import read_bdf
from cae_mesh_common.bdf.bdf_validator import validate_bdf
from cae_mesh_common.qa.connector_quality import connector_quality_metrics
from cae_mesh_common.qa.report_writer import write_qa_html, write_qa_json
from cae_mesh_common.qa.shell_quality import shell_quality_metrics
from cae_mesh_common.qa.solid_quality import solid_quality_metrics


@dataclass
class MeshRequest:
    sample_id: str
    assembly: dict[str, Any]
    recipe: dict[str, Any]
    output_dir: Path
    backend: str = "LOCAL_PROCEDURAL"


@dataclass
class MeshResult:
    sample_id: str
    backend: str
    output_dir: Path
    bdf_path: Path
    qa_metrics_path: Path
    qa_report_path: Path
    validation_path: Path
    accepted: bool
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "backend": self.backend,
            "output_dir": str(self.output_dir),
            "bdf_path": str(self.bdf_path),
            "qa_metrics_path": str(self.qa_metrics_path),
            "qa_report_path": str(self.qa_report_path),
            "validation_path": str(self.validation_path),
            "accepted": self.accepted,
            "metrics": self.metrics,
        }


class MeshBackend(Protocol):
    def status(self) -> dict[str, Any]:
        ...

    def run(self, request: MeshRequest) -> MeshResult:
        ...


class LocalProceduralMeshingBackend:
    """Deterministic executable backend used by the delivery workflow."""

    def status(self) -> dict[str, Any]:
        return {"backend": "LOCAL_PROCEDURAL", "available": True, "mode": "deterministic"}

    def run(self, request: MeshRequest) -> MeshResult:
        output_dir = Path(request.output_dir)
        solver_dir = output_dir / "solver_deck"
        metadata_dir = output_dir / "metadata"
        report_dir = output_dir / "reports"
        solver_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)

        bdf_path = solver_dir / "model_final.bdf"
        self._write_bdf(request.assembly, request.recipe, bdf_path)
        (metadata_dir / "mesh_recipe_final.json").write_text(
            json.dumps(request.recipe, indent=2, sort_keys=True), encoding="utf-8"
        )
        mesh_summary_path = metadata_dir / "mesh_summary.json"

        validation = validate_bdf(bdf_path)
        model = read_bdf(bdf_path)
        metrics: dict[str, Any] = {
            "sample_id": request.sample_id,
            "accepted": validation.passed,
            **validation.to_dict(),
            **shell_quality_metrics(model),
            **solid_quality_metrics(model),
            **connector_quality_metrics(model),
            "failed_regions": [] if validation.passed else validation.messages,
        }
        mesh_summary_path.write_text(json.dumps({"backend": self.status(), "metrics": metrics}, indent=2), encoding="utf-8")
        qa_metrics_path = report_dir / "qa_metrics.json"
        validation_path = report_dir / "bdf_validation.json"
        qa_report_path = report_dir / "qa_report.html"
        write_qa_json(metrics, qa_metrics_path)
        write_qa_json(validation.to_dict(), validation_path)
        write_qa_html(metrics, qa_report_path)
        return MeshResult(
            sample_id=request.sample_id,
            backend="LOCAL_PROCEDURAL",
            output_dir=output_dir,
            bdf_path=bdf_path,
            qa_metrics_path=qa_metrics_path,
            qa_report_path=qa_report_path,
            validation_path=validation_path,
            accepted=validation.passed,
            metrics=metrics,
        )

    def _write_bdf(self, assembly: dict[str, Any], recipe: dict[str, Any], path: Path) -> None:
        parts = assembly["parts"]
        materials = assembly["material_library"]["materials"]
        material_ids = {material["material_id"]: index + 1 for index, material in enumerate(materials)}
        lines = ["$ Deterministic procedural Nastran BDF", "BEGIN BULK"]
        for material in materials:
            mid = material_ids[material["material_id"]]
            lines.append(f"MAT1,{mid},{material['young_modulus']},,{material['poisson_ratio']},{material['density']}")

        node_id = 1
        elem_id = 1
        prop_id = 1
        part_node_anchor: dict[str, int] = {}
        for part_index, part in enumerate(parts):
            strategy = _strategy_for_part(recipe, part["part_uid"], part.get("strategy", "shell"))
            mid = material_ids[part["material_id"]]
            length = float(part["dimensions"]["length"])
            width = float(part["dimensions"]["width"])
            height = float(part["dimensions"]["height"])
            ox = part_index * 150.0
            oy = (part_index % 3) * 35.0
            oz = (part_index % 2) * 8.0
            if strategy in {"solid", "solid_tet"}:
                nodes = [
                    (ox, oy, oz),
                    (ox + length, oy, oz),
                    (ox, oy + width, oz),
                    (ox, oy, oz + height),
                    (ox + length / 2, oy, oz),
                    (ox + length / 2, oy + width / 2, oz),
                    (ox, oy + width / 2, oz),
                    (ox, oy, oz + height / 2),
                    (ox + length / 2, oy, oz + height / 2),
                    (ox, oy + width / 2, oz + height / 2),
                ]
                ids = list(range(node_id, node_id + len(nodes)))
                for nid, coords in zip(ids, nodes):
                    lines.append(f"GRID,{nid},,{coords[0]:.4f},{coords[1]:.4f},{coords[2]:.4f}")
                lines.append(f"PSOLID,{prop_id},{mid}")
                lines.append(f"CTETRA10,{elem_id},{prop_id}," + ",".join(str(nid) for nid in ids))
                part_node_anchor[part["part_uid"]] = ids[0]
                node_id += len(nodes)
                elem_id += 1
                prop_id += 1
            elif strategy == "mass_only":
                lines.append(f"GRID,{node_id},,{ox:.4f},{oy:.4f},{oz:.4f}")
                lines.append(f"CONM2,{elem_id},{node_id},,{max(0.1, length * width * height * 1e-6):.5f}")
                part_node_anchor[part["part_uid"]] = node_id
                node_id += 1
                elem_id += 1
            else:
                nodes = [(ox, oy, oz), (ox + length, oy, oz), (ox + length, oy + width, oz), (ox, oy + width, oz)]
                ids = list(range(node_id, node_id + len(nodes)))
                for nid, coords in zip(ids, nodes):
                    lines.append(f"GRID,{nid},,{coords[0]:.4f},{coords[1]:.4f},{coords[2]:.4f}")
                thickness = max(0.5, float(part.get("nominal_thickness", 1.0)))
                lines.append(f"PSHELL,{prop_id},{mid},{thickness:.4f}")
                lines.append(f"CQUAD4,{elem_id},{prop_id}," + ",".join(str(nid) for nid in ids))
                part_node_anchor[part["part_uid"]] = ids[0]
                node_id += len(nodes)
                elem_id += 1
                prop_id += 1

        lines.append(f"PBUSH,{prop_id},{next(iter(material_ids.values()))}")
        connector_pid = prop_id
        prop_id += 1
        for connection in assembly.get("connections", []):
            a = part_node_anchor.get(connection["part_uid_a"])
            b = part_node_anchor.get(connection["part_uid_b"])
            if a and b:
                lines.append(f"CBUSH,{elem_id},{connector_pid},{a},{b}")
                elem_id += 1

        lines.extend(["ENDDATA", ""])
        path.write_text("\n".join(lines), encoding="utf-8")


def _strategy_for_part(recipe: dict[str, Any], part_uid: str, default: str) -> str:
    for item in recipe.get("part_strategies", []):
        if item.get("part_uid") == part_uid:
            return str(item.get("strategy", default))
    return default
