from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mesh_generator.cad.feature_extractor import extract_features
from ai_mesh_generator.cad.importer import import_input_assembly
from ai_mesh_generator.graph.graph_builder import build_amg_graph
from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.cad.cad_exporter import export_assembly_step
from cae_mesh_common.cad.step_io import inspect_step_brep


def run_step_ingestion_regression(output_dir: Path | str, sample_count: int = 3) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(sample_count):
        assembly = AssemblyGrammar(910_000).generate(50_000 + index)
        assembly["sample_id"] = f"golden_ap242_{index:03d}"
        job_dir = output / assembly["sample_id"] / "input_package"
        geometry_dir = job_dir / "geometry"
        metadata_dir = job_dir / "metadata"
        geometry_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        step_path = export_assembly_step(geometry_dir / "assembly.step", assembly["sample_id"], assembly["parts"])
        (metadata_dir / "assembly.json").write_text(json.dumps(assembly, indent=2, sort_keys=True), encoding="utf-8")
        imported = extract_features(import_input_assembly(job_dir))
        graph = build_amg_graph(imported)
        step_info = inspect_step_brep(step_path)
        node_counts = {node_type: len(nodes) for node_type, nodes in graph.node_sets.items()}
        edge_counts = {edge_type: len(edges) for edge_type, edges in graph.edge_sets.items()}
        passed = (
            bool(step_info["valid_step"])
            and bool(step_info["is_ap242"])
            and bool(step_info["is_brep"])
            and not bool(step_info["descriptor_only"])
            and imported["geometry_source"]["cad_kernel"] == "STEP_AP242_BREP"
            and all(count > 0 for count in node_counts.values())
        )
        records.append(
            {
                "sample_id": assembly["sample_id"],
                "step_file": str(step_path),
                "passed": passed,
                "step_validation": step_info,
                "geometry_source": imported["geometry_source"],
                "node_counts": node_counts,
                "edge_counts": edge_counts,
            }
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output.resolve()),
        "sample_count": sample_count,
        "passed_count": sum(1 for record in records if record["passed"]),
        "failed_count": sum(1 for record in records if not record["passed"]),
        "accepted": all(record["passed"] for record in records) and bool(records),
        "records": records,
        "limitation": "Golden assemblies are locally generated AP242 B-Rep STEP fixtures; no external OEM STEP files were supplied.",
    }
    (output / "STEP_INGESTION_REGRESSION_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report
