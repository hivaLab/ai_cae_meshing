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
- Latest required test command: python -m pytest

Next task:
- T-303_TRUTH_MATCHING_REPORT

Work only on T-303_TRUTH_MATCHING_REPORT scope:
- Match CDF feature truth records to T-302 detected feature candidates by stable geometry signatures and geometry tolerances.
- Produce a feature_matching_report.json writer for generated smoke samples.
- Report matched, unmatched_truth, unmatched_detected, recall_by_type, and false_match_count.
- Require 100% truth recall and 0 false matches for accepted generated smoke samples used in tests.
- Keep truth matching as a CDF-side reporting layer; do not make it an AMG training or inference path.

Do not implement in this session:
- Real ANSA execution.
- AMG model training or inference.
- ANSA oracle command runner or ANSA internal scripts.
- Full dataset generation at scale.
- New feature candidate detection heuristics beyond small fixes needed for matching tests.
- Dataset-scale random generation beyond existing T-203 placement primitives.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep ANSA API imports confined to ansa_scripts directories.
- Do not add graph target_action_id or target numeric control columns.
- Keep CadQuery/OCP as optional cad dependency, not a core hard dependency.
- Reuse T-301 graph extraction and T-302 candidate detection APIs.
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
- T-303 truth matching report is implemented or explicitly blocked.
- Generated flat-panel and bent-part smoke samples reach 100% truth recall with 0 false matches.
- feature_matching_report.json is JSON-compatible and schema-valid if an existing contract exists.
- Existing P0/P1/P2 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
