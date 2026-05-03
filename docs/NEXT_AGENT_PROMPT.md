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
- T-705_AMG_REAL_INFERENCE_TO_ANSA_MESH is complete.
- Latest full regression: python -m pytest -> 195 passed, 1 skipped in 7.87s.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Real accepted CDF dataset:
- runs\pilot_cdf_100
- 100 accepted samples
- strict validation:
  python -m cad_dataset_factory.cdf.cli validate --dataset runs\pilot_cdf_100 --require-ansa
  -> SUCCESS, accepted_count=100, error_count=0

Real AMG training pilot:
- checkpoint: runs\amg_training_real_pilot\checkpoint.pt
- metrics: runs\amg_training_real_pilot\metrics.json
- sample_count=100
- candidate_count=100
- manifest_feature_count=100
- matched_target_count=100
- label_coverage_ratio=1.0
- train_sample_count=80
- validation_sample_count=20

Real AMG inference pilot:
- command:
  python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\pilot_cdf_100 --checkpoint runs\amg_training_real_pilot\checkpoint.pt --out runs\amg_inference_real_pilot --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --limit 20
- result: SUCCESS
- inference summary: runs\amg_inference_real_pilot\inference_summary.json
- held-out subset: sample_000081 through sample_000100
- attempted_count=20
- success_count=20
- failed_count=0
- retry_count=0
- all successful samples have real ANSA_v25.1.0 reports, accepted=true execution/quality reports, num_hard_failed_elements=0, and non-empty BDF meshes.

Important limitation:
- The current real dataset and inference proof are a pilot distribution dominated by SM_FLAT_PANEL with one HOLE_UNKNOWN candidate per sample.
- Do not overclaim production generalization from this pilot.

Next task:
- T-706_REAL_PIPELINE_SCALE_UP_AND_GENERALIZATION_BENCHMARK

Work only on T-706 scope:
- Broaden the real pipeline beyond the current flat-panel single-hole pilot.
- Generate or curate a larger real ANSA-accepted dataset with mixed part families and feature types.
- Train AMG on the expanded real accepted manifest labels.
- Run AMG inference on an unseen held-out set through real ANSA.
- Report first-pass VALID_MESH rate, retry success rate, MESH_FAILED/OUT_OF_SCOPE reasons, hard failed element counts, and mesh artifact paths.
- Do not count mocks, placeholders, disabled ANSA paths, controlled failures, deterministic rule fallback, or synthetic graph targets as success.
- Do not import `cad_dataset_factory` from AMG source.
- Do not add target_action_id or target numeric control columns to graph inputs.
- Do not use `cad/reference_midsurface.step` as a model input.

Recommended implementation direction:
1. Inspect the pilot coverage in `runs\pilot_cdf_100` and quantify part_class, feature type, role, action, and candidate-count histograms.
2. Decide the minimum expanded benchmark target from existing CDF capabilities:
   - at least multiple part classes if current ANSA binding can mesh them reliably
   - at least HOLE/SLOT/CUTOUT where candidate detection and truth matching are already implemented
   - record any blocked BEND/FLANGE path with exact ANSA or detector failure evidence
3. Generate the expanded real CDF dataset fail-closed.
4. Strictly validate every accepted sample with real ANSA evidence.
5. Train AMG on the expanded dataset using manifest labels only.
6. Run real AMG inference on an unseen held-out subset.
7. Store a reproducible benchmark report under `runs\...` and update STATUS/TASKS/NEXT_AGENT_PROMPT with exact counts and blockers.

Acceptance for T-706:
- The benchmark report includes dataset size, accepted/rejected counts, part/feature/action coverage, train/validation/test split counts, AMG label coverage, training metrics, inference attempted/success/failed counts, retry counts, and failure reason histogram.
- Every counted successful inference output has real ANSA execution/quality reports accepted=true, num_hard_failed_elements=0, and a non-empty BDF mesh.
- Any unsupported family or feature path is explicit BLOCKED/FAILED evidence, not silently skipped.
- python -m pytest passes.

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, CONTRACTS.md, DATASET.md, or real ANSA output semantics conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. dataset generation command/result
5. training command/result
6. inference command/result
7. coverage and real mesh quality metrics
8. next recommended task
9. blockers or risks
```

## Expected next-session output

```text
- T-706 is DONE only if the expanded real-pipeline benchmark runs through real ANSA and records coverage/generalization metrics.
- Otherwise T-706 remains IN_PROGRESS or BLOCKED with exact generation, training, inference, ANSA, or quality failure reasons.
- python -m pytest passes.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md remain aligned with the next unblocked real-pipeline task.
```
