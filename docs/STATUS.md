# STATUS.md

Last updated: 2026-05-05 KST

## Project State

```text
Project state        : T-711 fail-closed AI recommendation gate exposes candidate/model gap
Active phase         : P7_REAL_PIPELINE_COMPLETION
Active task          : T-711_AI_CANDIDATE_QUALITY_IMPROVEMENT
Primary source docs  : AMG.md, CDF.md
Execution backend    : ANSA Batch Mesh through adapter/script boundary
Dataset factory      : CDF-SM-ANSA-V1
Model target         : AMG_MANIFEST_SM_V1
Verified ANSA path   : C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```

## Completed Scope

| item | status | note |
|---|---|---|
| P0 contracts and rules | DONE | repository skeleton, schemas, formula/rule tests, dependency boundaries |
| CDF writers and domain models | DONE | T-101 through T-104 |
| CDF CAD generation | DONE | T-201 through T-203 |
| CDF graph and truth matching | DONE | T-301 through T-303 |
| CDF ANSA oracle boundary | DONE | T-401 through T-403 |
| AMG rule-only pipeline | DONE | T-501 through T-503 |
| AMG model/data foundations | DONE | T-601 through T-603 |
| Real fail-closed CDF CLI | DONE | T-701 |
| Real ANSA binding | DONE | T-702, ANSA v25.1.0 batch/script path |
| Real accepted CDF pilot | DONE | T-703, 100 real accepted samples |
| Real AMG training pilot | DONE | T-704 |
| Real AMG inference pilot | DONE | T-705, 20/20 held-out VALID_MESH |
| Mixed real pipeline benchmark | DONE | T-706, 150 accepted samples and 23/23 test VALID_MESH |
| Family expansion benchmark | DONE | T-707, 240 accepted samples and 36/36 test VALID_MESH |
| Fast quality-aware iteration | DONE | T-708, 40 real samples, 120 perturbation evaluations, blocked=0, quality benchmark SUCCESS |
| Quality ranker recommendation | DONE | T-709, 6 real paired ANSA comparisons, 5 improved, recommendation benchmark SUCCESS |
| Fresh active-learning loop | DONE | T-710, 48 fresh real ANSA candidates, 5/6 improved after retraining, benchmark SUCCESS |

## Current Evidence

```text
Note:
  Older generated run directories through T-707 were cleaned from the workspace after completion.
  Their counts below are historical recorded evidence, not currently retained run artifacts.
  Retained real ANSA artifacts for immediate reuse are T-708, T-710, and T-711 outputs.

Historical T-707 benchmark root:
  runs\t707_family_benchmark

Dataset:
  runs\t707_family_benchmark\dataset
  accepted_count=240
  rejected_count=1
  strict validation: SUCCESS, error_count=0
  splits: train=168, val=36, test=36

Coverage:
  part_class:
    SM_FLAT_PANEL=120
    SM_SINGLE_FLANGE=30
    SM_L_BRACKET=30
    SM_U_CHANNEL=30
    SM_HAT_CHANNEL=30
  feature_type:
    HOLE=60
    SLOT=60
    CUTOUT=60
    BEND=240
    FLANGE=240

Training:
  runs\t707_family_benchmark\training
  checkpoint: runs\t707_family_benchmark\training\checkpoint.pt
  metrics: runs\t707_family_benchmark\training\metrics.json
  label_coverage_ratio=1.0
  candidate_count=660
  manifest_feature_count=660

Inference:
  runs\t707_family_benchmark\inference
  split: test
  attempted_count=36
  success_count=36
  failed_count=0
  after_retry_valid_mesh_rate=1.0
  per-family VALID_MESH rate=1.0 for every required part class

T-707 benchmark report:
  runs\t707_family_benchmark\benchmark_report.json
  status=SUCCESS

T-708 quality benchmark:
  runs\t708_quality_exploration_smoke\quality_benchmark_metricfix2.json
  status=SUCCESS
  quality exploration: runs\t708_quality_exploration_smoke\quality_exploration_metricfix2
  baseline_count=40
  evaluated_count=120
  passed_count=84
  near_fail_count=40 in CDF summary, 76 in benchmark evidence including scored failed cases
  failed_count=36
  blocked_count=0
  quality_score_variance=2814384.4276997964
  same_geometry_quality_delta_mean=1671.256000525
  same_geometry_meaningful_delta_count=40
  validation_pairwise_accuracy=0.6666666666666666

T-709 recommendation gate:
  recommendation root: runs\t708_quality_exploration_smoke\recommendation_metricfix4
  benchmark report: runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
  attempted_count=6
  valid_pair_count=6
  improved_count=5
  improvement_rate=0.8333333333333334
  median_improvement_delta=0.39606200000000547
  selected_non_baseline_count=5
  failure_reason_counts={}
  status=SUCCESS

T-710 fresh active-learning gate:
  fresh evidence root: runs\t710_fresh_quality_loop\fresh_quality_exploration
  refreshed training: runs\t710_fresh_quality_loop\training_refreshed
  refreshed recommendation: runs\t710_fresh_quality_loop\recommendation_refreshed
  refreshed benchmark: runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json
  fresh sample_count=6
  fresh generated_count=48
  fresh evaluated_count=48
  fresh blocked_count=0
  fresh unique_candidate_hash_count=48
  fresh quality_score_variance=2048357.424587557
  refreshed recommendation attempted_count=6
  refreshed valid_pair_count=6
  refreshed improved_count=5
  refreshed improvement_rate=0.8333333333333334
  refreshed median_improvement_delta=0.7116335000000036
  selected_non_baseline_count=6
  baseline improvement_rate delta=0.0
  baseline median delta improvement=0.3155714999999981
  status=SUCCESS

T-711 fail-closed AI recommendation gate:
  recommendation root: runs\t710_fresh_quality_loop\recommendation_risk_failclosed
  benchmark report: runs\t710_fresh_quality_loop\recommendation_benchmark_risk_failclosed.json
  attempted_count=6
  valid_pair_count=5
  improved_count=5
  improvement_rate=1.0 over valid AI pairs
  median_improvement_delta=0.7940939999999973
  mean_improvement_delta=0.8044342000000004
  worst_improvement_delta=0.5720929999999935 over valid AI pairs
  severe_regression_threshold=-1.0
  severe_regression_count=0
  selected_non_baseline_count=5
  selected_baseline_count=0
  failure_reason_counts={no_ai_candidate_passed_risk_gate: 1}
  status=FAILED because sample_000036 had no non-baseline AI candidate above the risk threshold
```

## Blockers And Risks

| item | status | note |
|---|---|---|
| ANSA executable/license | resolved | ANSA v25.1.0 path executes real batch workflow |
| Mock or placeholder accepted samples | resolved | fail-closed checks reject controlled failure, unavailable/mock ANSA, hard failed elements, and placeholder mesh |
| Single-feature flat-panel overclaim | resolved | T-706 included mixed flat and L-bracket cases |
| Broader bent-family generalization | resolved for deterministic generated families | T-707 covers SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, and SM_HAT_CHANNEL |
| HAT truth/detector mismatch | resolved | HAT truth now records four structural flange/sidewall patches to match detected graph candidates |
| Production-scale model quality | reframed | T-708 prioritizes information density, quality response diversity, and ranking evidence over blind sample count |
| T-708 real smoke gate | resolved | dataset/validation/quality-explore/training/benchmark succeeded with pass, near-fail, and fail labels |
| Real ANSA control application | resolved for T-708 | manifest controls now bind to ANSA mesh sizing, washer/refinement, suppression/fill, bend row, and flange sizing API paths |
| Quality statistics parsing | resolved for T-708 | parser uses the Session-Parts report table and does not confuse element-count TOTAL headers with violating shell totals |
| Recommendation quality | resolved for T-709 | ranker selected better controls in 5 of 6 paired real ANSA comparisons |
| Fresh control proposal | resolved for T-710 | fresh candidates generated and evaluated with real ANSA, then used for refreshed recommendation |
| Baseline fallback masking | resolved | risk-aware mode no longer selects baseline as a successful recommendation; no candidate means `no_ai_candidate_passed_risk_gate` |
| AI candidate/model quality | open | sample_000036 has no non-baseline fresh candidate that beats the risk gate, so T-711 remains IN_PROGRESS |

## Next Task

```text
T-711_AI_CANDIDATE_QUALITY_IMPROVEMENT

Continue T-711 by improving the AI candidate generation/training path so every held-out sample,
including sample_000036, receives a non-baseline AI recommendation that passes real ANSA validation.
```

## Session Log Template

```text
## Session YYYY-MM-DD T-XXX

Completed:
  - T-XXX ...

Changed files:
  - ...

Tests:
  - command: ...
  - result: PASS/FAIL

Real gates:
  - command: ...
  - result: ...

Blockers:
  - none / ...

Next:
  - T-YYY ...
```

## Session 2026-05-03 T-707

Completed:
  - T-707_REAL_PIPELINE_FAMILY_EXPANSION_AND_ROBUSTNESS

Changed files:
  - ai_mesh_generator/amg/benchmark/real_pipeline.py
  - cad_dataset_factory/cdf/cadgen/bent_part.py
  - cad_dataset_factory/cdf/pipeline/e2e_dataset.py
  - tests/test_amg_real_pipeline_benchmark.py
  - tests/test_cdf_bent_part_generator.py
  - tests/test_cdf_mixed_benchmark_profile.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest
  - result: PASS, 210 passed and 1 skipped in 9.88s

Real gates:
  - command: python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t707_family_benchmark\dataset --count 240 --seed 707 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_family_expansion_v1
  - result: SUCCESS, accepted_count=240, rejected_count=1
  - command: python -m cad_dataset_factory.cdf.cli validate --dataset runs\t707_family_benchmark\dataset --require-ansa
  - result: SUCCESS, accepted_count=240, error_count=0
  - command: python -m ai_mesh_generator.amg.training.real --dataset runs\t707_family_benchmark\dataset --out runs\t707_family_benchmark\training --epochs 15 --batch-size 16 --seed 707
  - result: SUCCESS, label_coverage_ratio=1.0, candidate_count=660, manifest_feature_count=660
  - command: python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\t707_family_benchmark\dataset --checkpoint runs\t707_family_benchmark\training\checkpoint.pt --out runs\t707_family_benchmark\inference --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --split test
  - result: SUCCESS, attempted_count=36, success_count=36, failed_count=0
  - command: python -m ai_mesh_generator.amg.benchmark.real_pipeline --dataset runs\t707_family_benchmark\dataset --training runs\t707_family_benchmark\training --inference runs\t707_family_benchmark\inference --out runs\t707_family_benchmark\benchmark_report.json --profile sm_family_expansion_v1
  - result: SUCCESS

Evidence:
  - benchmark report: runs\t707_family_benchmark\benchmark_report.json
  - per-family VALID_MESH rate: 1.0 for SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL
  - feature_type histogram: HOLE=60, SLOT=60, CUTOUT=60, BEND=240, FLANGE=240

Blockers:
  - none for T-707.
  - Remaining risk: production-scale dataset/model selection is not yet done.

Next:
  - T-708_FAST_QUALITY_AWARE_DATASET_ITERATION

## Session 2026-05-05 T-708 Code Pass

Completed:
  - Implemented the code-side pass for T-708_FAST_QUALITY_AWARE_DATASET_ITERATION.
  - T-708 remains IN_PROGRESS until manifest controls materially affect real ANSA mesh quality and the quality benchmark passes.

Changed files:
  - pyproject.toml
  - cad_dataset_factory/cdf/cli.py
  - cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py
  - cad_dataset_factory/cdf/pipeline/e2e_dataset.py
  - cad_dataset_factory/cdf/quality/__init__.py
  - cad_dataset_factory/cdf/quality/exploration.py
  - ai_mesh_generator/amg/training/__init__.py
  - ai_mesh_generator/amg/training/quality.py
  - ai_mesh_generator/amg/benchmark/__init__.py
  - ai_mesh_generator/amg/benchmark/quality.py
  - tests/test_cdf_mixed_benchmark_profile.py
  - tests/test_cdf_quality_exploration.py
  - tests/test_amg_quality_training.py
  - tests/test_amg_quality_benchmark.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest
  - result: PASS, 224 passed and 1 skipped in 10.43s

Real gates:
  - command: python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t708_quality_exploration_smoke\dataset --count 40 --seed 708 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_quality_exploration_v1
  - result: SUCCESS, accepted_count=40, rejected_count=2
  - command: python -m cad_dataset_factory.cdf.cli validate --dataset runs\t708_quality_exploration_smoke\dataset --require-ansa
  - result: SUCCESS, accepted_count=40, error_count=0
  - command: python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  - result: SUCCESS, baseline_count=40, evaluated_count=120, blocked_count=0, passed_count=160, failed_count=0, quality_score_variance=9231610.37480431
  - command: python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration --out runs\t708_quality_exploration_smoke\training_quality --epochs 5 --batch-size 32 --seed 708
  - result: SUCCESS, validation_pairwise_accuracy=0.6785714285714286
  - command: python -m ai_mesh_generator.amg.benchmark.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration --training runs\t708_quality_exploration_smoke\training_quality --out runs\t708_quality_exploration_smoke\quality_benchmark.json
  - result: FAILED, has_pass_and_fail_or_near_fail_examples=false, same_geometry_quality_delta_meaningful=false

Evidence:
  - quality benchmark: runs\t708_quality_exploration_smoke\quality_benchmark.json
  - quality exploration summary: runs\t708_quality_exploration_smoke\quality_exploration\quality_exploration_summary.json
  - same_geometry_quality_delta_mean=4.2975000086498125e-05
  - same_geometry_quality_delta_max=0.0001560000000608852
  - same_geometry_meaningful_delta_count=0
  - baseline_best_improvement_mean=4.102500008701382e-05
  - ANSA reports show controls_applied entries, but cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py `ansa_apply_*_control` functions only record controls.

Blockers:
  - Real ANSA controls are not applied to mesh generation yet; perturbations are effectively no-op with respect to same-geometry quality.
  - T-708 cannot be marked DONE from geometry-level quality variance alone.

Next:
  - Implement real ANSA control application for at least edge length, washer, suppression, bend rows, and flange sizing, then rerun T-708 quality gate.

## Session 2026-05-05 T-708 Real Gate Closure

Completed:
  - T-708_FAST_QUALITY_AWARE_DATASET_ITERATION.
  - Bound manifest control perturbations to real ANSA mesh-control API calls.
  - Fixed ANSA statistics parsing so Session-Parts quality totals are not overwritten by shell element-count TOTAL headers.
  - Preserved accepted-but-margin-poor records as NEAR_FAIL and hard-failed records as FAILED instead of hiding them as blocked metric gaps.

Changed files:
  - ai_mesh_generator/amg/benchmark/quality.py
  - cad_dataset_factory/cdf/cli.py
  - cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py
  - cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_oracle.py
  - cad_dataset_factory/cdf/quality/exploration.py
  - tests/test_amg_quality_benchmark.py
  - tests/test_cdf_ansa_internal_script_skeleton.py
  - tests/test_cdf_quality_exploration.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest tests\test_cdf_quality_exploration.py tests\test_amg_quality_benchmark.py tests\test_cdf_ansa_internal_script_skeleton.py tests\test_dependency_boundary.py
  - result: PASS, 22 passed and 1 skipped in 0.47s
  - command: python -m pytest
  - result: PASS, 229 passed and 2 skipped in 10.54s
  - command: $env:ANSA_EXECUTABLE='C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat'; python -m pytest tests\test_cdf_quality_exploration.py -m requires_ansa
  - result: PASS, 1 passed and 5 deselected in 29.01s

Real gates:
  - command: python -m cad_dataset_factory.cdf.cli validate --dataset runs\t708_quality_exploration_smoke\dataset --require-ansa
  - result: SUCCESS, accepted_count=40, error_count=0
  - command: python -m cad_dataset_factory.cdf.cli quality-explore --dataset runs\t708_quality_exploration_smoke\dataset --out runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --perturbations-per-sample 3 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  - result: SUCCESS, baseline_count=40, evaluated_count=120, blocked_count=0, passed_count=84, near_fail_count=40, failed_count=36, quality_score_variance=2814384.4276997964
  - command: python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --out runs\t708_quality_exploration_smoke\training_quality_metricfix2 --epochs 5 --batch-size 32 --seed 708
  - result: SUCCESS, validation_pairwise_accuracy=0.6666666666666666
  - command: python -m ai_mesh_generator.amg.benchmark.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t708_quality_exploration_smoke\quality_benchmark_metricfix2.json
  - result: SUCCESS

Evidence:
  - quality benchmark: runs\t708_quality_exploration_smoke\quality_benchmark_metricfix2.json
  - action_entropy_bits=2.272088893287269
  - feature_type_entropy_bits=2.28558992945765
  - control_value_variance=28.23013372004848
  - same_geometry_quality_delta_mean=1671.256000525
  - same_geometry_meaningful_delta_count=40
  - benchmark near_fail_count=76, including scored failed records
  - ANSA execution reports include bound_to_real_ansa_api=true and applied API paths for mesh length/perimeter controls.

Blockers:
  - none for T-708.
  - Remaining risk: T-708 proves quality-aware data and ranking signal, but not yet that the trained ranker selects better controls during fresh recommendation. That is T-709.

Next:
  - T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA

## Session 2026-05-05 T-709

Completed:
  - T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA.
  - Added AMG-side quality recommendation and recommendation benchmark paths.
  - Shared the quality ranker feature-vector construction between training and recommendation to avoid train/serve drift.
  - Extended real ANSA suppression/fill binding so baseline and recommended manifests both produce real mesh artifacts.

Changed files:
  - ai_mesh_generator/amg/quality_features.py
  - ai_mesh_generator/amg/training/quality.py
  - ai_mesh_generator/amg/recommendation/__init__.py
  - ai_mesh_generator/amg/recommendation/quality.py
  - ai_mesh_generator/amg/benchmark/__init__.py
  - ai_mesh_generator/amg/benchmark/recommendation.py
  - cad_dataset_factory/cdf/oracle/ansa_scripts/cdf_ansa_api_layer.py
  - pyproject.toml
  - tests/test_amg_quality_recommendation.py
  - tests/test_cdf_ansa_internal_script_skeleton.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest tests\test_amg_quality_training.py tests\test_amg_quality_recommendation.py tests\test_amg_quality_benchmark.py tests\test_dependency_boundary.py
  - result: PASS, 17 passed in 2.42s
  - command: python -m pytest tests\test_cdf_ansa_internal_script_skeleton.py tests\test_amg_quality_recommendation.py tests\test_dependency_boundary.py
  - result: PASS, 16 passed in 1.65s
  - command: python -m pytest
  - result: PASS, 234 passed and 2 skipped in 10.81s

Real gates:
  - command: python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t708_quality_exploration_smoke\recommendation_metricfix4 --split test --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  - result: SUCCESS, attempted_count=6, valid_pair_count=6, improved_count=5, improvement_rate=0.8333333333333334, median_improvement_delta=0.39606200000000547, selected_non_baseline_count=5, failure_reason_counts={}
  - command: python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t708_quality_exploration_smoke\recommendation_metricfix4 --out runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
  - result: SUCCESS

Evidence:
  - recommendation summary: runs\t708_quality_exploration_smoke\recommendation_metricfix4\recommendation_summary.json
  - recommendation benchmark: runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
  - all 6 paired samples have baseline and recommended real ANSA reports plus non-empty BDF outputs.

Blockers:
  - none for T-709.
  - Remaining risk: T-709 chooses among T-708 evaluated perturbation manifests; T-710 must generate fresh candidates, append evidence, and retrain.

Next:
  - T-710_FRESH_QUALITY_CONTROL_PROPOSAL_AND_ACTIVE_LEARNING_LOOP

## Session 2026-05-05 T-710

Completed:
  - T-710_FRESH_QUALITY_CONTROL_PROPOSAL_AND_ACTIVE_LEARNING_LOOP.
  - Added AMG-only fresh candidate proposal and real ANSA evidence append path.
  - Extended quality training to consume extra fresh evidence roots.
  - Extended recommendation benchmark with baseline comparison.

Changed files:
  - ai_mesh_generator/amg/recommendation/fresh.py
  - ai_mesh_generator/amg/recommendation/__init__.py
  - ai_mesh_generator/amg/training/quality.py
  - ai_mesh_generator/amg/benchmark/recommendation.py
  - pyproject.toml
  - tests/test_amg_fresh_quality_proposal.py
  - tests/test_amg_quality_recommendation.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest tests\test_amg_fresh_quality_proposal.py tests\test_amg_quality_recommendation.py tests\test_amg_quality_training.py tests\test_dependency_boundary.py
  - result: PASS, 15 passed in 2.44s
  - command: python -m pytest
  - result: PASS, 238 passed and 2 skipped in 11.11s

Real gates:
  - command: python -m ai_mesh_generator.amg.recommendation.fresh --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --training runs\t708_quality_exploration_smoke\training_quality_metricfix2 --out runs\t710_fresh_quality_loop\fresh_quality_exploration --split test --candidates-per-sample 8 --limit 6 --seed 710 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  - result: SUCCESS, sample_count=6, generated_count=48, evaluated_count=48, blocked_count=0, quality_score_variance=2048357.424587557
  - command: python -m ai_mesh_generator.amg.training.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t708_quality_exploration_smoke\quality_exploration_metricfix2 --extra-quality-evidence runs\t710_fresh_quality_loop\fresh_quality_exploration --out runs\t710_fresh_quality_loop\training_refreshed --epochs 5 --batch-size 32 --seed 710
  - result: SUCCESS, example_count=208, validation_pairwise_accuracy=0.6666666666666666
  - command: python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --training runs\t710_fresh_quality_loop\training_refreshed --out runs\t710_fresh_quality_loop\recommendation_refreshed --split test --limit 6 --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  - result: SUCCESS, attempted_count=6, valid_pair_count=6, improved_count=5, improvement_rate=0.8333333333333334, median_improvement_delta=0.7116335000000036
  - command: python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t710_fresh_quality_loop\recommendation_refreshed --out runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json --baseline runs\t708_quality_exploration_smoke\recommendation_benchmark_metricfix4.json
  - result: SUCCESS

Evidence:
  - fresh summary: runs\t710_fresh_quality_loop\fresh_quality_exploration\quality_exploration_summary.json
  - refreshed benchmark: runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json
  - T-709 improvement_rate was preserved at 0.8333333333333334.
  - median_improvement_delta improved from 0.39606200000000547 to 0.7116335000000036.
  - selected_non_baseline_count increased from 5 to 6.

Blockers:
  - none for T-710.
  - Remaining risk: sample_000036 regressed by -9.106281, so mean_improvement_delta is negative despite benchmark success.

Next:
  - T-711_RISK_AWARE_RECOMMENDATION_GUARDRAILS

## Session 2026-05-05 T-711 Corrective Pass

Completed:
  - Removed baseline fallback as a successful recommendation path.
  - Removed baseline selection from the non-risk-aware recommendation path as well; baseline is comparison evidence only.
  - Added fail-closed risk-aware candidate selection: if no non-baseline AI candidate passes risk thresholds, the sample fails with no_ai_candidate_passed_risk_gate.
  - Added downside-risk metrics to recommendation summaries and benchmark reports.
  - Split per-sample improvement epsilon from median acceptance threshold so benchmark statistics do not hide or distort safety criteria.

Changed files:
  - ai_mesh_generator/amg/recommendation/quality.py
  - ai_mesh_generator/amg/benchmark/recommendation.py
  - tests/test_amg_quality_recommendation.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest tests\test_amg_fresh_quality_proposal.py tests\test_amg_quality_candidate_diagnostics.py tests\test_amg_quality_training.py tests\test_cdf_ansa_internal_script_skeleton.py tests\test_amg_quality_recommendation.py
  - result: PASS, 24 passed in 2.99s
  - command: python -m pytest
  - result: PASS, 244 passed and 2 skipped in 12.23s

Real gates:
  - command: python -m ai_mesh_generator.amg.recommendation.quality --dataset runs\t708_quality_exploration_smoke\dataset --quality-exploration runs\t710_fresh_quality_loop\fresh_quality_exploration --training runs\t710_fresh_quality_loop\training_refreshed --out runs\t710_fresh_quality_loop\recommendation_risk_failclosed --split test --limit 6 --risk-aware --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  - result: PARTIAL_FAILED, attempted_count=6, valid_pair_count=5, improvement_rate=1.0 over valid AI pairs, median_improvement_delta=0.7940939999999973, severe_regression_count=0, failure_reason_counts={no_ai_candidate_passed_risk_gate: 1}
  - command: python -m ai_mesh_generator.amg.benchmark.recommendation --recommendation runs\t710_fresh_quality_loop\recommendation_risk_failclosed --out runs\t710_fresh_quality_loop\recommendation_benchmark_risk_failclosed.json --baseline runs\t710_fresh_quality_loop\recommendation_benchmark_refreshed.json --min-improvement-rate 0.8333333333333334 --min-median-delta 0.7116335000000036 --severe-regression-threshold -1.0 --max-severe-regression-count 0
  - result: FAILED, all_pairs_valid=false, failure_reason_counts={no_ai_candidate_passed_risk_gate: 1}, selected_baseline_count=0

Evidence:
  - recommendation summary: runs\t710_fresh_quality_loop\recommendation_risk_failclosed\recommendation_summary.json
  - recommendation benchmark: runs\t710_fresh_quality_loop\recommendation_benchmark_risk_failclosed.json
  - sample_000036 diagnostic: runs\t710_fresh_quality_loop\sample_000036_candidate_diagnostic.json
  - sample_000036 no longer falls back to baseline; it is reported as no_ai_candidate_passed_risk_gate.
  - 5 paired samples have non-baseline AI recommendations with real ANSA reports plus non-empty BDF outputs.
  - Fresh candidate generation now includes non-baseline SUPPRESS candidates with suppression_max_diameter_scale for small relief/drain features.
  - The ANSA API layer passes suppression_max_diameter_scale into the real fill/suppression API path.
  - Recommendation now runs only the selected non-baseline AI manifest by default; baseline ANSA execution requires --compare-baseline.
  - Sanity retraining with feature normalization and the updated quality vector completed at runs\t711_ai_candidate_quality_improvement\training_quality_v2 with validation_pairwise_accuracy=0.6666666666666666.
  - Real ANSA single-sample probe for sample_000036 generated four non-baseline SUPPRESS candidates; best fresh score was 0.039156000000002675 versus old recorded baseline/reference score 1.9891719999999915.
  - AI-only recommendation probe for sample_000036 succeeded with selected_baseline_count=0 and recommended_score=0.45267200000000596.

Blockers:
  - T-711 is not DONE. sample_000036 needs improved AI candidate generation/training, not baseline fallback.
  - The quality feature vector changed, so existing quality-ranker checkpoints from T-710 are intentionally stale for new T-711 candidates and must be retrained.
  - The single-sample probe is not a full T-711 gate. The full six-sample held-out gate still needs to be rerun after generating fresh candidates for all six samples.

Next:
  - T-711_AI_CANDIDATE_QUALITY_IMPROVEMENT
