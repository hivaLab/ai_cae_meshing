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
- T-708_FAST_QUALITY_AWARE_DATASET_ITERATION is IN_PROGRESS.
- The T-708 code-side pass was implemented and committed.
- The T-708 real smoke gate was executed, and it failed correctly. Do not mark T-708 DONE yet.

Latest verification:
- python -m pytest
- Result: 224 passed, 1 skipped in 10.43s.

Recent code baseline:
- Commit 517584b added the quality-aware dataset iteration pipeline.
- The follow-up commit records the real T-708 gate blocker and hardens the quality benchmark against geometry-only variance.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

T-708 real smoke gate evidence:
1. Dataset generation:
   python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t708_quality_exploration_smoke\dataset --count 40 --seed 708 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_quality_exploration_v1
   Result: SUCCESS, accepted_count=40, rejected_count=2.

2. Dataset validation:
   python -m cad_dataset_factory.cdf.cli validate --dataset runs\t708_quality_exploration_smoke\dataset --require-ansa
   Result: SUCCESS, accepted_count=40, error_count=0.

3. Quality exploration:
   python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   Result: SUCCESS, baseline_count=40, evaluated_count=120, blocked_count=0, passed_count=160, failed_count=0, quality_score_variance=9231610.37480431.

4. Quality ranker training:
   python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration --out runs\t708_quality_exploration_smoke\training_quality --epochs 5 --batch-size 32 --seed 708
   Result: SUCCESS, validation_pairwise_accuracy=0.6785714285714286.

5. Quality benchmark:
   python -m ai_mesh_generator.amg.benchmark.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration --training runs\t708_quality_exploration_smoke\training_quality --out runs\t708_quality_exploration_smoke\quality_benchmark.json
   Result: FAILED.
   Failed criteria:
     has_pass_and_fail_or_near_fail_examples=false
     same_geometry_quality_delta_meaningful=false

Important quality evidence:
- quality benchmark: runs\t708_quality_exploration_smoke\quality_benchmark.json
- quality exploration summary: runs\t708_quality_exploration_smoke\quality_exploration\quality_exploration_summary.json
- same_geometry_quality_delta_mean=4.2975000086498125e-05
- same_geometry_quality_delta_max=0.0001560000000608852
- same_geometry_meaningful_delta_count=0
- baseline_best_improvement_mean=4.102500008701382e-05
- quality_score_variance=9231610.37480431 is dominated by geometry differences, not by manifest-control effects.

Root cause:
- cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py currently has `ansa_apply_*_control` functions that record controls into execution reports but do not bind those controls to real ANSA mesh operations.
- The affected functions are:
  - ansa_apply_hole_control
  - ansa_apply_slot_control
  - ansa_apply_cutout_control
  - ansa_apply_bend_control
  - ansa_apply_flange_control
- Therefore the T-708 perturbation manifests are nearly no-op for the same geometry. The current data cannot prove meaningful quality-aware learning.

Immediate next task:
- Implement real ANSA control application, then rerun the T-708 real quality gate.

Closed implementation plan:
1. Re-read `AMG.md`, `CDF.md`, and `ANSA_INTEGRATION.md` sections about manifest controls, ANSA adapter operations, batch meshing, and quality reports.
2. Inspect `cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py` and `cdf_ansa_oracle.py`.
3. Add an ANSA runtime probe or introspection path if needed to discover the exact v25.1.0 API calls for:
   - edge length refinement on hole/slot/cutout boundary entities
   - hole washer controls or equivalent local refinement
   - hole/slot suppression or fill behavior where physically supported
   - bend row controls
   - flange sizing controls
4. Replace report-only `ansa_apply_*_control` behavior with actual ANSA API calls. If a control cannot be bound, return a structured unavailable/failure result and do not count it as success.
5. Add a real requires_ansa gate proving that two manifests for the same geometry with different controls produce a meaningful difference in mesh statistics or quality metrics.
6. Rerun:
   - python -m pytest
   - cdf generate --profile sm_quality_exploration_v1 --count 40 --require-ansa
   - cdf validate --require-ansa
   - cdf quality-explore --perturbations-per-sample 3
   - amg training quality
   - amg benchmark quality

T-708 DONE criteria remain:
- Dataset generation and cdf validate --require-ansa succeed.
- quality_exploration_summary.json has blocked_count=0.
- action_entropy_bits > 0 and control_value_variance > 0.
- same_geometry_quality_delta_mean >= 0.01 or an explicitly justified stricter/looser physical threshold based on ANSA metric units.
- both pass and fail or near-fail examples are present.
- validation_pairwise_accuracy > 0.50.
- amg-quality-benchmark returns status SUCCESS.
- No mock, placeholder, unavailable ANSA, controlled failure, deterministic fallback, synthetic graph target, or geometry-only variance can count as success.

If ANSA API binding is not possible from available runtime/docs:
- Keep T-708 BLOCKED.
- Record the exact unavailable API/control, ANSA probe output, command, exit code, and representative report path.
- Do not hide the issue with synthetic metrics, fallback controls, or geometry-level variance.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real ANSA control binding evidence
5. real T-708 gate commands/results
6. whether T-708 is DONE, IN_PROGRESS, or BLOCKED
7. next recommended task
8. blockers or risks
```
