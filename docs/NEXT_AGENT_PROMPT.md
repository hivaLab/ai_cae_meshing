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
7. ANSA_INTEGRATION.md
8. AMG.md
9. CDF.md
10. DATASET.md

Current state:
- P0_BOOTSTRAP_CONTRACTS_AND_RULES is complete.
- T-101 through T-104 are complete.
- T-201 through T-203 are complete.
- T-301 through T-303 are complete.
- T-401 through T-403 are complete.
- T-501 through T-503 are complete.
- T-601 through T-603 are complete; T-602/T-603 remain skeleton/smoke foundations only.
- T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED is complete.
- T-702_CDF_REAL_ANSA_API_BINDING is complete for ANSA v25.1.0.
- T-703_CDF_ACCEPTED_DATASET_PILOT is complete.
- T-704_AMG_REAL_DATASET_TRAINING is complete.
- Latest full regression: python -m pytest -> 186 passed, 1 skipped in 7.40s.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Real accepted CDF dataset:
- runs\pilot_cdf_100
- 100 accepted samples
- 2 rejected attempts, reason histogram: feature_truth_matching_failed=2
- strict validation command:
  python -m cad_dataset_factory.cdf.cli validate --dataset runs\pilot_cdf_100 --require-ansa
  -> SUCCESS, accepted_count=100, error_count=0

Real AMG training pilot:
- command:
  python -m ai_mesh_generator.amg.training.real --dataset runs\pilot_cdf_100 --out runs\amg_training_real_pilot --epochs 5 --batch-size 16 --seed 1
- result: SUCCESS
- checkpoint: runs\amg_training_real_pilot\checkpoint.pt
- metrics: runs\amg_training_real_pilot\metrics.json
- sample_count=100
- candidate_count=100
- manifest_feature_count=100
- matched_target_count=100
- label_coverage_ratio=1.0
- train_sample_count=80
- validation_sample_count=20
- split_source=deterministic_80_20_fallback

Next task:
- T-705_AMG_REAL_INFERENCE_TO_ANSA_MESH

Work only on T-705_AMG_REAL_INFERENCE_TO_ANSA_MESH scope:
- Load the T-704 checkpoint and run AMG inference on held-out real samples.
- Convert model outputs into schema-valid `AMG_MANIFEST_SM_V1` manifests.
- Execute the manifests through the real ANSA path and validate the resulting meshes.
- Use deterministic retry policy only for documented AMG retry cases.
- Do not count dry-run, mock adapter, disabled oracle, placeholder mesh, controlled failure, or unavailable ANSA as success.
- Do not import `cad_dataset_factory` from AMG source.
- Do not add target_action_id or target numeric control columns to graph inputs.
- Do not use `cad/reference_midsurface.step` as a model input.

Implementation targets:
1. Add an AMG inference module and CLI entrypoint, for example:
   - `ai_mesh_generator/amg/inference/real_mesh.py`
   - console script `amg-infer-real`
2. Inputs:
   - dataset root, default `runs\pilot_cdf_100`
   - checkpoint path, default `runs\amg_training_real_pilot\checkpoint.pt`
   - output root, for example `runs\amg_inference_real_pilot`
   - ANSA executable path
   - optional explicit sample ids; otherwise use the T-704 deterministic validation subset, currently last 20 accepted samples.
3. For each held-out sample:
   - load `graph/brep_graph.npz`, `graph/graph_schema.json`, and config through AMG file contracts only
   - run `AmgGraphModel`
   - apply masks and projector
   - serialize predicted controls into `AMG_MANIFEST_SM_V1`
   - validate manifest against the contract before ANSA execution
4. Execute real ANSA:
   - call the existing AMG manifest runner or CDF ANSA runner boundary, whichever matches AMG.md without importing CDF source into AMG
   - write execution report, quality report, solver deck/mesh artifact, and per-sample inference report
   - reject outputs if ANSA is unavailable, mocked, dry-run, skeleton-only, or quality report is not accepted
5. Retry:
   - implement only documented deterministic retry cases from AMG.md
   - after max attempts, write schema-valid `MESH_FAILED` result with explicit reason
6. Aggregate:
   - write `inference_summary.json` with sample count, attempted count, success count, retry count, failure reasons, hard-failed element counts, and output paths.

Acceptance for T-705:
- At least the held-out validation subset from `runs\pilot_cdf_100` is processed.
- Every successful sample has:
  - schema-valid predicted AMG manifest
  - real ANSA execution report with accepted=true
  - real ANSA quality report with accepted=true
  - num_hard_failed_elements=0
  - non-empty solver deck or mesh artifact
  - no controlled_failure_reason, unavailable, mock-ansa, dry-run, or placeholder output
- Failures are explicit `OUT_OF_SCOPE` or `MESH_FAILED` records, not silent fallbacks.
- `python -m pytest` passes.
- A real inference command completes and writes summary evidence.

Do not implement in T-705:
- new CDF dataset generation beyond small held-out artifact preparation if needed
- production heterogeneous GNN architecture redesign
- model retraining as the main success path
- target leakage columns in graph inputs
- mock success paths

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, CONTRACTS.md, DATASET.md, or real ANSA output semantics conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. inference command and result
5. dataset/checkpoint/output paths
6. number of attempted/successful/failed real ANSA inference samples
7. retry and failure reason summary
8. next recommended task
9. blockers or risks
```

## Expected next-session output

```text
- T-705 is DONE only if AMG checkpoint inference produces real ANSA quality-passing mesh outputs for held-out samples.
- Otherwise T-705 remains IN_PROGRESS or BLOCKED with exact inference, manifest, ANSA, or quality failure reasons.
- python -m pytest passes.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md remain aligned with the next unblocked real-pipeline task.
```
