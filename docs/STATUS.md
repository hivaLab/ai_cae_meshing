# STATUS.md

Last updated: 2026-05-03 KST

## 1. 현재 상태

```text
Project state        : T-203 feature placement sampler complete
Active phase         : P3_BREP_GRAPH_AND_MATCHING
Active task          : T-301_BREP_GRAPH_EXTRACTOR
Primary source docs  : AMG.md, CDF.md
Execution backend    : ANSA Batch Mesh, through adapter/script boundary
Dataset factory      : CDF-SM-ANSA-V1
Model target         : AMG_MANIFEST_SM_V1
```

## 2. 완료된 항목

| item | status | note |
|---|---|---|
| AMG specification | DONE | `AMG.md` available |
| CDF specification | DONE | `CDF.md` available |
| Agent handoff docs | DONE | this document set |
| Code repository skeleton | DONE | T-001 complete |
| JSON schemas | DONE | T-002 complete; ANSA report contracts split into execution and quality reports |
| Formula tests | DONE | T-004/T-005 complete |
| CDF domain models | DONE | T-101 complete |
| CDF manifest writer | DONE | T-102 complete |
| CDF auxiliary label writers | DONE | T-103 complete |
| CDF sample writer | DONE | T-104 complete |
| CDF flat panel generator | DONE | T-201 complete |
| CDF bent part generators | DONE | T-202 complete |
| CDF feature placement sampler | DONE | T-203 complete |
| CDF generator | TODO | after P0 |
| ANSA oracle | TODO | after pure tests and mock runner |
| AMG rule-only pipeline | TODO | after contracts and CDF labels |
| AMG model training | TODO | after dataset ingestion path exists |

## 3. 현재 blocker

| blocker | severity | resolution |
|---|---:|---|
| ANSA executable path not configured | medium | pure tests and mocked reports proceed; real ANSA tests use `requires_ansa` marker |
| CAD kernel behavior not validated | medium | defer to P2; begin with schema and math rules |
| CDF/TASKS requested obsolete `CDF_ANSA_ORACLE_REPORT_SM_V1.schema.json` name | resolved | use canonical `CDF_ANSA_EXECUTION_REPORT_SM_V1` and `CDF_ANSA_QUALITY_REPORT_SM_V1` |
| AMG graph node type listed `FEATURE` while CDF/CONTRACTS listed `FEATURE_CANDIDATE` | resolved | use canonical `FEATURE_CANDIDATE` |

## 4. 다음 작업

```text
T-301_BREP_GRAPH_EXTRACTOR
  Extract PART/FACE/EDGE/COEDGE/VERTEX/FEATURE_CANDIDATE graph from STEP.
```

## 5. 상태 업데이트 규칙

에이전트는 작업 완료 후 이 파일을 갱신한다.

```text
1. Last updated 갱신
2. Active task 갱신
3. 완료된 task status 변경
4. blocker 추가/해결 기록
5. 다음 작업을 한 개 이상 명시
```

## 6. 세션 로그 템플릿

```text
## Session YYYY-MM-DD

Completed:
  - T-XXX ...

Changed files:
  - ...

Tests:
  - command: ...
  - result: PASS/FAIL

Blockers:
  - none / ...

Next:
  - T-YYY ...
```

## Session 2026-05-03

Completed:
  - none

Changed files:
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: FAIL/BLOCKED, collected 0 items; pytest also could not create `.pytest_cache` due WinError 5 access denied

Blockers:
  - CDF/TASKS request `CDF_ANSA_ORACLE_REPORT_SM_V1.schema.json`, but CONTRACTS canonical schema versions list `CDF_ANSA_EXECUTION_REPORT_SM_V1` and `CDF_ANSA_QUALITY_REPORT_SM_V1`.
  - AMG graph node type lists `FEATURE`, while CDF and CONTRACTS list `FEATURE_CANDIDATE`.

Next:
  - BLOCKED_SOURCE_CONTRACT_CLARIFICATION

## Session 2026-05-03 P0 completion

Completed:
  - BLOCKED_SOURCE_CONTRACT_CLARIFICATION
  - T-001_REPOSITORY_SKELETON
  - T-002_CONTRACT_SCHEMA_SKELETON
  - T-003_CONFIG_SCHEMA_AND_DEFAULTS
  - T-004_MATH_UTILITIES
  - T-005_LABEL_RULES_PURE
  - T-006_DEPENDENCY_BOUNDARY_TESTS

Changed files:
  - .gitignore
  - AGENT.md
  - README.md
  - pyproject.toml
  - contracts/*.schema.json
  - configs/*.json
  - ai_mesh_generator/**
  - cad_dataset_factory/**
  - tests/**
  - docs/AMG.md
  - docs/ARCHITECTURE.md
  - docs/CDF.md
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 26 passed in 0.13s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - CAD kernel behavior not validated; CadQuery generation remains out of this session.

Next:
  - T-101_CDF_DOMAIN_MODELS

## Session 2026-05-03 T-101

Completed:
  - T-101_CDF_DOMAIN_MODELS

Changed files:
  - pyproject.toml
  - cad_dataset_factory/cdf/domain/__init__.py
  - cad_dataset_factory/cdf/domain/models.py
  - tests/test_cdf_domain_models.py
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 32 passed in 0.25s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - CAD kernel behavior not validated; CadQuery generation remains out of this session.

Next:
  - T-102_CDF_MANIFEST_WRITER

## Session 2026-05-03 T-102

Completed:
  - T-102_CDF_MANIFEST_WRITER

Changed files:
  - .gitignore
  - cad_dataset_factory/cdf/labels/__init__.py
  - cad_dataset_factory/cdf/labels/manifest_writer.py
  - tests/test_cdf_manifest_writer.py
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 39 passed in 0.25s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - CAD kernel behavior not validated; CadQuery generation remains out of this session.

Next:
  - T-103_CDF_AUX_LABEL_WRITERS

## Session 2026-05-03 T-103

Completed:
  - T-103_CDF_AUX_LABEL_WRITERS

Changed files:
  - cad_dataset_factory/cdf/labels/__init__.py
  - cad_dataset_factory/cdf/labels/aux_label_writer.py
  - tests/test_cdf_aux_label_writer.py
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 48 passed in 0.28s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - CAD kernel behavior not validated; CadQuery generation remains out of this session.

Next:
  - T-104_CDF_SAMPLE_WRITER

## Session 2026-05-03 T-104

Completed:
  - T-104_CDF_SAMPLE_WRITER

Changed files:
  - cad_dataset_factory/cdf/dataset/__init__.py
  - cad_dataset_factory/cdf/dataset/sample_writer.py
  - tests/test_cdf_sample_writer.py
  - docs/AGENT.md
  - docs/NEXT_AGENT_PROMPT.md
  - docs/README.md
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 53 passed in 0.29s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - CAD kernel behavior not validated; T-201 begins CadQuery flat-panel generation and must validate CAD behavior.

Next:
  - T-201_FLAT_PANEL_GENERATOR

## Session 2026-05-03 T-201

Completed:
  - T-201_FLAT_PANEL_GENERATOR

Changed files:
  - pyproject.toml
  - cad_dataset_factory/cdf/cadgen/__init__.py
  - cad_dataset_factory/cdf/cadgen/flat_panel.py
  - tests/test_cdf_flat_panel_generator.py
  - docs/NEXT_AGENT_PROMPT.md
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 60 passed in 1.63s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - Bent part generation remains unimplemented and is the next P2 task.

Next:
  - T-202_BENT_PART_GENERATORS

## Session 2026-05-03 T-202

Completed:
  - T-202_BENT_PART_GENERATORS

Changed files:
  - cad_dataset_factory/cdf/cadgen/__init__.py
  - cad_dataset_factory/cdf/cadgen/bent_part.py
  - tests/test_cdf_bent_part_generator.py
  - docs/NEXT_AGENT_PROMPT.md
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 69 passed in 1.57s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - Random feature placement remains unimplemented and is the next P2 task.

Next:
  - T-203_FEATURE_PLACEMENT_SAMPLER

## Session 2026-05-03 T-203

Completed:
  - T-203_FEATURE_PLACEMENT_SAMPLER

Changed files:
  - cad_dataset_factory/cdf/sampling/__init__.py
  - cad_dataset_factory/cdf/sampling/feature_layout.py
  - tests/test_cdf_feature_layout_sampler.py
  - docs/NEXT_AGENT_PROMPT.md
  - docs/STATUS.md
  - docs/TASKS.md

Tests:
  - command: python -m pytest
  - result: PASS, 77 passed in 1.70s

Blockers:
  - ANSA executable path not configured; real ANSA tests remain deferred to `requires_ansa`.
  - B-rep graph extraction remains unimplemented and is the next phase task.

Next:
  - T-301_BREP_GRAPH_EXTRACTOR
