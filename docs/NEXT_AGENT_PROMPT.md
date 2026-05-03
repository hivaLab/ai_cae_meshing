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
- T-601_DATASET_LOADER is complete.
- T-602_MODEL_SKELETON is complete.
- Latest required test command: python -m pytest

Next task:
- T-603_TRAINING_LOOP_SMOKE

Work only on T-603_TRAINING_LOOP_SMOKE scope:
- Add a small training-loop smoke path using synthetic mocked graph data or T-601-style sample fixtures.
- Compute losses for part class, feature type, masked feature action, log size/control values, division-like values, and quality risk without NaN.
- Verify optimizer step, checkpoint save/load, and basic metric reporting.
- Keep the training smoke fast and deterministic.

Do not implement in this session:
- Full dataset-scale training.
- Production model architecture beyond the T-602 skeleton.
- Real ANSA execution or real ANSA API binding.
- New CDF generation, B-rep detection, or truth matching heuristics.
- Graph target_action_id or target numeric control columns.
- Using cad/reference_midsurface.step as a model input.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep AMG source independent from CDF package imports; communicate through contract files only.
- Keep ANSA API imports confined to ansa_scripts directories.
- Keep Torch under the optional `model` dependency.
- Run python -m pytest before finishing.
- Update docs/STATUS.md, docs/TASKS.md, and docs/NEXT_AGENT_PROMPT.md with completed work, tests run, and the next task.

Known risks:
- ANSA executable path is not configured in this environment; real ANSA tests remain deferred to requires_ansa.
- T-602 provides only a lightweight MLP skeleton and projector boundary; full heterogeneous B-rep GNN remains future work.
- T-603 must avoid adding supervised target columns to graph inputs.

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
- T-603 AMG training-loop smoke is implemented or explicitly blocked.
- Loss computes without NaN.
- Optimizer step and checkpoint save/load work.
- Metrics are reported.
- Existing P0-P6 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
