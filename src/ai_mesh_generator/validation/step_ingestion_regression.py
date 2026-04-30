from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mesh_generator.cad.feature_extractor import extract_features
from ai_mesh_generator.cad.importer import import_input_assembly, write_step_input_package
from ai_mesh_generator.graph.graph_builder import build_amg_graph
from ai_mesh_generator.input.validator import validate_input_package_dir
from cae_dataset_factory.assembly.assembly_grammar import AssemblyGrammar
from cae_dataset_factory.cad.cad_exporter import export_assembly_step
from cae_mesh_common.cad.step_io import inspect_step_brep


def run_step_ingestion_regression(
    output_dir: Path | str,
    sample_count: int = 5,
    cad_dir: Path | str | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    sources = _step_sources(output, sample_count, cad_dir)
    for source in sources:
        sample_id = f"{source['sample_id']}"
        job_dir, packaged_assembly = write_step_input_package(source["step_file"], output / sample_id / "input_package", sample_id)
        package_validation = validate_input_package_dir(job_dir)
        imported = extract_features(import_input_assembly(job_dir))
        graph = build_amg_graph(imported)
        step_info = inspect_step_brep(Path(job_dir) / "geometry" / "assembly.step")
        node_counts = {node_type: len(nodes) for node_type, nodes in graph.node_sets.items()}
        edge_counts = {edge_type: len(edges) for edge_type, edges in graph.edge_sets.items()}
        traceability = _traceability_summary(imported, packaged_assembly)
        passed = (
            bool(package_validation["valid"])
            and bool(step_info["valid_step"])
            and bool(step_info["is_ap242"])
            and bool(step_info["is_brep"])
            and not bool(step_info["descriptor_only"])
            and imported["geometry_source"]["cad_kernel"] == "STEP_AP242_BREP_OCP"
            and imported.get("topology_traceability", {}).get("source") == "STEP_AP242_BREP_OCP"
            and all(count > 0 for count in node_counts.values())
            and traceability["passed"]
        )
        records.append(
            {
                "sample_id": sample_id,
                "source": source["source"],
                "step_file": str(Path(job_dir) / "geometry" / "assembly.step"),
                "input_package": str(job_dir),
                "passed": passed,
                "package_validation": package_validation,
                "step_validation": step_info,
                "geometry_source": imported["geometry_source"],
                "topology_traceability": traceability,
                "node_counts": node_counts,
                "edge_counts": edge_counts,
            }
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output.resolve()),
        "sample_count": sample_count,
        "cad_dir": str(Path(cad_dir).resolve()) if cad_dir else None,
        "source_count": len(sources),
        "passed_count": sum(1 for record in records if record["passed"]),
        "failed_count": sum(1 for record in records if not record["passed"]),
        "accepted": all(record["passed"] for record in records) and bool(records),
        "records": records,
        "limitation": _limitation(cad_dir),
    }
    (output / "STEP_INGESTION_REGRESSION_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "STEP_INGESTION_REGRESSION_REPORT.md").write_text(render_step_ingestion_report(report), encoding="utf-8")
    return report


def render_step_ingestion_report(report: dict[str, Any]) -> str:
    lines = [
        "# STEP Ingestion Regression Report",
        "",
        f"Generated at: {report['generated_at']}",
        f"Output directory: {report['output_dir']}",
        f"CAD directory: {report['cad_dir']}",
        f"Sample count: {report['source_count']}",
        f"Passed: {report['passed_count']}",
        f"Failed: {report['failed_count']}",
        f"Acceptance: {'ACCEPTED' if report['accepted'] else 'FAILED'}",
        f"Limitation: {report['limitation']}",
        "",
        "| sample_id | source | passed | parts | faces | edges | contacts | connections | traceability |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in report["records"]:
        nodes = record["node_counts"]
        traceability = record["topology_traceability"]
        lines.append(
            "| {sample_id} | {source} | {passed} | {parts} | {faces} | {edges} | {contacts} | {connections} | {traceability} |".format(
                sample_id=record["sample_id"],
                source=record["source"],
                passed=record["passed"],
                parts=nodes.get("part", 0),
                faces=nodes.get("face", 0),
                edges=nodes.get("edge", 0),
                contacts=nodes.get("contact_candidate", 0),
                connections=nodes.get("connection", 0),
                traceability=traceability.get("passed", False),
            )
        )
    return "\n".join(lines) + "\n"


def _step_sources(output: Path, sample_count: int, cad_dir: Path | str | None) -> list[dict[str, Any]]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if cad_dir:
        root = Path(cad_dir)
        files = sorted([*root.glob("*.step"), *root.glob("*.stp"), *root.glob("*.STEP"), *root.glob("*.STP")])
        if len(files) < sample_count:
            raise FileNotFoundError(f"CAD directory {root} contains {len(files)} STEP files, requested {sample_count}")
        return [
            {"sample_id": f"external_step_{index:03d}_{path.stem}", "step_file": path, "source": "external_cad_dir"}
            for index, path in enumerate(files[:sample_count])
        ]
    source_dir = output / "golden_step_fixtures"
    source_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for index in range(sample_count):
        assembly = AssemblyGrammar(910_000).generate(50_000 + index)
        sample_id = f"golden_ap242_{index:03d}"
        assembly["sample_id"] = sample_id
        step_path = export_assembly_step(source_dir / f"{sample_id}.step", sample_id, assembly["parts"])
        sources.append({"sample_id": sample_id, "step_file": step_path, "source": "local_golden_ap242_fixture"})
    return sources


def _traceability_summary(imported: dict[str, Any], packaged: dict[str, Any]) -> dict[str, Any]:
    parts = imported.get("parts", [])
    source_products = [part.get("source_product_name") for part in parts]
    source_indices = [part.get("source_solid_index") for part in parts]
    graph_ready = all(part.get("topology_source") == "STEP_AP242_BREP_OCP" for part in parts)
    product_unique = len([name for name in source_products if name]) == len(set(source_products)) == len(parts)
    index_unique = len([idx for idx in source_indices if idx is not None]) == len(set(source_indices)) == len(parts)
    topology = imported.get("topology_traceability", {})
    return {
        "passed": bool(graph_ready and product_unique and index_unique and topology.get("solid_count") == len(parts)),
        "part_count": len(parts),
        "source_product_names": source_products,
        "source_solid_indices": source_indices,
        "graph_ready_topology": graph_ready,
        "unique_product_names": product_unique,
        "unique_solid_indices": index_unique,
        "packaged_part_count": len(packaged.get("parts", [])),
    }


def _limitation(cad_dir: Path | str | None) -> str:
    if cad_dir:
        return "External STEP files were supplied by --cad-dir; production acceptance still depends on ANSA/license availability."
    return "Golden assemblies are locally generated AP242 B-Rep STEP fixtures; no external OEM STEP files were supplied."
