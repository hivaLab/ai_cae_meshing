# STATUS.md

Last updated: 2026-05-03 KST

## Project State

```text
Project state        : T-707 real family-expansion benchmark complete
Active phase         : P7_REAL_PIPELINE_COMPLETION
Active task          : T-708_PRODUCTION_SCALE_DATASET_AND_MODEL_SELECTION
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

Benchmark report:
  runs\t707_family_benchmark\benchmark_report.json
  status=SUCCESS
```

## Blockers And Risks

| item | status | note |
|---|---|---|
| ANSA executable/license | resolved | ANSA v25.1.0 path executes real batch workflow |
| Mock or placeholder accepted samples | resolved | fail-closed checks reject controlled failure, unavailable/mock ANSA, hard failed elements, and placeholder mesh |
| Single-feature flat-panel overclaim | resolved | T-706 included mixed flat and L-bracket cases |
| Broader bent-family generalization | resolved for deterministic generated families | T-707 covers SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, and SM_HAT_CHANNEL |
| HAT truth/detector mismatch | resolved | HAT truth now records four structural flange/sidewall patches to match detected graph candidates |
| Production-scale model quality | open | T-707 proves closed generated benchmark robustness, not large-scale production model selection |

## Next Task

```text
T-708_PRODUCTION_SCALE_DATASET_AND_MODEL_SELECTION

Scale the real accepted dataset and compare explicit AMG model/training configurations.
Select checkpoints using real validation/test evidence, not smoke tests or synthetic targets.
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
  - T-708_PRODUCTION_SCALE_DATASET_AND_MODEL_SELECTION
