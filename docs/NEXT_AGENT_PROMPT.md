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
- Latest required test command: python -m pytest

Next task:
- T-503_AMG_ANSA_ADAPTER_INTERFACE

Work only on T-503_AMG_ANSA_ADAPTER_INTERFACE scope:
- Create the AMG-side AnsaAdapter interface and manifest runner skeleton.
- Map AMG_MANIFEST_SM_V1 feature actions to adapter operation requests without importing ANSA APIs outside ansa_scripts.
- Provide a mock adapter that can simulate success and failure deterministically.
- Add unit tests for adapter operation mapping, dry-run behavior, failure propagation, and retry policy skeleton behavior.
- Keep AMG code independent from cad_dataset_factory package imports.

Do not implement in this session:
- Real ANSA execution or real ANSA API binding.
- AMG model training or inference.
- Full dataset generation at scale.
- New B-rep feature detection, truth matching, or CDF generation heuristics.
- Quality threshold retuning or retry execution against real solver output.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep AMG source independent from CDF package imports; communicate through contract files only.
- Keep ANSA API imports confined to ansa_scripts directories.
- Do not add graph target_action_id or target numeric control columns.
- Keep CadQuery/OCP as optional cad dependency, not a core hard dependency.
- Reuse AMG_MANIFEST_SM_V1 and existing AMG config contracts.
- Run python -m pytest before finishing.
- Update docs/STATUS.md, docs/TASKS.md, and docs/NEXT_AGENT_PROMPT.md with completed work, tests run, and the next task.

Known risks:
- ANSA executable path is not configured in this environment; real ANSA tests remain deferred to requires_ansa.
- T-502 BEND controls use deterministic thickness_mm fallback when candidate metadata lacks true bend inner radius.

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
- T-503 AMG ANSA adapter interface is implemented or explicitly blocked.
- Manifest feature actions map to adapter operations through a tested AMG-side interface.
- Mock adapter success/failure and retry policy skeleton behavior are covered by tests.
- Existing P0-P5 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
