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
- T-701 through T-707 are complete with real ANSA evidence.
- T-708 has been redefined from blind production-scale expansion to fast quality-aware dataset iteration.
- The T-708 code-side pass is implemented and regression-tested.
- T-708 is NOT DONE yet because the real ANSA quality-exploration smoke gate has not been executed.

Latest regression:
- python -m pytest
- Result: 223 passed, 1 skipped in 10.35s.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

T-707 real baseline evidence:
- Dataset: runs\t707_family_benchmark\dataset
- Training: runs\t707_family_benchmark\training
- Inference: runs\t707_family_benchmark\inference
- Benchmark report: runs\t707_family_benchmark\benchmark_report.json
- CDF validate --require-ansa passed with accepted_count=240 and error_count=0.
- AMG inference on test split passed with attempted_count=36, success_count=36, failed_count=0.
- Required part coverage: SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL.
- Required feature coverage: HOLE, SLOT, CUTOUT, BEND, FLANGE.

T-708 code implemented so far:
- CDF profile sm_quality_exploration_v1.
  - Uses user-controlled --count; it does not force 10,000 samples.
  - Deterministic round-robin plan over flat and bent cases.
  - Adds role/action diversity: UNKNOWN, BOLT, MOUNT, RELIEF, DRAIN, PASSAGE, STRUCTURAL.
  - Adds KEEP_WITH_WASHER and SUPPRESS-producing cases, plus existing bend/flange controls.
  - Adds dimensional variance in thickness, width, height, feature size/location/count, bend angle/radius, and flange width.
- CDF quality exploration CLI:
  - python -m cad_dataset_factory.cdf.cli quality-explore ...
  - Perturbs baseline AMG manifests and runs real ANSA per candidate.
  - Records PASSED, FAILED, BLOCKED, quality scores, mesh evidence, and manifest/report paths.
  - Does not overwrite baseline labels.
  - Missing continuous quality metrics are BLOCKED, not guessed.
- ANSA quality report enrichment:
  - Parses ANSA Batch Mesh statistics HTML for continuous proxy metrics such as shell side length spread, aspect proxy, triangles percent, and violating shell element total.
- AMG quality training:
  - python -m ai_mesh_generator.amg.training.quality ...
  - Uses graph + manifest + quality exploration by file contract only.
  - Does not import cad_dataset_factory.
  - Builds same-geometry pairwise ranking targets from quality scores.
- AMG quality benchmark:
  - python -m ai_mesh_generator.amg.benchmark.quality ...
  - Reports action/control entropy, quality score variance, pass/fail/near-fail counts, baseline improvement, and pairwise ranking accuracy.

Non-negotiable constraints:
- AMG source must not import cad_dataset_factory.
- Graph inputs must not contain target_action_id or target numeric control columns.
- cad/reference_midsurface.step must not be used as a model input.
- Mock ANSA, disabled ANSA, controlled failures, unavailable ANSA, placeholder meshes, deterministic rule fallback, skipped families, or synthetic graph targets must never count as real success.
- Data quantity is user-controlled. Do not hard-code 10,000 samples as a completion condition.
- T-708 success is based on diversity, quality-response variance, and learning signal, not raw sample count.

Immediate next task:
- Execute and analyze the T-708 real quality-exploration smoke gate.

Run these commands first:
1. Confirm clean/test baseline:
   python -m pytest
2. Generate the smoke dataset:
   python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t708_quality_exploration_smoke\dataset --count 40 --seed 708 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_quality_exploration_v1
3. Strictly validate it:
   python -m cad_dataset_factory.cdf.cli validate --dataset runs\t708_quality_exploration_smoke\dataset --require-ansa
4. Run real quality perturbations:
   python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
5. Train quality-aware ranker:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration --out runs\t708_quality_exploration_smoke\training_quality --epochs 5 --batch-size 32 --seed 708
6. Build benchmark:
   python -m ai_mesh_generator.amg.benchmark.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration --training runs\t708_quality_exploration_smoke\training_quality --out runs\t708_quality_exploration_smoke\quality_benchmark.json

T-708 DONE criteria:
- The smoke dataset has real accepted samples and cdf validate --require-ansa passes.
- quality_exploration_summary.json has blocked_count=0.
- quality_score_variance > 0.
- Both pass and fail or near-fail quality records are present.
- action_entropy_bits > 0 and control_value_variance > 0.
- validation_pairwise_accuracy > 0.50.
- amg-quality-benchmark returns status SUCCESS.

If any criterion fails:
- Keep T-708 IN_PROGRESS or BLOCKED.
- Record exact command, exit code, blocker reason, rejection histogram, representative ANSA report paths, and whether the failure is data diversity, metric extraction, ANSA quality response, or ranking-learning related.
- Do not advance to the next task.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real smoke gate commands/results
5. quality benchmark metrics
6. whether T-708 is DONE, IN_PROGRESS, or BLOCKED
7. next recommended task
8. blockers or risks
```
