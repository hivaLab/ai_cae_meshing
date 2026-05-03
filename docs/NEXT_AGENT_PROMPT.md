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
- Latest required test command: python -m pytest

Next task:
- T-502_AMG_DETERMINISTIC_MANIFEST

Work only on T-502_AMG_DETERMINISTIC_MANIFEST scope:
- Generate AMG_MANIFEST_SM_V1 manifests from detected B-rep feature candidates and deterministic rules without AI model inference.
- Reuse AMG input validation outputs, AMG config, optional feature_overrides, and existing AMG label rule utilities.
- Apply feature action masks so UNKNOWN features are never suppressed.
- Apply growth-rate smoothing or bounded projection before manifest serialization.
- Keep the output manifest schema-valid.

Do not implement in this session:
- Full real ANSA oracle execution.
- AMG model training or inference.
- Full dataset generation at scale.
- New B-rep feature detection or truth matching heuristics.
- Dataset-scale random generation beyond existing T-203 placement primitives.
- ANSA adapter execution or retry policy.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep ANSA API imports confined to ansa_scripts directories.
- Do not add graph target_action_id or target numeric control columns.
- Keep CadQuery/OCP as optional cad dependency, not a core hard dependency.
- Reuse AMG_CONFIG_SM_V1, AMG_FEATURE_OVERRIDES_SM_V1, AMG_BREP_GRAPH_SM_V1, and AMG_MANIFEST_SM_V1 contracts.
- Use T-501 OUT_OF_SCOPE validation failure manifests unchanged for invalid inputs.
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
- T-502 deterministic AMG manifest generation is implemented or explicitly blocked.
- Generated manifests validate against AMG_MANIFEST_SM_V1.
- UNKNOWN features are not suppressed.
- Growth-rate smoothing or bounded projection is covered by tests.
- Existing P0/P1/P2 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
