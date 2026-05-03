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
- Latest required test command: python -m pytest

Next task:
- T-202_BENT_PART_GENERATORS

Work only on T-202_BENT_PART_GENERATORS scope:
- Generate single flange, L bracket, U channel, and hat channel constant-thickness sheet-metal solids.
- Generate bend and flange truth records compatible with FeatureTruthDocument.
- Reuse the T-201 flat-panel CAD generation style, coordinate conventions, structured errors, and STEP export helpers.
- Add CadQuery smoke tests for at least one bent family when CadQuery is available.

Do not implement in this session:
- Real ANSA execution.
- AMG model training or inference.
- B-rep graph extraction beyond placeholders explicitly required by tests.
- Random feature placement sampler; this remains T-203_FEATURE_PLACEMENT_SAMPLER.
- ANSA oracle command runner or ANSA internal scripts.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep ANSA API imports confined to ansa_scripts directories.
- Do not add graph target_action_id or target numeric control columns.
- Keep CadQuery as an optional cad dependency, not a core hard dependency.
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
- T-202 bent part generator scope is implemented or explicitly blocked.
- BendTruth and FlangeTruth records are JSON-compatible.
- Existing P0/P1/T-201 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
