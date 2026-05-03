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
- P0 through P6 are complete.
- T-701 through T-706 are complete.
- T-706 proved a constrained mixed real pipeline benchmark:
  - dataset: runs\t706_mixed_benchmark\dataset
  - training: runs\t706_mixed_benchmark\training
  - inference: runs\t706_mixed_benchmark\inference
  - benchmark report: runs\t706_mixed_benchmark\benchmark_report.json
- Latest full regression:
  python -m pytest -> 204 passed, 1 skipped in 8.65s.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

T-706 real evidence:
- CDF generation:
  python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t706_mixed_benchmark\dataset --count 150 --seed 706 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_mixed_benchmark_v1
  -> SUCCESS, accepted_count=150, rejected_count=1
- CDF validation:
  python -m cad_dataset_factory.cdf.cli validate --dataset runs\t706_mixed_benchmark\dataset --require-ansa
  -> SUCCESS, accepted_count=150, error_count=0
- AMG training:
  python -m ai_mesh_generator.amg.training.real --dataset runs\t706_mixed_benchmark\dataset --out runs\t706_mixed_benchmark\training --epochs 10 --batch-size 16 --seed 706
  -> SUCCESS, label_coverage_ratio=1.0, candidate_count=240, manifest_feature_count=240
- AMG inference:
  python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\t706_mixed_benchmark\dataset --checkpoint runs\t706_mixed_benchmark\training\checkpoint.pt --out runs\t706_mixed_benchmark\inference --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --split test
  -> SUCCESS, attempted_count=23, success_count=23, failed_count=0
- Benchmark report:
  python -m ai_mesh_generator.amg.benchmark.real_pipeline --dataset runs\t706_mixed_benchmark\dataset --training runs\t706_mixed_benchmark\training --inference runs\t706_mixed_benchmark\inference --out runs\t706_mixed_benchmark\benchmark_report.json
  -> SUCCESS

T-706 coverage:
- part_class histogram:
  SM_FLAT_PANEL=120
  SM_L_BRACKET=30
- feature_type histogram:
  HOLE=60
  SLOT=60
  CUTOUT=60
  BEND=30
  FLANGE=30
- splits:
  train=105
  val=22
  test=23
- after_retry_valid_mesh_rate=1.0

Important implementation note:
- AMG model `feature_type_logits` now include a strong structural prior from the graph candidate `feature_type_id` column.
- This is not a deterministic action/control fallback. AMG does not rediscover features; CDF/graph extraction supplies typed feature candidates by file contract.
- The prior prevents auxiliary feature type head noise from rejecting otherwise valid candidate-type-consistent inference.

Remaining limitation:
- T-706 covers SM_FLAT_PANEL and SM_L_BRACKET only.
- SM_SINGLE_FLANGE, SM_U_CHANNEL, and SM_HAT_CHANNEL are not yet part of a real accepted benchmark.
- Production-scale robustness is not proven by T-706.

Next task:
- T-707_REAL_PIPELINE_FAMILY_EXPANSION_AND_ROBUSTNESS

Work only on T-707 scope:
- Expand real CDF generation and benchmark probing to SM_SINGLE_FLANGE, SM_U_CHANNEL, and SM_HAT_CHANNEL.
- Include harder feature combinations only when CAD generation, B-rep candidate detection, truth matching, manifest writing, real ANSA execution, and quality acceptance all pass fail-closed gates.
- Train AMG on the expanded real accepted dataset.
- Run AMG inference on a held-out split through real ANSA.
- Produce a benchmark report with per-family VALID_MESH rate and representative failures.
- Do not count mocks, placeholders, disabled ANSA paths, controlled failures, deterministic rule fallback, skipped families, or synthetic graph targets as success.
- Do not import `cad_dataset_factory` from AMG source.
- Do not add `target_action_id` or target numeric control columns to graph inputs.
- Do not use `cad/reference_midsurface.step` as a model input.

Recommended T-707 execution plan:
1. Probe each new family independently with one real ANSA sample:
   - SM_SINGLE_FLANGE
   - SM_U_CHANNEL
   - SM_HAT_CHANNEL
2. For each probe, record whether failure is CAD generation, graph extraction, candidate detection, truth matching, manifest generation, ANSA execution, or quality.
3. Only after all required probes pass, generate an expanded accepted dataset with balanced train/val/test coverage.
4. Validate the dataset with `cdf validate --require-ansa`.
5. Train AMG on the expanded real manifest labels.
6. Run `amg-infer-real --split test` through real ANSA.
7. Build a benchmark report and update STATUS/TASKS/NEXT_AGENT_PROMPT.

Acceptance for T-707:
- Every included family has real ANSA-accepted dataset samples and held-out real ANSA inference evidence.
- Any unsupported family has explicit BLOCKED/FAILED evidence and is not silently omitted.
- The benchmark report includes per-family coverage, per-family VALID_MESH rate, retry/failure histograms, hard failed element counts, and artifact paths.
- python -m pytest passes.

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, CONTRACTS.md, DATASET.md, or real ANSA output semantics conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real generation/validation/training/inference/benchmark commands and results
5. coverage and real mesh quality metrics
6. next recommended task
7. blockers or risks
```
