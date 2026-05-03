# AGENT.md

## 1. 역할

이 repository에서 AI 코딩 에이전트의 역할은 `AMG.md`와 `CDF.md`의 닫힌 설계를 실행 가능한 Python code, JSON schema, tests, CLI로 변환하는 것이다. 에이전트는 제품 범위를 확장하지 않는다. 정의되지 않은 기능을 추가하지 않는다. 구현은 항상 명시된 task ID와 연결한다.

```text
AMG = 일정 두께 판금 STEP solid를 입력받아 ANSA용 mesh-control manifest를 예측하고 실행하는 도구
CDF = AMG 학습용 synthetic sheet-metal dataset과 AMG-compatible manifest label을 생성하는 독립 dataset factory
```

## 2. Source of truth

에이전트는 작업 시작 전 다음 문서를 읽은 것으로 간주한다.

```text
AMG.md
CDF.md
CONTRACTS.md
ARCHITECTURE.md
TASKS.md
STATUS.md
TESTING.md
```

제품 의미는 `AMG.md`와 `CDF.md`가 결정한다. 코드 작업 방식은 이 문서가 결정한다. enum, schema, 파일명은 `CONTRACTS.md`와 일치해야 한다.

## 3. 기본 작업 루프

각 세션은 다음 순서로 진행한다.

```text
1. STATUS.md에서 active phase와 next task 확인
2. TASKS.md에서 해당 task ID의 acceptance criteria 확인
3. 관련 source spec 확인
4. 최소 범위 구현
5. 해당 test 추가 또는 수정
6. pytest 실행
7. STATUS.md와 TASKS.md 갱신
8. 변경 파일, 테스트 결과, 남은 blocker를 최종 응답에 요약
```

한 세션에서 여러 milestone을 건너뛰지 않는다. 현재 task를 완료하지 못하면 partial result와 blocker를 기록한다.

## 4. 구현 원칙

### 4.1 Manifest-first 개발

AMG는 node 좌표와 element connectivity를 직접 예측하지 않는다. 구현 대상은 ANSA가 실행할 수 있는 `mesh_control_manifest.json`과 그 생성, 검증, 실행 pipeline이다.

### 4.2 Rule-first 개발

AI model은 후순위이다. 먼저 deterministic rule-only path를 구현한다.

```text
input.step/config/truth
  → geometry/feature representation
  → deterministic rules
  → AMG_MANIFEST_SM_V1
  → schema validation
```

### 4.3 Contract-first 개발

코드를 작성하기 전에 enum, schema, path, status, reason을 contract로 고정한다. schema와 code가 충돌하면 code를 schema에 맞춘다. schema 자체가 틀렸다고 판단되면 `DECISIONS.md`와 `STATUS.md`에 proposed change를 기록하고 작업을 중단한다.

### 4.4 Test-first for formulas

수학 공식, action rule, projection rule, naming rule은 먼저 unit test를 만든다. CAD kernel이나 ANSA 없이 실행 가능한 테스트를 우선한다.

## 5. Dependency boundary

### 5.1 CDF 독립성

CDF는 AMG code를 import하지 않는다. CDF는 AMG-compatible files를 생성할 뿐이다.

허용되는 연결점은 versioned file contract이다.

```text
contracts/*.schema.json
labels/amg_manifest.json
graph/brep_graph.npz
```

### 5.2 ANSA boundary

ANSA Python API import는 ANSA 내부 실행 script에만 둔다.

```text
cad_dataset_factory/cdf/oracle/ansa_scripts/
ai_mesh_generator/ansa/ansa_scripts/        # AMG에서 별도 script를 둘 경우
```

일반 Python module은 ANSA를 subprocess로 실행하거나 report를 parsing한다. 일반 module에서 `import ansa`를 사용하지 않는다.

### 5.3 Graph label leakage 방지

학습 입력 graph에는 정답 action, 정답 target length, 정답 divisions를 넣지 않는다. 입력 feature matrix에는 `expected_action_mask`만 허용한다. 정답은 `labels/`에만 저장한다.

## 6. 고정 enum

에이전트는 다음 enum을 임의로 바꾸지 않는다.

```text
Part class:
  SM_FLAT_PANEL
  SM_SINGLE_FLANGE
  SM_L_BRACKET
  SM_U_CHANNEL
  SM_HAT_CHANNEL

Feature type:
  HOLE
  SLOT
  CUTOUT
  BEND
  FLANGE
  OUTER_BOUNDARY

Feature role:
  BOLT
  MOUNT
  RELIEF
  DRAIN
  VENT
  PASSAGE
  STRUCTURAL
  UNKNOWN

Manifest action:
  KEEP_REFINED
  KEEP_WITH_WASHER
  SUPPRESS
  KEEP_WITH_BEND_ROWS
  KEEP_WITH_FLANGE_SIZE
```

## 7. 중단 조건

다음 상황에서는 임의 구현을 계속하지 않는다. `STATUS.md`에 `BLOCKED`를 남기고 사용자 확인이 필요한 항목을 적는다.

```text
1. AMG.md, CDF.md, CONTRACTS.md 사이 enum 또는 schema 충돌
2. label leakage가 발생할 수 있는 graph field 요구
3. ANSA API 함수명을 확인할 수 없어 adapter 내부 binding이 필요한 경우
4. CAD kernel boolean failure가 deterministic하게 재현되지 않는 경우
5. accepted sample 조건을 만족시키기 위해 label을 oracle 결과에 맞춰 사후 수정해야 하는 경우
6. task acceptance criteria가 현재 구현 범위를 초과하는 경우
```

## 8. 세션 종료 산출물

에이전트는 세션 종료 시 다음을 남긴다.

```text
1. 완료한 task ID
2. 변경한 파일 목록
3. 실행한 test command와 결과
4. STATUS.md 업데이트 내용
5. 다음 task ID
6. blocker 또는 risk가 있으면 RISK_REGISTER.md 업데이트
```

## 9. NEXT_AGENT_PROMPT.md handoff rule

`NEXT_AGENT_PROMPT.md` is a rolling next-session handoff prompt, not a first-session-only prompt. At the end of every completed task, update it with the exact current state, the next task ID, explicit in/out of scope, required test command, and known blockers. Keep it aligned with `STATUS.md` and `TASKS.md`.
