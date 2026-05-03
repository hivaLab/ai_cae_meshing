# STATUS.md

Last updated: 2026-05-03 KST

## Project State

```text
Project state        : T-706 real mixed pipeline benchmark complete
Active phase         : P7_REAL_PIPELINE_COMPLETION
Active task          : T-707_REAL_PIPELINE_FAMILY_EXPANSION_AND_ROBUSTNESS
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

## Current Evidence

```text
T-706 benchmark root:
  runs\t706_mixed_benchmark

Dataset:
  runs\t706_mixed_benchmark\dataset
  accepted_count=150
  rejected_count=1
  strict validation: SUCCESS, error_count=0
  splits: train=105, val=22, test=23

Coverage:
  part_class: SM_FLAT_PANEL=120, SM_L_BRACKET=30
  feature_type: HOLE=60, SLOT=60, CUTOUT=60, BEND=30, FLANGE=30

Training:
  runs\t706_mixed_benchmark\training
  checkpoint: runs\t706_mixed_benchmark\training\checkpoint.pt
  metrics: runs\t706_mixed_benchmark\training\metrics.json
  label_coverage_ratio=1.0
  candidate_count=240
  manifest_feature_count=240

Inference:
  runs\t706_mixed_benchmark\inference
  split: test
  attempted_count=23
  success_count=23
  failed_count=0
  after_retry_valid_mesh_rate=1.0

Benchmark report:
  runs\t706_mixed_benchmark\benchmark_report.json
  status=SUCCESS
```

## Blockers And Risks

| item | status | note |
|---|---|---|
| ANSA executable/license | resolved | ANSA v25.1.0 path executes real batch workflow |
| Mock or placeholder accepted samples | resolved | fail-closed checks reject controlled failure, unavailable/mock ANSA, hard failed elements, and placeholder mesh |
| Single-feature flat-panel overclaim | resolved for T-706 | benchmark now includes HOLE, SLOT, CUTOUT, BEND, FLANGE and SM_L_BRACKET |
| Broader bent-family generalization | open | SM_SINGLE_FLANGE, SM_U_CHANNEL, and SM_HAT_CHANNEL are not yet part of the real accepted benchmark |
| Production-scale model quality | open | T-706 proves constrained mixed benchmark success, not broad production robustness |

## Next Task

```text
T-707_REAL_PIPELINE_FAMILY_EXPANSION_AND_ROBUSTNESS

Expand the real benchmark to additional bent families and harder feature combinations.
Keep fail-closed semantics: unsupported family paths must be BLOCKED/FAILED evidence, not hidden skips.
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

## Session 2026-05-03 T-706

Completed:
  - T-706_REAL_PIPELINE_SCALE_UP_AND_GENERALIZATION_BENCHMARK

Changed files:
  - ai_mesh_generator/amg/benchmark/__init__.py
  - ai_mesh_generator/amg/benchmark/real_pipeline.py
  - ai_mesh_generator/amg/inference/real_mesh.py
  - ai_mesh_generator/amg/model/graph_model.py
  - cad_dataset_factory/cdf/cli.py
  - cad_dataset_factory/cdf/pipeline/e2e_dataset.py
  - pyproject.toml
  - tests/test_amg_real_mesh_inference.py
  - tests/test_amg_real_pipeline_benchmark.py
  - tests/test_cdf_mixed_benchmark_profile.py
  - docs/STATUS.md
  - docs/TASKS.md
  - docs/NEXT_AGENT_PROMPT.md

Tests:
  - command: python -m pytest
  - result: PASS, 204 passed and 1 skipped in 8.65s

Real gates:
  - command: python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\t706_mixed_benchmark\dataset --count 150 --seed 706 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --profile sm_mixed_benchmark_v1
  - result: SUCCESS, accepted_count=150, rejected_count=1
  - command: python -m cad_dataset_factory.cdf.cli validate --dataset runs\t706_mixed_benchmark\dataset --require-ansa
  - result: SUCCESS, accepted_count=150, error_count=0
  - command: python -m ai_mesh_generator.amg.training.real --dataset runs\t706_mixed_benchmark\dataset --out runs\t706_mixed_benchmark\training --epochs 10 --batch-size 16 --seed 706
  - result: SUCCESS, label_coverage_ratio=1.0, candidate_count=240, manifest_feature_count=240
  - command: python -m ai_mesh_generator.amg.inference.real_mesh --dataset runs\t706_mixed_benchmark\dataset --checkpoint runs\t706_mixed_benchmark\training\checkpoint.pt --out runs\t706_mixed_benchmark\inference --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat --split test
  - result: SUCCESS, attempted_count=23, success_count=23, failed_count=0
  - command: python -m ai_mesh_generator.amg.benchmark.real_pipeline --dataset runs\t706_mixed_benchmark\dataset --training runs\t706_mixed_benchmark\training --inference runs\t706_mixed_benchmark\inference --out runs\t706_mixed_benchmark\benchmark_report.json
  - result: SUCCESS

Evidence:
  - benchmark report: runs\t706_mixed_benchmark\benchmark_report.json
  - part_class histogram: SM_FLAT_PANEL=120, SM_L_BRACKET=30
  - feature_type histogram: HOLE=60, SLOT=60, CUTOUT=60, BEND=30, FLANGE=30
  - after_retry_valid_mesh_rate=1.0

Blockers:
  - none for T-706.
  - Remaining risk: broader bent families are not yet validated in the real benchmark.

Next:
  - T-707_REAL_PIPELINE_FAMILY_EXPANSION_AND_ROBUSTNESS
