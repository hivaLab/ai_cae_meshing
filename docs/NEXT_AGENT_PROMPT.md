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
- Latest required test command: python -m pytest

Next task:
- T-302_FEATURE_CANDIDATE_DETECTOR

Work only on T-302_FEATURE_CANDIDATE_DETECTOR scope:
- Add deterministic feature candidate detection on top of the T-301 B-rep graph extractor.
- Detect HOLE, SLOT, CUTOUT, BEND, and FLANGE candidates where the current STEP topology and geometry helpers support it.
- Keep FEATURE_CANDIDATE output compatible with AMG_BREP_GRAPH_SM_V1 feature_candidate_columns.
- Preserve graph_schema.json target leakage protections: no target_action_id or target numeric control columns.
- Add focused tests using generated flat-panel and bent-part STEP fixtures where possible.

Do not implement in this session:
- Real ANSA execution.
- AMG model training or inference.
- ANSA oracle command runner or ANSA internal scripts.
- Full dataset generation at scale.
- Truth matching reports; leave matching to T-303_TRUTH_MATCHING_REPORT.
- Dataset-scale random generation beyond existing T-203 placement primitives.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep ANSA API imports confined to ansa_scripts directories.
- Do not add graph target_action_id or target numeric control columns.
- Keep CadQuery/OCP as optional cad dependency, not a core hard dependency.
- Reuse T-301 graph extraction and writing APIs instead of duplicating STEP import/export logic.
- Run python -m pytest before finishing.
- Update docs/STATUS.md, docs/TASKS.md, and docs/NEXT_AGENT_PROMPT.md with completed work, tests run, and the next task.

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
- T-302 feature candidate detector is implemented or explicitly blocked.
- FEATURE_CANDIDATE rows are populated deterministically where supported.
- graph_schema.json remains target-leakage free.
- Existing P0/P1/P2 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
