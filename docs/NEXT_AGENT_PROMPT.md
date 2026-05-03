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
- Latest required test command: python -m pytest

Next task:
- T-301_BREP_GRAPH_EXTRACTOR

Work only on T-301_BREP_GRAPH_EXTRACTOR scope:
- Extract an AMG_BREP_GRAPH_SM_V1-compatible graph from STEP inputs.
- Produce graph/brep_graph.npz and graph/graph_schema.json with stable node/edge feature column order.
- Include PART, FACE, EDGE, COEDGE, VERTEX, and FEATURE_CANDIDATE graph entities where available.
- Validate coedge cycles and adjacency arrays structurally.

Do not implement in this session:
- Real ANSA execution.
- AMG model training or inference.
- ANSA oracle command runner or ANSA internal scripts.
- Full dataset generation at scale.
- Truth matching report logic beyond minimal graph extraction tests.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep ANSA API imports confined to ansa_scripts directories.
- Do not add graph target_action_id or target numeric control columns.
- Keep CadQuery/OCP as optional cad dependency, not a core hard dependency.
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
- T-301 B-rep graph extractor is implemented or explicitly blocked.
- graph_schema.json has required node/edge columns and no target leakage columns.
- brep_graph.npz stores structurally valid adjacency arrays.
- Existing P0/P1/P2 tests continue to pass.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md are updated for the following task.
```
