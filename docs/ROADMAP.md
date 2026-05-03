# ROADMAP.md

## 1. 개발 전략

전체 구현은 `contract → pure rules → synthetic CAD/data → ANSA oracle → AMG rule-only → AMG model` 순서로 진행한다. ANSA와 CAD kernel은 외부 dependency가 크므로, 수학 공식과 schema를 먼저 고정한다.

```text
P0  Bootstrap contracts and pure rules
P1  CDF rule label engine and file writer
P2  CDF flat/bent CAD generation
P3  B-rep graph extraction and feature matching
P4  ANSA oracle runner and report parser
P5  AMG rule-only manifest pipeline
P6  AMG dataset loader and model baseline
P7  End-to-end integration and scale-up
```

## 2. Phase P0: Bootstrap contracts and pure rules

목표:

```text
- repository skeleton 생성
- shared schema skeleton 작성
- enum과 status/reason 고정
- formula utility와 deterministic label rule 구현
- ANSA/CAD 없이 실행 가능한 unit tests 확보
```

Deliverables:

```text
contracts/*.schema.json
configs/*.json
cad_dataset_factory/cdf/labels/sizing.py
cad_dataset_factory/cdf/labels/amg_rules.py
ai_mesh_generator/labels/sizing_field.py
ai_mesh_generator/labels/rule_manifest.py
tests for formulas and dependency boundaries
```

Exit criteria:

```text
pytest passes without ANSA
manifest examples validate against AMG_MANIFEST_SM_V1
no AMG import in CDF
no ANSA API import outside ansa_scripts
```

## 3. Phase P1: CDF rule label engine and file writer

목표:

```text
- generated parameter/truth objects를 AMG-compatible manifest로 변환
- face/edge/feature auxiliary labels 작성
- sample directory writer 작성
- dataset index and split writer 작성
```

Exit criteria:

```text
one synthetic truth object can produce a complete labels/ directory
all JSON files validate schema
no target action appears in graph input schema
```

## 4. Phase P2: CDF CAD generation

목표:

```text
- CadQuery/OCP 기반 flat panel, single flange, L bracket, U channel, hat channel 생성
- feature placement constraints 적용
- STEP export/re-import validation 구현
- reference midsurface export 구현
```

Exit criteria:

```text
100 generated flat panel samples export STEP successfully
constant thickness validation passes for accepted samples
feature truth files match generated parameters
```

## 5. Phase P3: B-rep graph extraction and feature matching

목표:

```text
- STEP에서 face/edge/coedge/vertex graph 추출
- deterministic feature candidate detection 구현
- truth-to-detected matching report 작성
- graph/brep_graph.npz와 graph_schema.json 작성
```

Exit criteria:

```text
coedge next/prev cycles pass tests
coedge mate pairs pass tests
feature matching recall reaches phase target on generated samples
feature input columns contain expected_action_mask but no target_action_id
```

## 6. Phase P4: ANSA oracle runner

목표:

```text
- external ANSA batch command builder
- ANSA internal script skeleton
- report parser
- mocked ANSA report tests
- requires_ansa smoke test
```

Exit criteria:

```text
mocked oracle pass/fail reports parse correctly
requires_ansa smoke test can run one sample when ANSA_EXECUTABLE is configured
accepted samples have zero hard failed elements in reports
```

## 7. Phase P5: AMG rule-only pipeline

목표:

```text
- input.step + amg_config.json + optional feature_overrides.json
- geometry validation
- B-rep graph extraction
- deterministic feature detection
- deterministic manifest generation
- ANSA execution through AMG adapter when available
```

Exit criteria:

```text
flat panel sample produces valid AMG_MANIFEST_SM_V1
OUT_OF_SCOPE reasons are structured
retry policy is implemented for deterministic retry cases
```

## 8. Phase P6: AMG dataset loader and model baseline

목표:

```text
- CDF dataset loader
- graph tensor batching
- baseline rule predictor wrapper
- simple trainable model skeleton
- output heads and masked loss
```

Exit criteria:

```text
train loop loads dataset without CDF runtime dependency
feature action mask is applied
model output passes rule projector before manifest serialization
```

## 9. Phase P7: End-to-end integration and scale-up

목표:

```text
- CDF generated dataset package
- AMG training on generated dataset
- unseen generated STEP inference
- ANSA quality validation
```

Exit criteria:

```text
accepted generated samples can be loaded by AMG
first-pass and retry success metrics are reported
model metrics and mesh quality metrics are stored in reproducible reports
```
