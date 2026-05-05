# STATUS.md

Last updated: 2026-05-05 KST

## Project State

```text
Project state        : T-708 quality-aware iteration real gate complete
Active phase         : P7_REAL_PIPELINE_COMPLETION
Active task          : T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA
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

## Current Evidence

```text
T-707 benchmark root:
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
| Recommendation quality | open | T-709 must prove the ranker can select better controls, not only rank already-evaluated perturbations |

## Next Task

```text
T-709_QUALITY_RANKER_RECOMMENDATION_TO_REAL_ANSA

Use the T-708 quality ranker to select recommended manifests for held-out geometries, run real ANSA,
and compare recommended mesh quality against baseline and naive control manifests.
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
