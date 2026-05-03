# AMG/CDF Agent Development Pack

이 디렉터리는 `AMG.md`와 `CDF.md`를 실제 코드 개발로 전환하기 위한 AI 에이전트용 MD 문서 세트이다. 이 문서들은 제품 설계를 다시 정의하지 않는다. 역할은 다음 세 가지이다.

```text
1. 에이전트가 어떤 순서로 구현할지 고정한다.
2. 구현 중 임의 해석을 방지하기 위해 계약, 금지된 의존성, 검증 기준을 분리한다.
3. 매 세션 종료 시 상태와 다음 작업을 갱신할 수 있는 운영 문서를 제공한다.
```

## 배치 위치

아래 파일들을 repository root에 둔다. 같은 root에 `AMG.md`와 `CDF.md`가 있어야 한다.

```text
repo_root/
  AMG.md
  CDF.md
  AGENT.md
  STATUS.md
  ROADMAP.md
  TASKS.md
  ARCHITECTURE.md
  CONTRACTS.md
  DEVELOPMENT_RULES.md
  TESTING.md
  RUNBOOK.md
  DATASET.md
  ANSA_INTEGRATION.md
  MODEL_PLAN.md
  RISK_REGISTER.md
  DECISIONS.md
  NEXT_AGENT_PROMPT.md
```

## 문서 우선순위

충돌이 발생하면 에이전트는 임의로 선택하지 않는다. `STATUS.md`에 `BLOCKED`를 기록하고 사용자에게 확인을 요청한다.

```text
1. AMG.md, CDF.md
   제품 정의, 수학적 규칙, schema target, pipeline의 최상위 source of truth.

2. CONTRACTS.md
   코드 구현에서 사용해야 하는 enum, 파일 계약, schema version, label leakage 방지 규칙.

3. AGENT.md
   AI 에이전트의 작업 방식, 금지된 의존성, 세션 종료 규칙.

4. ROADMAP.md, TASKS.md, STATUS.md
   구현 순서, 현재 상태, 작업 단위, 완료 기준.

5. 나머지 운영 문서
   테스트, 실행, 리스크, ANSA 연동, 모델 개발 보조 기준.
```

## 파일별 목적

| file | 목적 |
|---|---|
| `AGENT.md` | 코딩 에이전트가 반드시 지켜야 하는 작업 규칙과 중단 조건 |
| `STATUS.md` | 현재 개발 상태, 활성 milestone, blocker, 다음 작업 |
| `ROADMAP.md` | 전체 구현 순서와 phase별 exit criteria |
| `TASKS.md` | 원자적 task ID, 산출물, acceptance criteria |
| `ARCHITECTURE.md` | repository 구조, 패키지 경계, 데이터 흐름 |
| `CONTRACTS.md` | AMG/CDF 공유 schema, enum, manifest, graph, dataset 파일 계약 |
| `DEVELOPMENT_RULES.md` | Python 구현 규칙, 재현성, 오류 처리, dependency boundary |
| `TESTING.md` | unit/integration/ANSA test gate와 CI 기준 |
| `RUNBOOK.md` | 목표 CLI, 개발 실행 순서, smoke test 절차 |
| `DATASET.md` | CDF dataset 생성, label, split, acceptance 구현 기준 |
| `ANSA_INTEGRATION.md` | ANSA runner/script/adapter/mocking/실패 reason 기준 |
| `MODEL_PLAN.md` | AMG model 구현 순서, baseline, metrics, checkpoint 규칙 |
| `RISK_REGISTER.md` | 주요 기술 리스크와 concrete mitigation |
| `DECISIONS.md` | 고정된 architecture decision record |
| `NEXT_AGENT_PROMPT.md` | 다음 코딩 세션에 바로 붙여 넣을 수 있도록 매 작업 종료 시 갱신하는 rolling handoff 지시문 |

## 다음 세션 handoff

`NEXT_AGENT_PROMPT.md`는 첫 세션 전용 문서가 아니라 다음 세션용 rolling handoff 문서다. 각 작업 종료 시 `STATUS.md`, `TASKS.md`와 함께 현재 완료 상태, 다음 task ID, 금지 범위, 테스트 명령, blocker를 갱신한다.
