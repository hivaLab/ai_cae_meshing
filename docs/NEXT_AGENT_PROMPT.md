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
- T-601 through T-603 are complete, but T-602/T-603 are model skeleton/smoke only.
- T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED is complete.
- T-702_CDF_REAL_ANSA_API_BINDING is complete for ANSA v25.1.0.
- T-703_CDF_ACCEPTED_DATASET_PILOT is complete.
- Latest pure regression: python -m pytest -> 176 passed, 1 skipped.
- Latest real ANSA probe:
  python -m cad_dataset_factory.cdf.cli ansa-probe --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --out runs\ansa_probe\ansa_runtime_probe.json --timeout-sec 90
  -> status=OK.
- Latest real pilot dataset:
  python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\pilot_cdf_100 --count 100 --seed 1 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  -> SUCCESS, accepted_count=100, rejected_count=2, attempted_count=102, runtime_sec=1234.132632.
  python -m cad_dataset_factory.cdf.cli validate --dataset runs\pilot_cdf_100 --require-ansa
  -> SUCCESS, accepted_count=100, error_count=0.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Real accepted dataset for T-704:
- runs\pilot_cdf_100
- 100 accepted samples
- rejection_reason_counts.feature_truth_matching_failed = 2
- accepted samples have real ANSA_v25.1.0 reports, zero hard failed elements, and non-empty BDF meshes.

Next task:
- T-704_AMG_REAL_DATASET_TRAINING

Work only on T-704_AMG_REAL_DATASET_TRAINING scope:
- Train AMG on real CDF accepted samples using file contracts only.
- Use `runs\pilot_cdf_100` as the initial real pilot dataset.
- Use `labels/amg_manifest.json` as label-side supervision.
- Do not use synthetic smoke targets as the success path.
- Do not add target_action_id or target numeric control columns to graph inputs.
- Do not import `cad_dataset_factory` from AMG source.
- Do not use `cad/reference_midsurface.step` as a model input.

Implementation targets:
1. Add an AMG real-training CLI or script entrypoint that loads a dataset root through the existing AMG dataset loader.
2. Refuse to train unless `cdf validate --require-ansa`-equivalent acceptance evidence is present:
   - dataset_index accepted samples exist
   - reports/sample_acceptance.json accepted=true and accepted_by.ansa_oracle=true
   - reports/ansa_execution_report.json accepted=true
   - reports/ansa_quality_report.json accepted=true and num_hard_failed_elements=0
   - meshes/ansa_oracle_mesh.bdf exists and is non-empty
3. Build supervised targets from `labels/amg_manifest.json`, not from graph target columns:
   - part class target from manifest part class
   - feature type target from manifest feature records
   - feature action target from manifest feature action
   - numeric targets from manifest controls, bounded by mesh policy
4. Train the existing T-602 model for a small but real dataset run:
   - deterministic seed
   - train/validation split from dataset split files or deterministic fallback if split is empty
   - checkpoint save/load
   - metrics JSON with per-head losses and label coverage
5. The run is a real training pilot, not production-scale convergence. Completion requires loss/metrics/checkpoint over real accepted labels.

Acceptance for T-704:
- Training command completes on `runs\pilot_cdf_100`.
- Checkpoint is written.
- metrics JSON records sample count, candidate count, manifest-label coverage, train/validation losses, and refusal status for invalid datasets.
- Training refuses a dataset without real ANSA-accepted samples.
- `python -m pytest` passes.
- Any new model/training tests use real-manifest-style fixtures and do not rely on synthetic target columns.

Do not implement in T-704:
- AMG inference-to-ANSA mesh; that is T-705.
- Production heterogeneous B-rep GNN architecture beyond the current model skeleton unless directly required to train.
- CDF generation changes except small validation/evidence fixes if a loader invariant exposes a bug.
- New ANSA execution logic.

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, CONTRACTS.md, DATASET.md, or the real pilot dataset evidence conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. training command and result
5. dataset path, sample count, and label coverage
6. checkpoint and metrics paths
7. next recommended task
8. blockers or risks
```

## Expected next-session output

```text
- T-704 is DONE only if AMG trains on real accepted CDF labels from runs\pilot_cdf_100 and writes checkpoint/metrics.
- Otherwise T-704 remains IN_PROGRESS or BLOCKED with exact dataset/model/training failure reasons.
- python -m pytest passes.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md remain aligned with T-705_AMG_REAL_INFERENCE_TO_ANSA_MESH or the next unblocked real-training task.
```
