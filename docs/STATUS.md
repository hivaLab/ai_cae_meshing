# STATUS.md

Last updated: 2026-05-03 KST

## 1. 현재 상태

```text
Project state        : Specification handoff complete; code implementation not started
Active phase         : P0_BOOTSTRAP_CONTRACTS_AND_RULES
Active task          : T-001_REPOSITORY_SKELETON
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
| Code repository skeleton | TODO | start with T-001 |
| JSON schemas | TODO | start with T-002 |
| Formula tests | TODO | start with T-004/T-005 |
| CDF generator | TODO | after P0 |
| ANSA oracle | TODO | after pure tests and mock runner |
| AMG rule-only pipeline | TODO | after contracts and CDF labels |
| AMG model training | TODO | after dataset ingestion path exists |

## 3. 현재 blocker

| blocker | severity | resolution |
|---|---:|---|
| ANSA executable path not configured | medium | pure tests and mocked reports proceed; real ANSA tests use `requires_ansa` marker |
| No repository code yet | low | create skeleton in T-001 |
| CAD kernel behavior not validated | medium | defer to P2; begin with schema and math rules |

## 4. 다음 작업

```text
T-001_REPOSITORY_SKELETON
  Create package directories, pyproject.toml skeleton, empty __init__.py files, and docs location.

T-002_CONTRACT_SCHEMA_SKELETON
  Create JSON schema skeletons for AMG_MANIFEST_SM_V1, AMG_BREP_GRAPH_SM_V1, CDF_FEATURE_TRUTH_SM_V1, CDF_ANSA_ORACLE_REPORT_SM_V1.

T-003_CONFIG_SCHEMA_AND_DEFAULTS
  Create default config files and config loaders.

T-004_MATH_UTILITIES
  Implement clamp, make_even, log-size projection utility skeleton, and tests.

T-005_LABEL_RULES_PURE
  Implement hole/slot/cutout/bend/flange deterministic label functions and tests.
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
