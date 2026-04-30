from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_mesh_generator.output.result_packager import validate_result_package
from ai_mesh_generator.workflow.run_mesh_job import run_mesh_job
from ai_mesh_generator.meshing.ansa_runner import AnsaCommandBackend
from cae_mesh_common.cad.step_io import cad_kernel_status
from cae_mesh_common.schema.validators import validate_all_repository_schemas
from cae_mesh_common.graph.hetero_graph import load_graph
from cae_dataset_factory.dataset.dataset_validator import validate_dataset
from cae_dataset_factory.workflow.build_dataset import build_dataset
from training_pipeline.evaluate import evaluate_model
from training_pipeline.export_model import export_model
from training_pipeline.train import train_model


def main() -> int:
    output_root = ROOT / "runs" / "full_delivery"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    command_log: list[str] = []
    schema_results = validate_all_repository_schemas()
    command_log.append("validate_all_repository_schemas")
    cad_status = cad_kernel_status()
    command_log.append("cad kernel status")

    dataset_dir = output_root / "CAE_MESH_DATASET_V001"
    dataset_result = build_dataset(
        ROOT / "configs" / "cdf" / "base_indoor_generation_v001.yaml",
        dataset_dir,
        num_samples=1000,
        force=True,
    )
    command_log.append("cdf generate --num-samples 1000")

    dataset_validation = validate_dataset(dataset_dir)
    command_log.append("cdf validate-dataset")

    # Graphs are generated during sample writing; this step validates/reuses them.
    graph_validation = validate_graph_artifacts(dataset_dir)
    command_log.append("cdf build-graphs")

    model_dir = output_root / "artifacts" / "models" / "brep_assembly_net_v001"
    training = train_model(ROOT / "configs" / "training" / "brep_assembly_net.yaml", dataset_dir, model_dir)
    command_log.append("train-brep-assembly-net")

    eval_dir = output_root / "reports" / "model_eval_test"
    evaluation = evaluate_model(model_dir / "model.pt", dataset_dir, "test", eval_dir)
    command_log.append("evaluate-brep-assembly-net --split test")

    exported_model = export_model(model_dir / "model.pt", output_root / "artifacts" / "models" / "amg_deployment_model.pt")
    command_log.append("export-amg-model")

    test_sample_id = (dataset_dir / "splits" / "test.txt").read_text(encoding="utf-8").splitlines()[0]
    index_rows = json.loads(dataset_result_to_json(dataset_dir))
    test_row = next(row for row in index_rows if row["sample_id"] == test_sample_id)
    amg_output = output_root / "MESH_RESULT.zip"
    amg_summary = run_mesh_job(test_row["input_zip"], exported_model, amg_output, backend="LOCAL_PROCEDURAL")
    command_log.append("amg run-mesh")

    amg_validation = validate_result_package(amg_output)
    command_log.append("amg validate-result")
    ansa_status = AnsaCommandBackend().status()
    command_log.append("ansa backend status")
    ansa_probe = {"attempted": False, "passed": False, "reason": "ANSA backend is not available"}
    if ansa_status["available"]:
        ansa_output = output_root / "ANSA_MESH_RESULT.zip"
        try:
            ansa_summary = run_mesh_job(test_row["input_zip"], exported_model, ansa_output, backend="ANSA_BATCH")
            ansa_validation = validate_result_package(ansa_output)
            ansa_manifest = ansa_summary["mesh_result"]["metrics"].get("ansa_manifest", {})
            ansa_probe = {
                "attempted": True,
                "passed": bool(ansa_validation["passed"]),
                "result_package": str(ansa_output),
                "summary": ansa_summary,
                "validation": ansa_validation,
                "batch_meshing_manager_invoked": bool(ansa_manifest.get("batch_meshing_manager_invoked", False)),
                "batch_meshing_manager_reason": ansa_manifest.get("batch_meshing_manager_reason", ""),
                "ansa_import_counts": ansa_manifest.get("ansa_import_counts", {}),
                "ansa_batch_counts": ansa_manifest.get("ansa_batch_counts", {}),
                "ansa_recipe_application": ansa_manifest.get("ansa_recipe_application", {}),
                "solver_deck_recipe_application": ansa_manifest.get("solver_deck_recipe_application", {}),
                "native_entity_generation": ansa_manifest.get("native_entity_generation", {}),
                "ansa_quality_repair_loop": ansa_manifest.get("ansa_quality_repair_loop", {}),
            }
            command_log.append("amg run-mesh --backend ANSA_BATCH")
            command_log.append("amg validate-result --backend ANSA_BATCH")
        except Exception as exc:
            ansa_probe = {
                "attempted": True,
                "passed": False,
                "error": str(exc),
                "batch_meshing_manager_invoked": False,
            }
            command_log.append("amg run-mesh --backend ANSA_BATCH failed")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_validation": schema_results,
        "cad_kernel": cad_status,
        "commands": command_log,
        "dataset": {
            "manifest": dataset_result["manifest"],
            "validation": dataset_validation.to_dict(),
            "graph_artifacts": graph_validation,
        },
        "model": {
            "path": str(model_dir / "model.pt"),
            "exported_path": str(exported_model),
            "artifact": artifact_summary(training["artifact"]),
        },
        "training": training["metrics"],
        "evaluation": evaluation,
        "amg": {
            "test_sample_id": test_sample_id,
            "summary": amg_summary,
            "validation": amg_validation,
        },
        "ansa_backend": ansa_status,
        "ansa_execution_probe": ansa_probe,
        "known_limitations": [
            "Generated assemblies are deterministic synthetic CAD solids exported through CadQuery/OCP, not OEM production CAD.",
            "ANSA backend is explicit and does not fall back to local meshing.",
        ],
        "final_acceptance_status": "accepted"
        if dataset_validation.passed
        and graph_validation["passed"]
        and amg_validation["passed"]
        and cad_status["step_ap242_brep_export"]
        and ansa_probe["attempted"]
        and ansa_probe["passed"]
        and ansa_probe.get("batch_meshing_manager_invoked", False)
        and bool(ansa_probe.get("ansa_recipe_application", {}).get("batch_mesh_sessions", {}).get("session_count", 0))
        and int(ansa_probe.get("ansa_batch_counts", {}).get("SOLID", 0)) > 0
        and int(ansa_probe.get("ansa_batch_counts", {}).get("CBUSH", 0)) > 0
        and int(ansa_probe.get("ansa_batch_counts", {}).get("CONM2", 0)) > 0
        and int(ansa_probe.get("native_entity_generation", {}).get("solid_tetra", {}).get("created_count", 0)) > 0
        and int(ansa_probe.get("native_entity_generation", {}).get("connectors", {}).get("created_count", 0)) > 0
        and int(ansa_probe.get("native_entity_generation", {}).get("masses", {}).get("created_count", 0)) > 0
        else "failed",
    }
    final_report = ROOT / "FINAL_DELIVERY_REPORT.md"
    final_report.write_text(render_report(report), encoding="utf-8")
    (output_root / "FINAL_DELIVERY_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    update_status(report)
    print(json.dumps({"final_report": str(final_report), "status": report["final_acceptance_status"]}, indent=2))
    return 0 if report["final_acceptance_status"] == "accepted" else 1


def dataset_result_to_json(dataset_dir: Path) -> str:
    import pandas as pd

    frame = pd.read_parquet(dataset_dir / "dataset_index.parquet")
    return frame.to_json(orient="records")


def validate_graph_artifacts(dataset_dir: Path) -> dict:
    import pandas as pd

    frame = pd.read_parquet(dataset_dir / "dataset_index.parquet")
    required_node_types = {"part", "face", "edge", "contact_candidate", "connection"}
    total = len(frame)
    missing_graph_pt = 0
    missing_brep_json = 0
    missing_assembly_json = 0
    invalid_graphs = 0
    node_type_mismatches = 0
    first_graph_summary = {}
    for _, row in frame.iterrows():
        graph_path = Path(row["graph_path"])
        brep_json = graph_path.with_name("brep_graph.json")
        assembly_json = graph_path.with_name("assembly_graph.json")
        if not graph_path.exists():
            missing_graph_pt += 1
            continue
        if not brep_json.exists():
            missing_brep_json += 1
        if not assembly_json.exists():
            missing_assembly_json += 1
        try:
            graph = load_graph(graph_path)
        except Exception:
            invalid_graphs += 1
            continue
        if set(graph.node_sets) != required_node_types:
            node_type_mismatches += 1
        if not first_graph_summary:
            first_graph_summary = {
                "sample_id": graph.sample_id,
                "node_counts": {node_type: len(nodes) for node_type, nodes in graph.node_sets.items()},
                "edge_counts": {edge_type: len(edges) for edge_type, edges in graph.edge_sets.items()},
                "format": graph.metadata.get("graph_format", ""),
            }
    return {
        "sample_count": total,
        "graph_pt_count": total - missing_graph_pt,
        "brep_graph_json_count": total - missing_brep_json,
        "assembly_graph_json_count": total - missing_assembly_json,
        "missing_graph_pt": missing_graph_pt,
        "missing_brep_graph_json": missing_brep_json,
        "missing_assembly_graph_json": missing_assembly_json,
        "invalid_graphs": invalid_graphs,
        "node_type_mismatches": node_type_mismatches,
        "first_graph_summary": first_graph_summary,
        "passed": (
            missing_graph_pt == 0
            and missing_brep_json == 0
            and missing_assembly_json == 0
            and invalid_graphs == 0
            and node_type_mismatches == 0
        ),
    }


def artifact_summary(artifact: dict) -> dict:
    return {
        "model_id": artifact["model_id"],
        "model_type": artifact["model_type"],
        "framework": artifact["framework"],
        "hidden_dim": artifact["hidden_dim"],
        "num_layers": artifact["num_layers"],
        "node_input_dims": artifact["node_input_dims"],
        "edge_type_count": len(artifact["edge_types"]),
    }


def render_report(report: dict) -> str:
    dataset = report["dataset"]["manifest"]
    validation = report["dataset"]["validation"]
    graph_artifacts = report["dataset"]["graph_artifacts"]
    training = report["training"]
    evaluation = report["evaluation"]
    amg_metrics = report["amg"]["summary"]["mesh_result"]["metrics"]
    ansa_probe = report["ansa_execution_probe"]
    recipe_application = ansa_probe.get("ansa_recipe_application", {})
    deck_application = ansa_probe.get("solver_deck_recipe_application", {})
    native_generation = ansa_probe.get("native_entity_generation", {})
    quality_repair_loop = ansa_probe.get("ansa_quality_repair_loop", {})
    batch_sessions = recipe_application.get("batch_mesh_sessions", {})
    recipe_summary = recipe_application.get("summary", {})
    ansa_metrics = ansa_probe.get("summary", {}).get("mesh_result", {}).get("metrics", {})
    cad_kernel = report["cad_kernel"]
    return "\n".join(
        [
            "# Final Delivery Report",
            "",
            f"Generated at: {report['generated_at']}",
            "",
            "## Workflow Commands",
            *[f"- {cmd}" for cmd in report["commands"]],
            "",
            "## Dataset",
            f"- CAD kernel: {cad_kernel['kernel']}",
            f"- AP242 B-Rep export available: {cad_kernel['step_ap242_brep_export']}",
            f"- Dataset ID: {dataset['dataset_id']}",
            f"- Accepted samples: {dataset['accepted_count']}",
            f"- Rejected samples: {dataset['rejected_count']}",
            f"- Splits: train {dataset['splits']['train']} / val {dataset['splits']['val']} / test {dataset['splits']['test']}",
            f"- Acceptance rate: {dataset['acceptance_rate']:.4f}",
            f"- Dataset validation passed: {validation['passed']}",
            f"- STEP AP242 B-Rep failures: {validation['step_brep_failures']}",
            f"- Graph artifact validation passed: {graph_artifacts['passed']}",
            f"- graph.pt files: {graph_artifacts['graph_pt_count']}",
            f"- brep_graph.json files: {graph_artifacts['brep_graph_json_count']}",
            f"- assembly_graph.json files: {graph_artifacts['assembly_graph_json_count']}",
            "",
            "## Model",
            f"- Model type: {report['model']['artifact']['model_type']}",
            f"- Model path: {report['model']['path']}",
            f"- Exported model path: {report['model']['exported_path']}",
            f"- Hidden dim: {report['model']['artifact']['hidden_dim']}",
            f"- Message passing layers: {report['model']['artifact']['num_layers']}",
            f"- Edge relation types: {report['model']['artifact']['edge_type_count']}",
            f"- Train MAE: {training['train_mae']:.6f}",
            f"- Val MAE: {training['val_mae']:.6f}",
            f"- Test MAE: {evaluation['mae']:.6f}",
            f"- Test RMSE: {evaluation['rmse']:.6f}",
            f"- Size MAE percent: {evaluation['size_field_mae_percent']:.6f}",
            f"- PartStrategy macro F1: {evaluation['part_strategy_macro_f1']:.6f}",
            f"- FaceSemantic mean IoU: {evaluation['face_semantic_mean_iou']:.6f}",
            f"- EdgeSemantic macro F1: {evaluation['edge_semantic_macro_f1']:.6f}",
            f"- Connection recall: {evaluation['connection_candidate_recall']:.6f}",
            f"- Failure risk recall: {evaluation['failure_risk_recall']:.6f}",
            f"- Repair top-1 accuracy: {evaluation['repair_action_top1_accuracy']:.6f}",
            "",
            "## AMG Result",
            f"- Test sample: {report['amg']['test_sample_id']}",
            f"- Result package validation passed: {report['amg']['validation']['passed']}",
            f"- BDF parse success: {amg_metrics['bdf_parse_success']}",
            f"- Missing properties: {amg_metrics['missing_property_count']}",
            f"- Missing materials: {amg_metrics['missing_material_count']}",
            f"- Shell elements: {int(amg_metrics['shell_element_count'])}",
            f"- Solid elements: {int(amg_metrics['solid_element_count'])}",
            f"- Connectors: {int(amg_metrics['connector_count'])}",
            "",
            "## ANSA Backend",
            f"- Available: {report['ansa_backend']['available']}",
            f"- Executable: {report['ansa_backend']['executable']}",
            f"- Fallback enabled: {report['ansa_backend']['fallback_enabled']}",
            f"- Execution probe attempted: {ansa_probe['attempted']}",
            f"- Execution probe passed: {ansa_probe['passed']}",
            f"- Batch Meshing Manager invoked: {ansa_probe.get('batch_meshing_manager_invoked', False)}",
            f"- Batch Meshing Manager note: {ansa_probe.get('batch_meshing_manager_reason', ansa_probe.get('reason', ''))}",
            f"- ANSA import counts: {ansa_probe.get('ansa_import_counts', {})}",
            f"- ANSA batch counts: {ansa_probe.get('ansa_batch_counts', {})}",
            f"- AI recipe batch sessions: {batch_sessions.get('session_count', 0)}",
            f"- Per-part size fields planned: {recipe_summary.get('per_part_size_field_count', 0)}",
            f"- BMM size-field sessions applied: {batch_sessions.get('session_count', 0)}",
            f"- Materials written to deck: {deck_application.get('material_cards_written', 0)}",
            f"- PSHELL properties updated: {deck_application.get('pshell_cards_updated', 0)}",
            f"- Solver-deck element fallback enabled: {deck_application.get('element_creation_enabled', False)}",
            f"- Native CTETRA solids generated: {native_generation.get('solid_tetra', {}).get('created_count', 0)}",
            f"- Native CBUSH connectors generated: {native_generation.get('connectors', {}).get('created_count', 0)}",
            f"- Native CONM2 masses generated: {native_generation.get('masses', {}).get('created_count', 0)}",
            f"- ANSA quality repair status: {quality_repair_loop.get('status', '')}",
            f"- ANSA QA repair loop records: {ansa_metrics.get('repair_iteration_count', 0)}",
            "",
            "## Known Limitations",
            *[f"- {item}" for item in report["known_limitations"]],
            "",
            f"## Final Acceptance Status\n\n{report['final_acceptance_status'].upper()}",
            "",
        ]
    )


def update_status(report: dict) -> None:
    dataset = report["dataset"]["manifest"]
    validation = report["dataset"]["validation"]
    graph_artifacts = report["dataset"]["graph_artifacts"]
    cad_kernel = report["cad_kernel"]
    ansa_probe = report["ansa_execution_probe"]
    recipe_application = ansa_probe.get("ansa_recipe_application", {})
    deck_application = ansa_probe.get("solver_deck_recipe_application", {})
    native_generation = ansa_probe.get("native_entity_generation", {})
    quality_repair_loop = ansa_probe.get("ansa_quality_repair_loop", {})
    batch_sessions = recipe_application.get("batch_mesh_sessions", {})
    recipe_summary = recipe_application.get("summary", {})
    ansa_metrics = ansa_probe.get("summary", {}).get("mesh_result", {}).get("metrics", {})
    content = "\n".join(
        [
            "# Implementation Status",
            "",
            "Source of truth: `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md`",
            "",
            "## Milestone Status",
            "",
            "- Task 01 - Shared schema and validators: completed",
            "- Task 02 - BDF validation module: completed",
            "- Task 03 - CDF part template base: completed",
            "- Task 04 - CDF assembly grammar: completed",
            "- Task 05 - Face ID mapper and AP242 B-Rep STEP export: completed",
            "- Task 06 - Graph builder: completed; tensor B-Rep/assembly graph artifacts validated",
            "- Task 07 - BRepAssemblyNet: completed; heterogeneous graph neural network artifact exported",
            "- Task 08 - AMG recipe guard: completed",
            "- Task 09 - ANSA backend interface: completed",
            "- Task 10 - AMG E2E workflow: completed",
            "- Task 11 - CDF E2E workflow: completed",
            "- Full delivery script/report: completed",
            "",
            "## Commands Executed",
            *[f"- {cmd}" for cmd in report["commands"]],
            "",
            "## Validation Results",
            f"- CAD kernel: {cad_kernel['kernel']}",
            f"- AP242 B-Rep export available: {cad_kernel['step_ap242_brep_export']}",
            f"- Dataset validation passed: {validation['passed']}",
            f"- Schema failures: {validation['schema_failures']}",
            f"- Missing artifacts: {validation['missing_artifacts']}",
            f"- STEP AP242 B-Rep failures: {validation['step_brep_failures']}",
            f"- Split mismatches: {validation['split_mismatch_count']}",
            f"- Graph artifact validation passed: {graph_artifacts['passed']}",
            f"- graph.pt files: {graph_artifacts['graph_pt_count']}",
            f"- brep_graph.json files: {graph_artifacts['brep_graph_json_count']}",
            f"- assembly_graph.json files: {graph_artifacts['assembly_graph_json_count']}",
            f"- AMG result validation passed: {report['amg']['validation']['passed']}",
            "",
            "## Generated Dataset Counts",
            f"- Accepted samples: {dataset['accepted_count']}",
            f"- Rejected samples: {dataset['rejected_count']}",
            f"- Splits: train {dataset['splits']['train']} / val {dataset['splits']['val']} / test {dataset['splits']['test']}",
            f"- Acceptance rate: {dataset['acceptance_rate']:.4f}",
            "",
            "## Model Metrics",
            f"- Model type: {report['model']['artifact']['model_type']}",
            f"- Exported model path: {report['model']['exported_path']}",
            f"- Train MAE: {report['training']['train_mae']:.6f}",
            f"- Val MAE: {report['training']['val_mae']:.6f}",
            f"- Test MAE: {report['evaluation']['mae']:.6f}",
            f"- Test RMSE: {report['evaluation']['rmse']:.6f}",
            f"- Size MAE percent: {report['evaluation']['size_field_mae_percent']:.6f}",
            f"- PartStrategy macro F1: {report['evaluation']['part_strategy_macro_f1']:.6f}",
            f"- FaceSemantic mean IoU: {report['evaluation']['face_semantic_mean_iou']:.6f}",
            f"- EdgeSemantic macro F1: {report['evaluation']['edge_semantic_macro_f1']:.6f}",
            f"- Connection recall: {report['evaluation']['connection_candidate_recall']:.6f}",
            f"- Failure risk recall: {report['evaluation']['failure_risk_recall']:.6f}",
            f"- Repair top-1 accuracy: {report['evaluation']['repair_action_top1_accuracy']:.6f}",
            "",
            "## AMG Result Metrics",
            f"- Test sample: {report['amg']['test_sample_id']}",
            f"- BDF parse success: {report['amg']['summary']['mesh_result']['metrics']['bdf_parse_success']}",
            f"- Missing property count: {report['amg']['summary']['mesh_result']['metrics']['missing_property_count']}",
            f"- Missing material count: {report['amg']['summary']['mesh_result']['metrics']['missing_material_count']}",
            "",
            "## ANSA Backend",
            f"- Available: {report['ansa_backend']['available']}",
            f"- Executable: {report['ansa_backend']['executable']}",
            f"- Fallback enabled: {report['ansa_backend']['fallback_enabled']}",
            f"- Execution probe attempted: {report['ansa_execution_probe']['attempted']}",
            f"- Execution probe passed: {report['ansa_execution_probe']['passed']}",
            f"- Batch Meshing Manager invoked: {ansa_probe.get('batch_meshing_manager_invoked', False)}",
            f"- Batch Meshing Manager note: {ansa_probe.get('batch_meshing_manager_reason', ansa_probe.get('reason', ''))}",
            f"- ANSA import counts: {ansa_probe.get('ansa_import_counts', {})}",
            f"- ANSA batch counts: {ansa_probe.get('ansa_batch_counts', {})}",
            f"- AI recipe batch sessions: {batch_sessions.get('session_count', 0)}",
            f"- Per-part size fields planned: {recipe_summary.get('per_part_size_field_count', 0)}",
            f"- BMM size-field sessions applied: {batch_sessions.get('session_count', 0)}",
            f"- Materials written to deck: {deck_application.get('material_cards_written', 0)}",
            f"- PSHELL properties updated: {deck_application.get('pshell_cards_updated', 0)}",
            f"- Solver-deck element fallback enabled: {deck_application.get('element_creation_enabled', False)}",
            f"- Native CTETRA solids generated: {native_generation.get('solid_tetra', {}).get('created_count', 0)}",
            f"- Native CBUSH connectors generated: {native_generation.get('connectors', {}).get('created_count', 0)}",
            f"- Native CONM2 masses generated: {native_generation.get('masses', {}).get('created_count', 0)}",
            f"- ANSA quality repair status: {quality_repair_loop.get('status', '')}",
            f"- ANSA QA repair loop records: {ansa_metrics.get('repair_iteration_count', 0)}",
            "",
            "## Known Limitations",
            *[f"- {item}" for item in report["known_limitations"]],
            "",
            "## Final Acceptance Status",
            "",
            report["final_acceptance_status"].upper(),
            "",
        ]
    )
    (ROOT / "IMPLEMENTATION_STATUS.md").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
