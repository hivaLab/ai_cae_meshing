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
- T-603_TRAINING_LOOP_SMOKE is complete.
- T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED has fail-closed CLI code implemented, but is BLOCKED for DONE status because the real ANSA accepted-sample gate cannot run in this environment.
- Latest required test command: python -m pytest

Next task:
- T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED

Work only on T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED scope:
- Do not mark T-701 DONE until the requires_ansa gate creates real accepted samples.
- Re-run `cdf generate --config configs/cdf_sm_ansa_v1.default.json --out runs/e2e_cdf --count 1 --seed 1 --require-ansa` only after ANSA_EXECUTABLE and license are available.
- If the run still produces controlled-failure reports from the skeleton ANSA API layer, keep T-701 BLOCKED and proceed only after assigning/implementing T-702_CDF_REAL_ANSA_API_BINDING.
- Keep `cdf validate --dataset ... --require-ansa` strict: accepted samples must have real execution/quality reports and a non-placeholder `meshes/ansa_oracle_mesh.bdf`.

Do not implement in this session:
- Full dataset-scale training.
- Production model architecture beyond the T-602 skeleton.
- Real ANSA internal API binding beyond the existing runner boundary; that is T-702 unless T-701 discovers it is a hard blocker.
- New CDF generation, B-rep detection, or truth matching heuristics.
- Graph target_action_id or target numeric control columns.
- Using cad/reference_midsurface.step as a model input.
- Mock, disabled-oracle, or placeholder accepted samples.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep AMG source independent from CDF package imports; communicate through contract files only.
- Keep ANSA API imports confined to ansa_scripts directories.
- Keep Torch under the optional `model` dependency.
- Run python -m pytest before finishing.
- Update docs/STATUS.md, docs/TASKS.md, and docs/NEXT_AGENT_PROMPT.md with completed work, tests run, and the next task.

Known risks:
- ANSA executable path is not configured in this environment. T-701 code is implemented but real accepted-sample completion is BLOCKED until ANSA is configured.
- T-602 provides only a lightweight MLP skeleton and projector boundary; full heterogeneous B-rep GNN remains future work.
- T-603 is only a smoke loop with synthetic targets derived from candidate rows and masks; it is not production training.
- Real ANSA API binding is still a skeleton; T-702 is expected after T-701.

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
- T-701 remains BLOCKED or is promoted to DONE only after real ANSA accepted samples are generated and validated.
- Accepted samples are never counted from mock/disabled oracle paths.
- `python -m pytest` passes.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md remain aligned with the next real-pipeline task.
```
