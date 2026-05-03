# NEXT_AGENT_PROMPT.md

This is the rolling handoff prompt for the next coding session. Update it at the end of every completed task together with `docs/STATUS.md` and `docs/TASKS.md`.

```text
You are implementing the AMG/CDF project from the repository documents.

First, read these files in order:
1. AGENT.md
2. STATUS.md
3. TASKS.md
4. CONTRACTS.md
5. ARCHITECTURE.md
6. TESTING.md
7. AMG.md
8. CDF.md
9. DATASET.md

Current state:
- P0_BOOTSTRAP_CONTRACTS_AND_RULES is complete.
- T-101_CDF_DOMAIN_MODELS is complete.
- T-102_CDF_MANIFEST_WRITER is complete.
- T-103_CDF_AUX_LABEL_WRITERS is complete.
- T-104_CDF_SAMPLE_WRITER is complete.
- T-201_FLAT_PANEL_GENERATOR is complete.
- T-202_BENT_PART_GENERATORS is complete.
- T-203_FEATURE_PLACEMENT_SAMPLER is complete.
- T-301_BREP_GRAPH_EXTRACTOR is complete.
- T-302_FEATURE_CANDIDATE_DETECTOR is complete.
- T-303_TRUTH_MATCHING_REPORT is complete.
- T-401_ANSA_COMMAND_RUNNER is complete.
- T-402_ANSA_INTERNAL_SCRIPT_SKELETON is complete.
- T-403_ANSA_REPORT_PARSER is complete.
- T-501_AMG_INPUT_VALIDATION is complete.
- T-502_AMG_DETERMINISTIC_MANIFEST is complete.
- T-503_AMG_ANSA_ADAPTER_INTERFACE is complete.
- Latest required test command: python -m pytest

Next task:
- T-601_DATASET_LOADER

Work only on T-601_DATASET_LOADER scope:
- Add an AMG-side dataset loader that reads CDF sample directories through file contracts only.
- Load graph/brep_graph.npz, graph/graph_schema.json, and labels/amg_manifest.json.
- Validate schema versions before returning sample records.
- Build model-ready sample objects without importing cad_dataset_factory.
- Ensure cad/reference_midsurface.step is not used as a model input.

Do not implement in this session:
- AMG model architecture, training loop, or inference.
- Real ANSA execution or real ANSA API binding.
- New B-rep feature detection, truth matching, or CDF generation heuristics.
- Full dataset generation at scale.
- Any graph target_action_id or target numeric control columns.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep AMG source independent from CDF package imports; communicate through contract files only.
- Keep ANSA API imports confined to ansa_scripts directories.
- Reuse AMG_BREP_GRAPH_SM_V1 and AMG_MANIFEST_SM_V1 contracts.
- Run python -m pytest before finishing.
- Update docs/STATUS.md, docs/TASKS.md, and docs/NEXT_AGENT_PROMPT.md with completed work, tests run, and the next task.

Known risks:
- ANSA executable path is not configured in this environment; real ANSA tests remain deferred to requires_ansa.
- T-503 provides only the AMG-side adapter boundary and deterministic mock, not real ANSA binding.

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, CONTRACTS.md, and DATASET.md conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. next recommended task
5. any blockers or risks
```

## Expected next-session output

```text
- T-601 AMG dataset loader is implemented or explicitly blocked.
- Loader reads graph/brep_graph.npz, graph/graph_schema.json, and labels/amg_manifest.json.
- Schema versions are checked.
- reference_midsurface.step is not used as model input.
- Existing P0-P6 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
