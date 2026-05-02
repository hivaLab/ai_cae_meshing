# AI 기반 CAE 격자 자동 생성 기법 연구개발 계획서

## Codex 코드 개발 요청용 기준 문서 v0.1

본 계획은 LG전자 기업 과제 **“3D Full Assembly에 대한 CAE 격자 자동 생성”**을 실제 개발 가능한 소프트웨어 프로젝트로 정의한 기준 문서다. 개발 대상은 하나의 연구 아이디어가 아니라, 다음 두 개의 독립 실행 시스템이다.

```text
[시스템 A] AI Mesh Generator, AMG
- 실제 CAD assembly 입력
- AI가 mesh recipe 예측
- ANSA batch meshing으로 solver-ready FEM 생성
- Nastran BDF, QA report, failed region report 출력

[시스템 B] CAE Dataset Factory, CDF
- 학습용 CAD–mesh–label–QA dataset 자동 생성
- AMG와 독립적으로 실행 가능
- synthetic full assembly와 real CAD pseudo-label dataset 생성
- AI 학습용 graph.pt, label parquet, mesh BDF, QA metric 출력
```

중요한 설계 결정은 다음과 같다.

```text
AI가 node와 element connectivity를 직접 생성하지 않는다.

AI는 다음을 예측한다.
1. 부품별 shell / solid / connector / mass-only 전략
2. face / edge 단위 보존, 삭제, 접촉, 체결, midsurface label
3. 국부 mesh size field
4. connection 후보
5. meshing 실패 위험 영역
6. repair action 후보

실제 mesh 생성은 검증된 CAE pre-processor인 ANSA batch meshing backend가 수행한다.
```

본 계획의 1차 대상은 **가전 기구 구조해석용 shell/solid/connector hybrid FEM 자동 생성**이다. 대상 예시는 Base Indoor, Control Box, Door, Cover, Bracket, 판금 box, 얇은 플라스틱 housing, rib, boss, screw 체결부, PCB/motor dummy mass가 포함된 assembly다.

---

# 1. 문제 정의

## 1.1 개발 대상 문제

“3D Full Assembly CAE 격자 자동 생성”은 다음 작업을 자동화하는 것으로 정의한다.

| 구분                     | 자동화 대상                                                                      |
| ---------------------- | --------------------------------------------------------------------------- |
| CAD assembly import    | STEP assembly에서 part, instance, transform, face, edge, solid topology 추출    |
| 부품별 해석 표현 결정           | shell midsurface, solid tetra, connector replacement, mass-only, exclude 결정 |
| geometry cleanup       | 작은 hole, fillet, sliver face, short edge, logo, emboss 제거 또는 보존             |
| shell midsurface 생성    | 얇은 판금/플라스틱 부품의 neutral surface 생성 및 thickness property 부여                   |
| solid meshing 준비       | 두꺼운 hinge, insert, boss, structural block의 watertight solid 준비              |
| local mesh size 결정     | 체결부, contact face, rib root, hole, curvature 영역 size 조절                     |
| assembly connection 생성 | screw, tied contact, adhesive, hinge, mass connector 자동 생성                  |
| mesh 품질 검사             | aspect, skew, warpage, Jacobian, free edge, duplicate node, property 누락 검사  |
| repair loop            | 실패 영역을 local remesh, defeature 강화, washer 조정, size 감소로 자동 보정                |
| solver deck export     | Nastran BDF 및 include 파일 생성                                                 |
| QA report              | part별 pass/fail, 품질 metric, manual review list 생성                           |

---

## 1.2 1차 개발 범위

본 과제의 1차 개발 범위는 다음으로 고정한다.

```text
제품군:
- 에어컨 실내기, 공조기 base indoor, control box, door, cover, bracket류

해석 유형:
- 선형 정적해석
- 모달해석
- 주파수응답해석
- 진동 내구해석용 구조 FEM

요소 표현:
- Shell: CQUAD4, CTRIA3
- Solid: CTETRA10
- Connector: RBE2, RBE3, CBUSH
- Mass: CONM2

Solver deck:
- Nastran BDF
```

1차 제외 범위는 다음과 같다.

```text
- CFD volume mesh
- 열유동 mesh
- 전자기 mesh
- 사출성형 mesh
- crash / explicit nonlinear full vehicle 수준 mesh
- 접촉 비선형 상세해석용 고정밀 bolt thread mesh
- AI가 element connectivity를 직접 생성하는 end-to-end mesh generator
```

---

# 2. 전체 시스템 아키텍처

## 2.1 시스템 분리 원칙

전체 프로젝트는 반드시 다음 두 시스템으로 분리한다.

```text
AMG: AI Mesh Generator
- 실제 기업 CAD 입력을 받아 solver-ready mesh를 생성하는 운영 시스템

CDF: CAE Dataset Factory
- AI 학습용 데이터를 자동 생성하는 독립 시스템
- AMG를 import하거나 호출하지 않는다
- AMG와 schema만 공유한다
```

```text
cae_mesh_project/
│
├─ shared_schema/
│  ├─ input_package_schema.json
│  ├─ mesh_profile_schema.json
│  ├─ mesh_recipe_schema.json
│  ├─ label_schema.json
│  ├─ qa_metric_schema.json
│  └─ graph_schema.json
│
├─ ai_mesh_generator/        # AMG
│
├─ cae_dataset_factory/      # CDF
│
├─ training_pipeline/
│
├─ ansa_scripts/
│
├─ configs/
│
├─ tests/
│
└─ docs/
```

AMG와 CDF는 다음 파일만 공유한다.

```text
- input package schema
- mesh recipe schema
- graph schema
- label schema
- QA metric schema
- material schema
- connection schema
```

---

## 2.2 데이터 흐름 요약

```text
[AMG 운영 흐름]

LGE_CAE_MESH_JOB.zip
        ↓
입력 검증
        ↓
STEP B-Rep import / geometry healing
        ↓
B-Rep graph + assembly graph 생성
        ↓
AI inference
        ↓
mesh_recipe.json 생성
        ↓
engineering guard rule 적용
        ↓
ANSA batch meshing
        ↓
quality check + repair loop
        ↓
Nastran BDF export
        ↓
MESH_RESULT.zip
```

```text
[CDF 학습 데이터 생성 흐름]

generation_spec.yaml
        ↓
parametric CAD part 생성
        ↓
geometry variation + defect injection
        ↓
port-based full assembly 생성
        ↓
oracle label 생성
        ↓
STEP export + persistent face ID mapping
        ↓
ANSA batch meshing
        ↓
quality metric / failure label 생성
        ↓
B-Rep graph export
        ↓
CAE_MESH_DATASET_Vxxx
```

---

# 3. AMG 입력 데이터 정의

AMG의 입력은 단일 zip package로 고정한다.

```text
LGE_CAE_MESH_JOB.zip
│
├─ geometry/
│  └─ assembly.step
│
├─ metadata/
│  ├─ manifest.json
│  ├─ product_tree.json
│  ├─ part_attributes.csv
│  ├─ material_library.json
│  ├─ connections.csv
│  ├─ boundary_named_sets.json
│  └─ mesh_profile.yaml
│
└─ optional/
   ├─ analyst_override.yaml
   └─ previous_mesh_reference.bdf
```

CAD 교환 형식은 **STEP AP242 B-Rep assembly**로 고정한다. STEP은 제품 모델 데이터 교환을 위한 ISO 10303 계열 표준으로, AP242는 managed model-based 3D engineering을 대상으로 하는 application protocol이다. ([ISO][1])

---

## 3.1 `geometry/assembly.step`

`assembly.step`은 다음 정보를 포함해야 한다.

| 항목           | 요구사항                                        |
| ------------ | ------------------------------------------- |
| 형식           | STEP AP242                                  |
| 단위           | mm                                          |
| geometry 표현  | B-Rep solid/surface                         |
| topology     | solid, shell, face, edge, vertex            |
| surface type | plane, cylinder, cone, sphere, torus, NURBS |
| curve type   | line, circle, ellipse, spline               |
| assembly 구조  | part, instance, transform matrix            |
| part 식별자     | `part_uid`와 mapping 가능해야 함                  |
| tolerance    | 기본 0.01 mm 기준                               |

NX `.prt`, CATIA `.CATPart/.CATProduct`, Parasolid `.x_t`, JT 파일은 AMG의 직접 입력으로 받지 않는다. 기업 내부 CAD system에서 사전 변환기를 통해 `assembly.step`으로 변환한 뒤 AMG에 넣는다.

---

## 3.2 `metadata/manifest.json`

```json
{
  "job_id": "LGE_BI_2026_0001",
  "product_family": "BaseIndoor",
  "unit": "mm",
  "geometry_file": "geometry/assembly.step",
  "solver": "NASTRAN",
  "analysis_type": [
    "linear_static",
    "modal",
    "frequency_response"
  ],
  "mesh_profile": "metadata/mesh_profile.yaml",
  "product_tree_file": "metadata/product_tree.json",
  "part_attribute_file": "metadata/part_attributes.csv",
  "connection_file": "metadata/connections.csv",
  "boundary_named_set_file": "metadata/boundary_named_sets.json"
}
```

필수 검증 조건:

```text
- unit == "mm"
- solver == "NASTRAN"
- geometry_file 존재
- part_attribute_file 존재
- material_library.json 존재
- mesh_profile.yaml 존재
```

---

## 3.3 `metadata/product_tree.json`

```json
{
  "assembly_uid": "ASM_BASE_INDOOR_001",
  "children": [
    {
      "instance_uid": "INST_CONTROL_BOX_001",
      "part_uid": "PART_CONTROL_BOX_A",
      "part_name": "Control_Box",
      "parent_uid": "ASM_BASE_INDOOR_001",
      "transform_4x4": [
        [1.0, 0.0, 0.0, 120.0],
        [0.0, 1.0, 0.0, 35.0],
        [0.0, 0.0, 1.0, 10.0],
        [0.0, 0.0, 0.0, 1.0]
      ]
    }
  ]
}
```

검증 조건:

```text
- 모든 part_uid는 part_attributes.csv에 존재
- 모든 instance_uid는 unique
- transform_4x4는 4x4 matrix
- determinant가 0에 가까운 transform 금지
```

---

## 3.4 `metadata/part_attributes.csv`

```csv
part_uid,part_name,material_id,manufacturing_process,nominal_thickness_mm,min_thickness_mm,max_thickness_mm,component_role,mass_handling,mesh_priority
PART_CONTROL_BOX_A,Control_Box,SGCC_0p8,sheet_metal,0.8,0.75,0.85,control_box,mesh,high
PART_BASE_DOOR_B,Base_Door,ABS_GF20,injection_plastic,2.2,1.8,3.5,cover,mesh,normal
PART_SCREW_M3_01,Screw_M3,STEEL,purchased_fastener,0,0,0,fastener,connector,high
PART_PCB_01,PCB_Assy,PCB_EQUIV,electronic_module,1.6,1.6,1.6,electronic_module,mass_only,low
```

허용 값은 다음으로 고정한다.

```text
manufacturing_process:
- sheet_metal
- injection_plastic
- machined_metal
- purchased_fastener
- electronic_module
- rubber_part
- unknown

component_role:
- base
- cover
- door
- bracket
- control_box
- hinge
- boss
- fastener
- electronic_module
- motor
- duct
- decoration
- unknown

mass_handling:
- mesh
- simplified_solid
- connector
- mass_only
- exclude
```

---

## 3.5 `metadata/material_library.json`

```json
{
  "SGCC_0p8": {
    "material_name": "SGCC",
    "E_MPa": 210000.0,
    "nu": 0.30,
    "rho_tonne_per_mm3": 7.85e-9
  },
  "ABS_GF20": {
    "material_name": "ABS_GF20",
    "E_MPa": 5200.0,
    "nu": 0.38,
    "rho_tonne_per_mm3": 1.20e-9
  }
}
```

검증 조건:

```text
- E_MPa > 0
- 0 < nu < 0.5
- rho_tonne_per_mm3 > 0
- part_attributes.csv의 모든 material_id가 material_library.json에 존재
```

---

## 3.6 `metadata/connections.csv`

```csv
connection_uid,type,master_part_uid,slave_part_uid,feature_hint,diameter_mm,stiffness_profile,washer_radius_mm
CONN_0001,screw,PART_CONTROL_BOX_A,PART_BASE_DOOR_B,hole_pair_auto,3.0,M3_default,5.0
CONN_0002,tied_contact,PART_BRACKET_A,PART_PANEL_B,face_pair_auto,0,tied_default,0
CONN_0003,adhesive,PART_COVER_A,PART_FRAME_A,named_surface_ADH_01,0,adhesive_default,0
```

허용 connection type:

```text
- screw
- bolt
- rivet
- tied_contact
- adhesive
- hinge
- snap_fit
- mass_connector
```

최종 connector type은 AI 추론보다 `connections.csv`를 우선한다.

---

## 3.7 `metadata/boundary_named_sets.json`

```json
{
  "fixed_faces": [
    {
      "set_name": "FIX_BASE_MOUNT",
      "part_uid": "PART_BASE_A",
      "cad_face_hint": "mounting_bottom_faces"
    }
  ],
  "load_faces": [
    {
      "set_name": "LOAD_MOTOR_WEIGHT",
      "part_uid": "PART_MOTOR_BRACKET_A",
      "cad_face_hint": "motor_mounting_faces"
    }
  ],
  "review_faces": [
    {
      "set_name": "CAE_REVIEW_ZONE_01",
      "part_uid": "PART_CONTROL_BOX_A",
      "cad_face_hint": "connector_dense_region"
    }
  ]
}
```

규칙:

```text
- named boundary face는 defeature 금지
- load face는 local mesh size 완화 금지
- review face는 QA report에 무조건 포함
```

---

## 3.8 `metadata/mesh_profile.yaml`

```yaml
solver: NASTRAN
analysis_type: structural_modal

element_policy:
  shell_element: CQUAD4_CTRIA3
  solid_element: CTETRA10
  connector_elements:
    - RBE2
    - RBE3
    - CBUSH
    - CONM2

default_size:
  shell_target_mm: 5.0
  shell_min_mm: 1.5
  solid_target_mm: 4.0
  solid_min_mm: 1.2
  growth_rate: 1.35

defeature_rule:
  remove_hole_diameter_below_mm: 2.0
  remove_fillet_radius_below_mm: 1.0
  remove_slot_width_below_mm: 1.5
  preserve_connection_features: true
  preserve_boundary_named_sets: true

quality_shell:
  quad_ratio_min: 0.80
  aspect_ratio_max: 5.0
  skew_deg_max: 60.0
  warpage_deg_max: 15.0
  jacobian_min: 0.60
  min_angle_deg: 30.0
  max_angle_deg: 150.0

quality_solid:
  negative_jacobian_allowed: 0
  scaled_jacobian_min: 0.20
  aspect_ratio_max: 8.0
  min_dihedral_deg: 10.0
  max_dihedral_deg: 165.0

acceptance:
  fatal_error_allowed: 0
  property_assignment_rate_min: 1.0
  material_assignment_rate_min: 1.0
  in_scope_part_mesh_success_rate_min: 0.70
  cad_fe_mass_error_percent_max: 3.0
```

---

# 4. AMG 출력 데이터 정의

AMG의 최종 출력은 `MESH_RESULT.zip`으로 고정한다.

```text
MESH_RESULT.zip
│
├─ solver_deck/
│  ├─ model_final.bdf
│  ├─ materials.inc
│  ├─ properties.inc
│  ├─ connections.inc
│  └─ sets.inc
│
├─ native/
│  └─ model_final.ansa
│
├─ report/
│  ├─ qa_report.html
│  ├─ qa_metrics_global.json
│  ├─ qa_metrics_part.csv
│  ├─ qa_metrics_element.parquet
│  ├─ failed_regions.csv
│  └─ manual_review_list.csv
│
├─ viewer/
│  └─ mesh_preview.vtk
│
└─ metadata/
   ├─ mesh_recipe_final.json
   ├─ ai_prediction.json
   ├─ engineering_guard_log.json
   ├─ repair_history.json
   ├─ mesh_meta.json
   └─ cad_to_mesh_mapping.parquet
```

---

## 4.1 `solver_deck/model_final.bdf`

Nastran BDF card 사용 범위:

| Card     | 용도                              |
| -------- | ------------------------------- |
| `GRID`   | node                            |
| `CQUAD4` | shell quad                      |
| `CTRIA3` | shell triangle                  |
| `CTETRA` | 10-node tetra solid             |
| `PSHELL` | shell property                  |
| `PSOLID` | solid property                  |
| `MAT1`   | isotropic material              |
| `RBE2`   | rigid spider                    |
| `RBE3`   | distributed coupling            |
| `CBUSH`  | screw/bolt equivalent stiffness |
| `CONM2`  | lumped mass                     |
| `SET`    | node/element/face set           |

BDF 검증은 pyNastran으로 수행한다. pyNastran은 Nastran BDF reader/writer를 제공하며 BDF card 객체 접근, mass/area 등 속성 접근, BDF writing을 지원한다. ([pyNastran Documentation][2])

---

## 4.2 `metadata/mesh_recipe_final.json`

AI 예측과 guard rule 보정 후 실제 ANSA에 전달된 최종 recipe다.

```json
{
  "job_id": "LGE_BI_2026_0001",
  "parts": {
    "PART_CONTROL_BOX_A": {
      "strategy": "SHELL_MIDSURFACE",
      "target_size_mm": 5.0,
      "min_size_mm": 1.5,
      "thickness_mm": 0.8,
      "material_id": "SGCC_0p8",
      "property_type": "PSHELL",
      "quality_profile": "shell_thin_metal"
    },
    "PART_HINGE_A": {
      "strategy": "SOLID_TETRA",
      "target_size_mm": 3.0,
      "min_size_mm": 1.0,
      "material_id": "STEEL",
      "property_type": "PSOLID",
      "quality_profile": "solid_small_structural"
    }
  },
  "faces": {
    "FACE_001232": {
      "label": "PRESERVE_BOLT_HOLE",
      "target_size_mm": 0.8,
      "min_size_mm": 0.5,
      "washer_ring_count": 3,
      "defeature_action": "keep"
    },
    "FACE_001245": {
      "label": "REMOVE_SMALL_FILLET",
      "radius_mm": 0.6,
      "defeature_action": "remove"
    }
  },
  "connections": {
    "CONN_0001": {
      "type": "screw",
      "element_model": "RBE2_CBUSH_RBE2",
      "master_part_uid": "PART_CONTROL_BOX_A",
      "slave_part_uid": "PART_BASE_DOOR_B",
      "diameter_mm": 3.0,
      "washer_radius_mm": 5.0
    }
  }
}
```

---

## 4.3 품질 기준

### Shell mesh 기준

| 항목             |          기준 |
| -------------- | ----------: |
| quad ratio     |      80% 이상 |
| tria ratio     |      20% 이하 |
| aspect ratio   |      5.0 이하 |
| skew           |      60° 이하 |
| warpage        |      15° 이하 |
| Jacobian       |     0.60 이상 |
| min angle      |      30° 이상 |
| max angle      |     150° 이하 |
| free edge      | 의도된 외곽 외 0개 |
| duplicate node |          0개 |
| shell normal   |    part별 일관 |

### Solid mesh 기준

| 항목                |       기준 |
| ----------------- | -------: |
| element type      | CTETRA10 |
| negative Jacobian |       0개 |
| scaled Jacobian   |  0.20 이상 |
| aspect ratio      |   8.0 이하 |
| min dihedral      |   10° 이상 |
| max dihedral      |  165° 이하 |
| unreferenced node |       0개 |

### Assembly 기준

| 항목                              | PoC 기준 | Pilot 기준 |  운영 기준 |
| ------------------------------- | -----: | -------: | -----: |
| in-scope part mesh success rate | 70% 이상 |   80% 이상 | 90% 이상 |
| material assignment             |   100% |     100% |   100% |
| property assignment             |   100% |     100% |   100% |
| connector metadata 반영률          |   100% |     100% |   100% |
| BDF parse error                 |     0개 |       0개 |     0개 |
| fatal QA error                  |     0개 |       0개 |     0개 |
| CAD 대비 FE mass error            |  3% 이하 |    3% 이하 |  3% 이하 |

---

# 5. AI 모델 구성

## 5.1 모델 이름

```text
BRepAssemblyNet
```

구현 framework는 PyTorch + PyTorch Geometric으로 고정한다. PyTorch Geometric은 PyTorch 기반 graph neural network 구현 및 학습 library로 structured data graph 처리를 지원한다. ([PyTorch Geometric Documentation][3])

---

## 5.2 AI의 역할

AI는 다음 6개 예측을 수행한다.

```text
1. PartStrategyHead
   - part별 mesh 표현 방식 예측

2. FaceSemanticHead
   - face별 보존/삭제/체결/접촉/midsurface label 예측

3. EdgeSemanticHead
   - edge별 sharp edge, hole edge, fillet edge, short edge label 예측

4. SizeFieldHead
   - face/edge별 target mesh size 예측

5. ConnectionCandidateHead
   - part-part connection 후보와 type 예측

6. FailureRiskHead + RepairActionHead
   - meshing 실패 위험과 repair action 예측
```

AI가 직접 생성하지 않는 것:

```text
- node coordinate list
- element connectivity
- BDF card 직접 생성
- final mesh topology
```

---

## 5.3 입력 graph 구조

AI 입력은 PyTorch Geometric `HeteroData`로 저장한다.

```text
node types:
- face
- edge
- part
- contact_candidate
- connection

edge types:
- face shares_edge face
- face incident_to edge
- edge incident_to face
- face belongs_to part
- part has_face face
- part near part
- face contact_candidate face
- connection links part
- connection links face
```

---

## 5.4 Node feature 정의

### `face` node feature

```text
x_face = [
  area_log,
  perimeter_log,
  surface_type_onehot,
  centroid_x_norm,
  centroid_y_norm,
  centroid_z_norm,
  normal_x,
  normal_y,
  normal_z,
  curvature_mean,
  curvature_max,
  uv_bbox_u,
  uv_bbox_v,
  loop_count,
  inner_loop_count,
  estimated_thickness_mm,
  distance_to_nearest_part_mm,
  is_named_boundary,
  is_connection_related,
  material_embedding,
  manufacturing_process_embedding
]
```

### `edge` node feature

```text
x_edge = [
  length_log,
  curve_type_onehot,
  radius_if_circular,
  dihedral_angle_deg,
  convex_flag,
  concave_flag,
  adjacent_face_area_ratio,
  is_sharp_edge,
  is_hole_edge_candidate,
  is_short_edge_candidate
]
```

### `part` node feature

```text
x_part = [
  bbox_x_log,
  bbox_y_log,
  bbox_z_log,
  volume_log,
  surface_area_log,
  volume_to_area_ratio,
  nominal_thickness_mm,
  min_thickness_mm,
  max_thickness_mm,
  material_embedding,
  manufacturing_process_embedding,
  component_role_embedding,
  mass_handling_embedding,
  mesh_priority_embedding
]
```

### `contact_candidate` node feature

```text
x_contact_candidate = [
  master_part_embedding,
  slave_part_embedding,
  gap_mm,
  overlap_mm,
  opposing_normal_dot,
  projected_overlap_ratio,
  contact_area_estimate_log,
  is_metadata_connection
]
```

### `connection` node feature

```text
x_connection = [
  connection_type_embedding,
  diameter_mm,
  washer_radius_mm,
  axis_direction_x,
  axis_direction_y,
  axis_direction_z,
  stiffness_profile_embedding,
  master_part_embedding,
  slave_part_embedding
]
```

---

## 5.5 Network architecture

```text
Input: HeteroData
        ↓
Feature normalization
        ↓
Heterogeneous Graph Transformer Encoder
- hidden_dim = 256
- num_layers = 4
- attention_heads = 8
- dropout = 0.10
        ↓
Multi-head prediction
        ├─ PartStrategyHead
        ├─ FaceSemanticHead
        ├─ EdgeSemanticHead
        ├─ SizeFieldHead
        ├─ ConnectionCandidateHead
        ├─ FailureRiskHead
        └─ RepairActionHead
```

---

## 5.6 Head별 출력

### 5.6.1 `PartStrategyHead`

입력:

```text
part node embedding
```

출력 class:

```text
- SHELL_MIDSURFACE
- SOLID_TETRA
- CONNECTOR_REPLACEMENT
- MASS_ONLY
- EXCLUDE_FROM_ANALYSIS
- MANUAL_REVIEW
```

출력 예:

```json
{
  "part_uid": "PART_CONTROL_BOX_A",
  "strategy": "SHELL_MIDSURFACE",
  "confidence": 0.94
}
```

---

### 5.6.2 `FaceSemanticHead`

입력:

```text
face node embedding
```

출력 class:

```text
- PRESERVE_STRUCTURAL
- REMOVE_SMALL_HOLE
- REMOVE_SMALL_FILLET
- REMOVE_LOGO_EMBOSS
- PRESERVE_BOLT_HOLE
- CONTACT_FACE
- LOAD_BC_FACE
- MIDSURFACE_SOURCE
- THICKNESS_TRANSITION
- MANUAL_REVIEW
```

---

### 5.6.3 `EdgeSemanticHead`

출력 class:

```text
- NORMAL_EDGE
- SHARP_FEATURE_EDGE
- HOLE_EDGE
- FILLET_EDGE
- SHORT_EDGE_REMOVE
- WASHER_RING_EDGE
- MIDSURFACE_BOUNDARY_EDGE
- MANUAL_REVIEW
```

---

### 5.6.4 `SizeFieldHead`

입력:

```text
face 또는 edge embedding
```

출력:

```text
- h_target_mm
- h_min_mm
- growth_rate
- washer_ring_count
- curvature_refinement_flag
```

출력 예:

```json
{
  "entity_type": "face",
  "entity_uid": "FACE_001232",
  "h_target_mm": 0.8,
  "h_min_mm": 0.5,
  "growth_rate": 1.25,
  "washer_ring_count": 3,
  "curvature_refinement_flag": true
}
```

---

### 5.6.5 `ConnectionCandidateHead`

출력:

```text
- candidate_exists: true/false
- connection_type
- master_part_uid
- slave_part_uid
- master_face_uid
- slave_face_uid
- axis_origin
- axis_direction
- confidence
```

connection type class:

```text
- screw
- bolt
- rivet
- tied_contact
- adhesive
- hinge
- snap_fit
- mass_connector
- no_connection
```

---

### 5.6.6 `FailureRiskHead`

출력 class:

```text
- NO_RISK
- SLIVER_FACE_RISK
- SHORT_EDGE_RISK
- THIN_GAP_RISK
- OVERLAP_RISK
- MIDSURFACE_PAIRING_RISK
- SOLID_TETRA_FAILURE_RISK
- CONNECTOR_MISMATCH_RISK
- NONMANIFOLD_RISK
```

---

### 5.6.7 `RepairActionHead`

출력 class:

```text
- NO_ACTION
- SUPPRESS_SMALL_FEATURE
- MERGE_SLIVER_FACE
- REDUCE_LOCAL_SIZE
- INCREASE_WASHER_RADIUS
- INCREASE_RING_COUNT
- RECREATE_MIDSURFACE
- SWITCH_TO_SOLID
- MARK_MANUAL_REVIEW
```

---

## 5.7 Loss 구성

```text
L_total =
  1.0 * L_part_strategy_CE
+ 1.0 * L_face_semantic_CE
+ 0.5 * L_edge_semantic_CE
+ 1.0 * L_size_smoothL1
+ 1.0 * L_connection_CE_BCE
+ 0.7 * L_failure_risk_CE
+ 0.5 * L_repair_action_CE
```

데이터 source별 loss weight:

```text
synthetic_strong_label: 1.0
real_cad_auto_mesh_pseudo: 0.2 ~ 0.5
manual_validated_real: 1.0
```

---

## 5.8 Engineering guard rule

AI 출력은 그대로 실행하지 않는다. 다음 deterministic guard rule을 항상 적용한다.

| 조건                                                | 강제 처리                    |
| ------------------------------------------------- | ------------------------ |
| named boundary face                               | defeature 금지             |
| connection 관련 hole                                | 삭제 금지                    |
| material 누락                                       | mesh 생성 금지               |
| shell thickness <= 0                              | mesh 생성 금지               |
| AI confidence < 0.70                              | manual review            |
| purchased_fastener                                | connector replacement 우선 |
| electronic_module + mass_handling=mass_only       | CONM2 생성                 |
| small hole이 connection metadata에 포함               | washer mesh 생성           |
| fillet radius < profile threshold이고 BC/contact 무관 | suppress                 |
| local size < profile min                          | min size로 clip           |
| BDF property 누락                                   | export 실패 처리             |

---

# 6. AMG 전체 파이프라인

## 6.1 단계별 처리 흐름

```text
[1] Input package validation
[2] STEP import and geometry healing
[3] B-Rep / assembly feature extraction
[4] Graph construction
[5] AI inference
[6] Engineering guard rule
[7] Mesh recipe generation
[8] ANSA batch meshing
[9] Quality check
[10] Repair loop
[11] Assembly connection / property / material assignment
[12] BDF export
[13] BDF validation
[14] QA report generation
[15] MESH_RESULT.zip packaging
```

---

## 6.2 [1] Input validation

모듈:

```text
ai_mesh_generator/input/validator.py
```

검사 항목:

```text
- zip 구조 검사
- manifest schema 검사
- STEP 파일 존재 여부
- product_tree와 part_attributes 매핑률 100%
- material_library 매핑률 100%
- connection 참조 part 존재 여부
- mesh_profile 값 범위 검사
- unit mm 여부
```

실패 시:

```text
- fatal validation error
- ANSA 실행 금지
- validation_report.json 생성
```

---

## 6.3 [2] STEP import and geometry healing

모듈:

```text
ai_mesh_generator/cad/step_importer.py
ai_mesh_generator/cad/geometry_healer.py
```

Open CASCADE Technology는 STEP/IGES interface와 shape healing 기능을 제공하므로 B-Rep parsing, topology traversal, geometry healing에 사용한다. ([Open CASCADE][4])

처리:

```text
- STEP file load
- part별 shape 분리
- face, edge, vertex 탐색
- sewing tolerance 0.01 mm 적용
- sliver face 후보 탐지
- short edge 후보 탐지
- non-manifold 후보 탐지
- part bounding box 계산
```

---

## 6.4 [3] Feature extraction

모듈:

```text
ai_mesh_generator/cad/feature_extractor.py
```

추출 feature:

```text
face:
- area
- perimeter
- centroid
- normal
- surface type
- curvature
- loop count
- inner loop count
- estimated thickness
- nearest part distance

edge:
- length
- curve type
- radius
- adjacent face angle
- convex/concave
- short edge flag

part:
- bbox
- volume
- surface area
- volume/surface ratio
- nominal thickness
- material
- process
- role
```

특징 탐지 rule:

```text
hole_candidate:
- cylindrical face
- circular edge loop
- diameter within configured range

fillet_candidate:
- cylindrical or torus face
- radius below threshold
- adjacent smooth transition

thin_wall_candidate:
- manufacturing_process in {sheet_metal, injection_plastic}
- nominal_thickness_mm <= 4.0
- bbox_min_dimension / nominal_thickness_mm >= 8

contact_candidate:
- part-part distance <= 0.5 mm
- opposing normal dot <= -0.85
- projected overlap ratio >= 0.3

screw_hole_pair_candidate:
- two cylindrical hole faces
- axis nearly coaxial
- diameter difference <= 20%
- part-part gap <= 1.0 mm
```

---

## 6.5 [4] Graph construction

모듈:

```text
ai_mesh_generator/graph/graph_builder.py
```

출력:

```text
workdir/graph/input_graph.pt
workdir/graph/brep_graph.json
workdir/graph/assembly_graph.json
```

`graph.pt` 구조:

```python
data["face"].x
data["edge"].x
data["part"].x
data["contact_candidate"].x
data["connection"].x

data["face", "shares_edge", "face"].edge_index
data["face", "incident_to", "edge"].edge_index
data["face", "belongs_to", "part"].edge_index
data["part", "near", "part"].edge_index
data["face", "contact_candidate", "face"].edge_index
data["connection", "links", "part"].edge_index
```

---

## 6.6 [5] AI inference

모듈:

```text
ai_mesh_generator/inference/predictor.py
```

입력:

```text
input_graph.pt
trained_model.pt
normalization_stats.json
```

출력:

```text
ai_prediction.json
```

예:

```json
{
  "parts": {
    "PART_CONTROL_BOX_A": {
      "strategy": "SHELL_MIDSURFACE",
      "confidence": 0.94
    }
  },
  "faces": {
    "FACE_001232": {
      "label": "PRESERVE_BOLT_HOLE",
      "confidence": 0.91,
      "h_target_mm": 0.8,
      "h_min_mm": 0.5
    }
  },
  "failure_risk": {
    "FACE_008881": {
      "risk": "SLIVER_FACE_RISK",
      "confidence": 0.87,
      "repair_action": "MERGE_SLIVER_FACE"
    }
  }
}
```

---

## 6.7 [6] Engineering guard

모듈:

```text
ai_mesh_generator/recipe/guard.py
```

입력:

```text
ai_prediction.json
metadata/*
mesh_profile.yaml
```

출력:

```text
mesh_recipe_guarded.json
engineering_guard_log.json
```

guard log 예:

```json
{
  "overrides": [
    {
      "entity_uid": "FACE_001232",
      "ai_action": "REMOVE_SMALL_HOLE",
      "guarded_action": "KEEP",
      "reason": "connection_related_feature"
    }
  ]
}
```

---

## 6.8 [7] Mesh recipe generation

모듈:

```text
ai_mesh_generator/recipe/recipe_writer.py
```

출력:

```text
mesh_recipe_final.json
ansa_batch_config.json
```

ANSA에 전달할 최소 recipe:

```json
{
  "step_file": "geometry/assembly.step",
  "unit": "mm",
  "parts": [
    {
      "part_uid": "PART_CONTROL_BOX_A",
      "strategy": "SHELL_MIDSURFACE",
      "target_size_mm": 5.0,
      "min_size_mm": 1.5,
      "thickness_mm": 0.8,
      "material_id": "SGCC_0p8"
    }
  ],
  "defeature_actions": [
    {
      "face_uid": "FACE_001245",
      "action": "remove",
      "reason": "small_fillet"
    }
  ],
  "connections": [
    {
      "connection_uid": "CONN_0001",
      "type": "screw",
      "element_model": "RBE2_CBUSH_RBE2",
      "washer_radius_mm": 5.0
    }
  ]
}
```

---

## 6.9 [8] ANSA batch meshing

모듈:

```text
ai_mesh_generator/meshing/ansa_runner.py
ansa_scripts/amg_batch_mesh.py
```

ANSA는 shell/volume meshing, CAD clean-up, batch meshing, model build-up 기능을 제공하는 CAE pre-processor이므로 본 과제의 meshing backend로 고정한다. ([BETA CAE Systems][5])

실행 명령:

```bash
ansa64 -b -exec ansa_scripts/amg_batch_mesh.py -- \
  --config workdir/ansa_batch_config.json \
  --recipe workdir/mesh_recipe_final.json \
  --output workdir/mesh
```

ANSA script 내부 처리:

```python
def main():
    config = load_json("--config")
    recipe = load_json("--recipe")

    import_step(config["step_file"])
    apply_geometry_healing(tolerance_mm=0.01)

    for part in recipe["parts"]:
        if part["strategy"] == "SHELL_MIDSURFACE":
            create_midsurface(part)
            apply_shell_mesh_params(part)
        elif part["strategy"] == "SOLID_TETRA":
            prepare_solid_volume(part)
            apply_solid_mesh_params(part)
        elif part["strategy"] == "CONNECTOR_REPLACEMENT":
            suppress_fastener_geometry(part)
        elif part["strategy"] == "MASS_ONLY":
            create_conm2_representation(part)

    apply_defeature_actions(recipe["defeature_actions"])
    generate_mesh()
    run_quality_improvement()
    create_connections(recipe["connections"])
    assign_materials_and_properties(recipe)
    export_bdf("model_final.bdf")
    export_ansa_db("model_final.ansa")
    export_raw_quality("ansa_quality_raw.json")
```

---

## 6.10 [9] Quality check

모듈:

```text
ai_mesh_generator/qa/quality_checker.py
ai_mesh_generator/qa/shell_quality.py
ai_mesh_generator/qa/solid_quality.py
ai_mesh_generator/qa/connector_quality.py
```

검사:

```text
- shell aspect
- shell skew
- shell warpage
- shell Jacobian
- solid scaled Jacobian
- solid dihedral angle
- duplicate node
- free edge
- property 누락
- material 누락
- connector 누락
- unreferenced node
- FE mass vs CAD mass
```

---

## 6.11 [10] Repair loop

모듈:

```text
ai_mesh_generator/repair/repair_planner.py
ai_mesh_generator/repair/repair_executor.py
```

최대 반복:

```text
max_repair_iteration = 3
```

repair rule:

| 문제                  | repair action                      |
| ------------------- | ---------------------------------- |
| aspect ratio 초과     | local size 감소, remesh              |
| skew 초과             | edge swap, local remesh            |
| warpage 초과          | midsurface 재생성, face split         |
| Jacobian 낮음         | sliver face 제거, remesh             |
| free edge           | node equivalence, topology healing |
| solid tet 실패        | local size 감소, tiny face 제거        |
| connector washer 불량 | washer radius 증가, ring count 증가    |
| hole pair mismatch  | manual review                      |

repair history 예:

```json
{
  "iterations": [
    {
      "iteration": 1,
      "region_uid": "REGION_00042",
      "violation": "warpage",
      "action": "RECREATE_MIDSURFACE",
      "before": {
        "max_warpage_deg": 22.5
      },
      "after": {
        "max_warpage_deg": 11.2
      },
      "success": true
    }
  ]
}
```

---

## 6.12 [11] BDF validation and packaging

모듈:

```text
ai_mesh_generator/bdf/bdf_validator.py
ai_mesh_generator/output/package_writer.py
```

검증:

```text
- BDF read success
- GRID count > 0
- element count > 0
- duplicate ID count = 0
- missing property count = 0
- missing material count = 0
- invalid card count = 0
- fatal QA error count = 0
```

---

# 7. 독립형 학습 데이터셋 생성 모듈, CDF

## 7.1 CDF 목적

CDF는 사람이 CAD–mesh pair와 label을 수작업으로 만드는 문제를 해결하기 위한 독립형 시스템이다.

CDF는 다음을 자동 생성한다.

```text
- synthetic CAD part
- synthetic full assembly
- STEP assembly
- material / part / connection metadata
- oracle mesh recipe
- ANSA-generated mesh
- Nastran BDF
- face / edge / part / connection label
- mesh quality metric
- failure / repair label
- AI 학습용 B-Rep graph
```

CDF는 AMG를 호출하지 않는다. CDF는 자체 oracle rule과 자체 ANSA batch script로 dataset을 생성한다.

---

## 7.2 CDF 입력 구조

```text
CAE_DATASET_FACTORY_INPUT/
│
├─ generation_spec.yaml
├─ template_library/
│  ├─ plastic_base.yaml
│  ├─ ribbed_cover.yaml
│  ├─ sheet_metal_box.yaml
│  ├─ bracket_l.yaml
│  ├─ bracket_u.yaml
│  ├─ control_box.yaml
│  ├─ screw_pattern.yaml
│  ├─ pcb_dummy.yaml
│  └─ motor_dummy.yaml
│
├─ material_library.json
├─ connection_library.json
├─ mesh_profile_library/
│  ├─ structural_modal_shell_solid.yaml
│  └─ vibration_durability.yaml
│
├─ defect_injection_rule.yaml
│
└─ optional_real_cad_seed/
   ├─ geometry/
   │  └─ assembly.step
   └─ metadata/
      ├─ manifest.json
      ├─ product_tree.json
      ├─ part_attributes.csv
      ├─ material_library.json
      ├─ connections.csv
      └─ mesh_profile.yaml
```

---

## 7.3 `generation_spec.yaml`

```yaml
dataset_id: LGE_SYNTH_CAE_MESH_V001
random_seed: 20260430

num_assemblies:
  synthetic_strong_label: 10000
  real_auto_label: 500

product_family: BaseIndoor

assembly_scale:
  min_part_count: 40
  max_part_count: 220
  min_connection_count: 30
  max_connection_count: 600

geometry_unit: mm

part_distribution:
  sheet_metal_box: 0.12
  plastic_base: 0.18
  ribbed_cover: 0.20
  bracket_l: 0.18
  bracket_u: 0.08
  control_box: 0.05
  pcb_dummy: 0.04
  motor_dummy: 0.03
  purchased_fastener: 0.12

thickness_distribution:
  sheet_metal_mm:
    - 0.5
    - 0.8
    - 1.0
    - 1.2
    - 1.6
  plastic_nominal_mm:
    - 1.6
    - 2.0
    - 2.5
    - 3.0

mesh_profile: structural_modal_shell_solid

defect_injection:
  enable: true
  probability_per_part: 0.25
  sliver_face_probability: 0.08
  small_hole_probability: 0.15
  narrow_gap_probability: 0.12
  overlap_probability: 0.05
  bad_fillet_probability: 0.10

output:
  cad: STEP_AP242
  mesh: NASTRAN_BDF
  graph: PYTORCH_GEOMETRIC
  labels: PARQUET_JSON
```

---

## 7.4 Synthetic part template

CAD 생성은 CadQuery로 수행한다. CadQuery는 Python script로 parametric 3D CAD model을 생성하고 STEP 같은 CAD format을 출력할 수 있는 library다. ([CadQuery Documentation][6])

Template 목록:

| Template                | 실제 대응 부품        | feature                            | 기본 label                   |
| ----------------------- | --------------- | ---------------------------------- | -------------------------- |
| `PlasticBaseTemplate`   | base indoor     | rib, boss, duct opening, snap-fit  | shell                      |
| `RibbedCoverTemplate`   | door, cover     | thin wall, rib, hinge boss, groove | shell                      |
| `SheetMetalBoxTemplate` | control box     | flange, louver, screw hole, bend   | shell                      |
| `LBracketTemplate`      | bracket         | bend, slot, hole                   | shell                      |
| `UBracketTemplate`      | support bracket | multi-flange, hole pattern         | shell                      |
| `ThickHingeTemplate`    | hinge           | pin hole, thick boss               | solid                      |
| `PCBDummyTemplate`      | PCB             | board, mounting hole               | mass-only                  |
| `MotorDummyTemplate`    | fan motor       | cylinder, tab                      | mass-only/simplified solid |
| `ScrewTemplate`         | screw           | axis, diameter, head               | connector replacement      |
| `AdhesivePatchTemplate` | bonding region  | patch area                         | tied/adhesive              |

Template class 기본 interface:

```python
class PartTemplate(Protocol):
    template_name: str

    def sample_params(self, rng: Random, spec: GenerationSpec) -> BaseModel:
        ...

    def build(self, params: BaseModel) -> GeneratedPart:
        ...
```

`GeneratedPart` data structure:

```python
@dataclass
class GeneratedPart:
    part_uid: str
    part_name: str
    cad_shape: object
    material_id: str
    manufacturing_process: str
    nominal_thickness_mm: float
    component_role: str
    mass_handling: str
    mesh_priority: str
    feature_registry: list[FeatureRecord]
    face_labels: list[FaceLabel]
    edge_labels: list[EdgeLabel]
    named_ports: list[AssemblyPort]
```

---

## 7.5 Feature registry

부품 생성 시 CAD와 label을 동시에 생성한다.

예:

```json
{
  "feature_uid": "FEAT_CB_0001_HOLE_03",
  "feature_type": "screw_hole",
  "part_uid": "PART_CONTROL_BOX_0001",
  "diameter_mm": 3.2,
  "semantic_label": "PRESERVE_BOLT_HOLE",
  "defeature_action": "keep",
  "mesh_rule": {
    "washer_required": true,
    "washer_radius_mm": 5.0,
    "target_size_mm": 0.8,
    "ring_count": 3
  }
}
```

이 방식에서는 label을 사람이 나중에 붙이지 않는다. CAD 생성 코드가 feature를 만들면서 oracle label을 기록한다.

---

## 7.6 Geometry variation

각 template는 다음 변형을 자동 수행한다.

```text
dimension variation:
- width
- height
- depth
- thickness
- rib pitch
- rib height
- boss diameter
- hole diameter
- flange width
- fillet radius
- slot width
- bend radius

topology variation:
- rib 개수 변경
- boss 추가/삭제
- slot 추가/삭제
- vent pattern 변경
- flange 개수 변경
- screw hole pattern 변경
- snap-fit 개수 변경

defect variation:
- small hole
- tiny fillet
- sliver face
- short edge
- narrow gap
- minor overlap
- near-coaxial hole mismatch
```

Defect label:

| Defect          | 생성 방식                    | label                 |
| --------------- | ------------------------ | --------------------- |
| `small_hole`    | 0.5~2.0 mm hole 추가       | `REMOVE_SMALL_HOLE`   |
| `tiny_fillet`   | 0.2~1.0 mm radius 추가     | `REMOVE_SMALL_FILLET` |
| `sliver_face`   | narrow cut/chamfer 추가    | `SLIVER_FACE_RISK`    |
| `short_edge`    | min size보다 작은 edge 생성    | `SHORT_EDGE_RISK`     |
| `narrow_gap`    | part 간 0.01~0.5 mm gap   | `THIN_GAP_RISK`       |
| `minor_overlap` | 0.01~0.3 mm overlap      | `OVERLAP_RISK`        |
| `hole_mismatch` | screw axis 0.2~1.0 mm 편차 | `CONNECTION_REVIEW`   |

---

## 7.7 Persistent face/edge ID mapping

STEP export 후 CAD face ID가 바뀔 수 있으므로 CDF는 face signature matching을 수행한다.

절차:

```text
1. CAD 생성 직후 generator_face_uid 부여
2. face별 geometric signature 계산
3. STEP export
4. STEP re-import
5. re-import face와 원본 face signature matching
6. matching 실패율 기준 초과 시 sample reject
```

face signature:

```json
{
  "surface_type": "cylinder",
  "area": 12.566,
  "perimeter": 25.132,
  "centroid": [120.5, 35.0, 8.2],
  "normal_mean": [0.0, 0.0, 1.0],
  "curvature_mean": 0.3125,
  "curvature_max": 0.3125,
  "bbox_min": [118.9, 33.4, 8.2],
  "bbox_max": [122.1, 36.6, 8.2],
  "loop_count": 1,
  "adjacent_feature_uids": [
    "FEAT_CB_0001_HOLE_03"
  ]
}
```

matching gate:

```text
face matching rate >= 99.0%
edge matching rate >= 98.0%
connection feature matching rate = 100%
```

---

## 7.8 Full assembly 생성

Full assembly는 random placement가 아니라 **port-based assembly grammar**로 생성한다.

Assembly grammar:

```text
BaseIndoorAssembly
 ├─ PlasticBase
 │   ├─ RibGroup
 │   ├─ BossGroup
 │   ├─ MountingHolePattern
 │   └─ DuctOpening
 │
 ├─ ControlBoxAssembly
 │   ├─ SheetMetalControlBox
 │   ├─ ControlBoxCover
 │   ├─ PCBDummy
 │   └─ ScrewPattern
 │
 ├─ DoorAssembly
 │   ├─ RibbedPlasticDoor
 │   ├─ HingeSet
 │   └─ SnapFitSet
 │
 ├─ BracketGroup
 │   ├─ LBracket
 │   ├─ UBracket
 │   └─ ReinforcementPlate
 │
 └─ ConnectorGroup
     ├─ ScrewConnector
     ├─ TiedContact
     ├─ AdhesivePatch
     └─ MassConnector
```

Port 정의:

```json
{
  "port_uid": "PORT_CONTROL_BOX_BACK_FACE",
  "part_uid": "PART_CONTROL_BOX_0001",
  "port_type": "mounting_face",
  "origin": [0.0, 0.0, 0.0],
  "normal": [0.0, -1.0, 0.0],
  "allowed_connection": [
    "screw",
    "tied_contact"
  ],
  "preferred_mate_type": "face_to_face"
}
```

Mate rule:

```text
- mounting face normal은 반대 방향 정렬
- screw hole pattern은 축 정렬
- contact face gap은 0.0~0.2 mm
- 의도되지 않은 collision 금지
- duct, cover, base 간 clearance 유지
- fastener는 connector replacement 가능하도록 axis 기록
```

---

## 7.9 CDF mesh oracle

CDF는 AMG AI 모델을 사용하지 않는다. CDF는 generator oracle로 `mesh_recipe_oracle.json`을 만든다.

```json
{
  "parts": {
    "PART_CONTROL_BOX_001": {
      "strategy": "SHELL_MIDSURFACE",
      "target_size_mm": 5.0,
      "min_size_mm": 1.5,
      "thickness_mm": 0.8,
      "quality_profile": "shell_thin_metal"
    }
  },
  "defeature": {
    "FACE_000121": {
      "action": "remove",
      "reason": "small_hole_below_2mm"
    },
    "FACE_000188": {
      "action": "keep",
      "reason": "connection_related_hole"
    }
  },
  "connections": {
    "CONN_SYN_000391": {
      "type": "screw",
      "element_model": "RBE2_CBUSH_RBE2",
      "washer_radius_mm": 5.0,
      "ring_count": 3
    }
  }
}
```

---

## 7.10 CDF output dataset 구조

```text
CAE_MESH_DATASET_V001/
│
├─ dataset_manifest.json
├─ dataset_index.parquet
├─ split/
│  ├─ train.txt
│  ├─ val.txt
│  └─ test.txt
│
└─ samples/
   ├─ ASM_SYN_00000001/
   │  ├─ input_package/
   │  │  ├─ geometry/
   │  │  │  └─ assembly.step
   │  │  └─ metadata/
   │  │     ├─ manifest.json
   │  │     ├─ product_tree.json
   │  │     ├─ part_attributes.csv
   │  │     ├─ material_library.json
   │  │     ├─ connections.csv
   │  │     ├─ boundary_named_sets.json
   │  │     └─ mesh_profile.yaml
   │  │
   │  ├─ generation/
   │  │  ├─ generation_trace.json
   │  │  ├─ sampled_parameters.json
   │  │  ├─ feature_registry.json
   │  │  └─ assembly_constraint_graph.json
   │  │
   │  ├─ cad_graph/
   │  │  ├─ brep_graph.json
   │  │  ├─ assembly_graph.json
   │  │  └─ graph.pt
   │  │
   │  ├─ labels/
   │  │  ├─ part_strategy_labels.parquet
   │  │  ├─ face_semantic_labels.parquet
   │  │  ├─ edge_semantic_labels.parquet
   │  │  ├─ size_field_labels.parquet
   │  │  ├─ connection_labels.parquet
   │  │  ├─ failure_risk_labels.parquet
   │  │  └─ repair_action_labels.parquet
   │  │
   │  ├─ mesh/
   │  │  ├─ model_final.bdf
   │  │  ├─ model_final.ansa
   │  │  ├─ mesh_preview.vtk
   │  │  └─ mesh_to_cad_mapping.parquet
   │  │
   │  ├─ quality/
   │  │  ├─ qa_metrics_global.json
   │  │  ├─ qa_metrics_part.parquet
   │  │  ├─ qa_metrics_element.parquet
   │  │  ├─ failed_regions.parquet
   │  │  └─ qa_report.html
   │  │
   │  └─ oracle/
   │     ├─ mesh_recipe_oracle.json
   │     ├─ defeature_oracle.json
   │     └─ connector_oracle.json
   │
   └─ ASM_SYN_00000002/
      └─ ...
```

---

## 7.11 CDF dataset gate

### CAD gate

```text
STEP export success = true
STEP re-import success = true
face matching rate >= 99.0%
edge matching rate >= 98.0%
part metadata assignment rate = 100%
material assignment rate = 100%
connection part reference valid = 100%
```

### Assembly gate

```text
unintended collision count = 0
intended contact pair mapping rate = 100%
screw hole pair mapping rate = 100%
part transform valid = 100%
assembly tree valid = true
```

### Mesh gate

```text
BDF export success = true
BDF parse success = true
fatal error count = 0
missing property count = 0
missing material count = 0
duplicate node count = 0
unreferenced node count = 0
```

### Label gate

```text
part strategy label coverage = 100%
face semantic label coverage >= 95%
edge semantic label coverage >= 90%
connection label coverage = 100%
size field label coverage >= 95%
mesh_to_cad_mapping coverage >= 90%
```

기준 미달 sample은 dataset에 넣지 않고 다음 위치에 저장한다.

```text
CAE_MESH_DATASET_V001/rejected_samples/
```

---

# 8. Real CAD auto-label stream

CDF는 synthetic dataset만 만들지 않는다. 실제 LG CAD 입력도 자동 dataset으로 변환한다.

입력:

```text
REAL_CAD_JOB/
├─ geometry/
│  └─ assembly.step
└─ metadata/
   ├─ manifest.json
   ├─ product_tree.json
   ├─ part_attributes.csv
   ├─ material_library.json
   ├─ connections.csv
   └─ mesh_profile.yaml
```

처리:

```text
1. STEP import
2. B-Rep graph 생성
3. rule-based part strategy 추정
4. connection metadata 기반 connector 후보 생성
5. mesh_recipe_oracle 생성
6. ANSA batch meshing
7. QA metric 생성
8. pseudo-label 생성
9. confidence 낮은 region은 학습 제외 또는 low-weight label로 저장
```

Pseudo-label 예:

```json
{
  "sample_uid": "ASM_REAL_00042",
  "part_uid": "PART_CONTROL_BOX_A",
  "label_source": "real_cad_auto_mesh_pseudo",
  "strategy_label": "SHELL_MIDSURFACE",
  "label_confidence": 0.76,
  "loss_weight": 0.3
}
```

---

# 9. 사용 도구 및 소프트웨어

본 과제의 구현 stack은 하나로 고정한다.

| 구분                    | 도구                          | 사용 위치                                                   |
| --------------------- | --------------------------- | ------------------------------------------------------- |
| CAD 교환                | STEP AP242                  | AMG 입력, CDF 출력                                          |
| CAD 생성                | CadQuery                    | CDF synthetic part 생성                                   |
| CAD parsing / healing | Open CASCADE Technology     | B-Rep feature extraction, STEP re-import, shape healing |
| Meshing backend       | BETA CAE ANSA               | shell/solid mesh, midsurface, cleanup, BDF export       |
| ANSA 자동화              | ANSA Python script          | batch meshing, connector 생성, QA raw export              |
| AI framework          | PyTorch + PyTorch Geometric | BRepAssemblyNet 학습/추론                                   |
| BDF 검증                | pyNastran                   | BDF parse, card/property/material 검증                    |
| API                   | FastAPI                     | AMG/CDF job API                                         |
| Experiment tracking   | MLflow                      | model version, run metric, registry                     |
| Visualization         | VTK format                  | mesh preview, failed region visualization               |
| Dataframe 저장          | pandas + Parquet            | label, QA metric 저장                                     |
| DB                    | PostgreSQL                  | job metadata, dataset index                             |
| Object storage        | S3-compatible storage       | CAD, mesh, report artifact 저장                           |
| Container             | Docker                      | 개발/테스트 실행 환경                                            |

FastAPI는 Python type hint 기반 API framework로 사용할 수 있고, MLflow Model Registry는 모델 lifecycle과 version 관리를 위한 중앙 registry로 사용할 수 있다. ([FastAPI][7]) VTK는 scientific data 처리와 3D visualization을 위한 toolkit이며, VTK file format은 mesh preview와 failed region visualization에 사용한다. ([VTK][8])

Codex에 개발 요청을 전달할 때는 이 문서의 module path, schema, CLI, acceptance test를 기준으로 작업 단위를 나눈다. OpenAI Codex는 코드 작성, 코드 검토, 기존 codebase 이해를 지원하는 coding agent로 설명되어 있다. ([OpenAI 개발자][9])

---

# 10. 코드 모듈 구조

## 10.1 Repository 구조

```text
cae-mesh-automation/
│
├─ pyproject.toml
├─ README.md
├─ configs/
│  ├─ amg/
│  │  ├─ default_mesh_profile.yaml
│  │  └─ model_inference.yaml
│  ├─ cdf/
│  │  ├─ base_indoor_generation_v001.yaml
│  │  └─ defect_injection_rule.yaml
│  └─ training/
│     └─ brep_assembly_net.yaml
│
├─ schemas/
│  ├─ input_package.schema.json
│  ├─ product_tree.schema.json
│  ├─ material_library.schema.json
│  ├─ mesh_profile.schema.json
│  ├─ mesh_recipe.schema.json
│  ├─ label.schema.json
│  ├─ qa_metric.schema.json
│  └─ dataset_manifest.schema.json
│
├─ src/
│  ├─ cae_mesh_common/
│  │  ├─ __init__.py
│  │  ├─ schema/
│  │  │  ├─ validators.py
│  │  │  └─ models.py
│  │  ├─ cad/
│  │  │  ├─ occ_types.py
│  │  │  ├─ step_io.py
│  │  │  ├─ topology.py
│  │  │  ├─ face_signature.py
│  │  │  └─ geometry_features.py
│  │  ├─ graph/
│  │  │  ├─ hetero_graph.py
│  │  │  ├─ feature_normalizer.py
│  │  │  └─ pyg_io.py
│  │  ├─ bdf/
│  │  │  ├─ bdf_reader.py
│  │  │  ├─ bdf_validator.py
│  │  │  └─ bdf_metrics.py
│  │  ├─ qa/
│  │  │  ├─ shell_quality.py
│  │  │  ├─ solid_quality.py
│  │  │  ├─ connector_quality.py
│  │  │  ├─ mass_checker.py
│  │  │  └─ report_writer.py
│  │  └─ io/
│  │     ├─ package_reader.py
│  │     ├─ package_writer.py
│  │     └─ artifact_store.py
│  │
│  ├─ ai_mesh_generator/
│  │  ├─ __init__.py
│  │  ├─ cli.py
│  │  ├─ api.py
│  │  ├─ input/
│  │  │  └─ validator.py
│  │  ├─ cad/
│  │  │  ├─ importer.py
│  │  │  ├─ healer.py
│  │  │  └─ feature_extractor.py
│  │  ├─ graph/
│  │  │  └─ graph_builder.py
│  │  ├─ inference/
│  │  │  ├─ predictor.py
│  │  │  └─ model_loader.py
│  │  ├─ recipe/
│  │  │  ├─ guard.py
│  │  │  ├─ recipe_writer.py
│  │  │  └─ recipe_schema.py
│  │  ├─ meshing/
│  │  │  ├─ ansa_runner.py
│  │  │  └─ backend_interface.py
│  │  ├─ repair/
│  │  │  ├─ repair_planner.py
│  │  │  └─ repair_executor.py
│  │  ├─ output/
│  │  │  ├─ result_packager.py
│  │  │  └─ report_packager.py
│  │  └─ workflow/
│  │     └─ run_mesh_job.py
│  │
│  ├─ cae_dataset_factory/
│  │  ├─ __init__.py
│  │  ├─ cli.py
│  │  ├─ config/
│  │  │  └─ generation_spec.py
│  │  ├─ cad/
│  │  │  ├─ templates/
│  │  │  │  ├─ base.py
│  │  │  │  ├─ plastic_base.py
│  │  │  │  ├─ ribbed_cover.py
│  │  │  │  ├─ sheet_metal_box.py
│  │  │  │  ├─ bracket.py
│  │  │  │  ├─ pcb_dummy.py
│  │  │  │  ├─ motor_dummy.py
│  │  │  │  └─ screw.py
│  │  │  ├─ cad_exporter.py
│  │  │  ├─ step_reimport.py
│  │  │  └─ face_id_mapper.py
│  │  ├─ assembly/
│  │  │  ├─ port.py
│  │  │  ├─ mate_constraint.py
│  │  │  ├─ assembly_grammar.py
│  │  │  ├─ collision_checker.py
│  │  │  └─ connection_synthesizer.py
│  │  ├─ defects/
│  │  │  ├─ defect_injector.py
│  │  │  └─ defect_types.py
│  │  ├─ labeling/
│  │  │  ├─ feature_registry.py
│  │  │  ├─ part_strategy_oracle.py
│  │  │  ├─ face_semantic_oracle.py
│  │  │  ├─ edge_semantic_oracle.py
│  │  │  ├─ size_field_oracle.py
│  │  │  ├─ connection_oracle.py
│  │  │  └─ failure_labeler.py
│  │  ├─ meshing/
│  │  │  ├─ mesh_recipe_writer.py
│  │  │  ├─ ansa_runner.py
│  │  │  └─ cdf_mesh_backend.py
│  │  ├─ graph/
│  │  │  ├─ brep_graph_builder.py
│  │  │  ├─ assembly_graph_builder.py
│  │  │  └─ pyg_exporter.py
│  │  ├─ dataset/
│  │  │  ├─ sample_writer.py
│  │  │  ├─ dataset_indexer.py
│  │  │  ├─ split_builder.py
│  │  │  └─ dataset_validator.py
│  │  └─ workflow/
│  │     ├─ generate_sample.py
│  │     ├─ mesh_sample.py
│  │     ├─ evaluate_sample.py
│  │     └─ build_dataset.py
│  │
│  └─ training_pipeline/
│     ├─ __init__.py
│     ├─ data/
│     │  ├─ dataset.py
│     │  ├─ datamodule.py
│     │  └─ collate.py
│     ├─ models/
│     │  ├─ brep_assembly_net.py
│     │  ├─ encoders.py
│     │  └─ heads.py
│     ├─ losses/
│     │  └─ multitask_loss.py
│     ├─ train.py
│     ├─ evaluate.py
│     └─ export_model.py
│
├─ ansa_scripts/
│  ├─ amg_batch_mesh.py
│  ├─ cdf_batch_mesh.py
│  ├─ common_ansa_utils.py
│  └─ connector_builder.py
│
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ golden_samples/
│  └─ e2e/
│
└─ docs/
   ├─ input_package_spec.md
   ├─ mesh_recipe_spec.md
   ├─ dataset_spec.md
   ├─ ansa_backend_spec.md
   └─ codex_task_breakdown.md
```

---

# 11. CLI 및 API 정의

## 11.1 AMG CLI

```bash
amg validate-input \
  --job LGE_CAE_MESH_JOB.zip \
  --output workdir/validation_report.json
```

```bash
amg build-graph \
  --job LGE_CAE_MESH_JOB.zip \
  --output workdir/graph
```

```bash
amg predict-recipe \
  --graph workdir/graph/input_graph.pt \
  --model artifacts/models/brep_assembly_net.pt \
  --metadata workdir/metadata \
  --output workdir/mesh_recipe_final.json
```

```bash
amg run-mesh \
  --job LGE_CAE_MESH_JOB.zip \
  --model artifacts/models/brep_assembly_net.pt \
  --output MESH_RESULT.zip
```

```bash
amg validate-bdf \
  --bdf solver_deck/model_final.bdf \
  --output report/bdf_validation.json
```

---

## 11.2 CDF CLI

```bash
cdf validate-spec \
  --spec configs/cdf/base_indoor_generation_v001.yaml
```

```bash
cdf generate \
  --spec configs/cdf/base_indoor_generation_v001.yaml \
  --num-samples 10000 \
  --output /data/CAE_MESH_DATASET_V001
```

```bash
cdf mesh \
  --dataset /data/CAE_MESH_DATASET_V001 \
  --workers 16 \
  --backend ANSA_BATCH
```

```bash
cdf evaluate \
  --dataset /data/CAE_MESH_DATASET_V001
```

```bash
cdf build-graphs \
  --dataset /data/CAE_MESH_DATASET_V001
```

```bash
cdf build-split \
  --dataset /data/CAE_MESH_DATASET_V001 \
  --train 0.8 \
  --val 0.1 \
  --test 0.1
```

```bash
cdf validate-dataset \
  --dataset /data/CAE_MESH_DATASET_V001
```

---

## 11.3 Training CLI

```bash
train-brep-assembly-net \
  --config configs/training/brep_assembly_net.yaml \
  --dataset /data/CAE_MESH_DATASET_V001 \
  --output artifacts/models/brep_assembly_net_v001
```

```bash
evaluate-brep-assembly-net \
  --model artifacts/models/brep_assembly_net_v001/model.pt \
  --dataset /data/CAE_MESH_DATASET_V001 \
  --split test \
  --output reports/model_eval_v001
```

```bash
export-amg-model \
  --checkpoint artifacts/models/brep_assembly_net_v001/checkpoint.ckpt \
  --output artifacts/models/brep_assembly_net.pt
```

---

# 12. 핵심 Python data model

## 12.1 Part attribute model

```python
class PartAttribute(BaseModel):
    part_uid: str
    part_name: str
    material_id: str
    manufacturing_process: Literal[
        "sheet_metal",
        "injection_plastic",
        "machined_metal",
        "purchased_fastener",
        "electronic_module",
        "rubber_part",
        "unknown",
    ]
    nominal_thickness_mm: float
    min_thickness_mm: float
    max_thickness_mm: float
    component_role: str
    mass_handling: Literal[
        "mesh",
        "simplified_solid",
        "connector",
        "mass_only",
        "exclude",
    ]
    mesh_priority: Literal["low", "normal", "high"]
```

---

## 12.2 Mesh recipe model

```python
class PartMeshRecipe(BaseModel):
    part_uid: str
    strategy: Literal[
        "SHELL_MIDSURFACE",
        "SOLID_TETRA",
        "CONNECTOR_REPLACEMENT",
        "MASS_ONLY",
        "EXCLUDE_FROM_ANALYSIS",
        "MANUAL_REVIEW",
    ]
    target_size_mm: float
    min_size_mm: float
    thickness_mm: float | None
    material_id: str | None
    property_type: Literal["PSHELL", "PSOLID", "CONM2", "NONE"]
    quality_profile: str
    confidence: float
```

---

## 12.3 Face label model

```python
class FaceSemanticLabel(BaseModel):
    sample_uid: str
    part_uid: str
    face_uid: str
    feature_uid: str | None
    surface_type: str
    semantic_label: Literal[
        "PRESERVE_STRUCTURAL",
        "REMOVE_SMALL_HOLE",
        "REMOVE_SMALL_FILLET",
        "REMOVE_LOGO_EMBOSS",
        "PRESERVE_BOLT_HOLE",
        "CONTACT_FACE",
        "LOAD_BC_FACE",
        "MIDSURFACE_SOURCE",
        "THICKNESS_TRANSITION",
        "MANUAL_REVIEW",
    ]
    is_connection_related: bool
    is_named_boundary: bool
    defeature_action: Literal["keep", "remove", "merge", "suppress", "review"]
    target_size_mm: float
    min_size_mm: float
    label_source: Literal[
        "generator_oracle",
        "rule_oracle",
        "real_cad_auto_mesh_pseudo",
        "manual_validated",
    ]
    label_confidence: float
```

---

# 13. 테스트 및 수용 기준

## 13.1 Unit test

필수 unit test:

```text
- manifest schema validation
- part_attributes.csv parsing
- material_library validation
- mesh_profile validation
- face signature distance calculation
- part strategy oracle
- size field oracle
- guard rule override
- BDF parse validation
- shell quality metric calculation
- dataset index writer
```

---

## 13.2 Integration test

Golden sample 5개를 만든다.

```text
tests/golden_samples/
├─ simple_sheet_metal_box/
├─ plastic_base_with_ribs/
├─ control_box_with_screws/
├─ mixed_shell_solid_assembly/
└─ defect_injection_sample/
```

각 sample의 통과 기준:

```text
- input validation pass
- graph.pt 생성
- mesh_recipe 생성
- ANSA dry-run 또는 실제 run pass
- BDF parse pass
- QA report 생성
- output package 생성
```

ANSA license가 없는 CI 환경에서는 `MockMeshingBackend`로 BDF fixture를 생성한다. 운영/검증 환경에서는 ANSA backend만 사용한다.

---

## 13.3 End-to-end test

AMG E2E:

```bash
amg run-mesh \
  --job tests/golden_samples/control_box_with_screws/LGE_CAE_MESH_JOB.zip \
  --model tests/fixtures/model_dummy.pt \
  --output /tmp/MESH_RESULT.zip
```

통과 기준:

```text
- MESH_RESULT.zip 생성
- model_final.bdf 존재
- qa_report.html 존재
- mesh_recipe_final.json 존재
- bdf_parse_success = true
- missing_property_count = 0
- missing_material_count = 0
```

CDF E2E:

```bash
cdf generate \
  --spec tests/fixtures/cdf_smoke.yaml \
  --num-samples 10 \
  --output /tmp/CAE_MESH_DATASET_SMOKE

cdf validate-dataset \
  --dataset /tmp/CAE_MESH_DATASET_SMOKE
```

통과 기준:

```text
- sample 10개 생성
- assembly.step 10개 생성
- label parquet 생성
- graph.pt 생성
- dataset_index.parquet 생성
- rejected sample 비율 <= 20%
```

---

# 14. 성능 지표

## 14.1 AMG 지표

| 지표                           |    PoC |  Pilot |     운영 |
| ---------------------------- | -----: | -----: | -----: |
| in-scope part 자동 mesh 성공률    |    70% |    80% |    90% |
| BDF parse success            |   100% |   100% |   100% |
| material/property assignment |   100% |   100% |   100% |
| fatal QA error               |      0 |      0 |      0 |
| manual review part 비율        | 30% 이하 | 20% 이하 | 10% 이하 |
| 기존 수작업 대비 시간 단축              |    50% |    60% |    70% |
| 동일 입력 재실행 recipe 재현성         |   100% |   100% |   100% |

---

## 14.2 AI 지표

| Head                    | Metric         |      목표 |
| ----------------------- | -------------- | ------: |
| PartStrategyHead        | macro F1       | 0.95 이상 |
| FaceSemanticHead        | mean IoU       | 0.85 이상 |
| EdgeSemanticHead        | macro F1       | 0.85 이상 |
| SizeFieldHead           | MAE            |  15% 이하 |
| ConnectionCandidateHead | recall         | 0.90 이상 |
| FailureRiskHead         | recall         | 0.85 이상 |
| RepairActionHead        | top-1 accuracy | 0.75 이상 |

---

## 14.3 CDF 지표

| 항목                               |                           목표 |
| -------------------------------- | ---------------------------: |
| synthetic sample 생성 성공률          |                       90% 이상 |
| face matching rate               |                       99% 이상 |
| edge matching rate               |                       98% 이상 |
| connection feature matching rate |                         100% |
| BDF parse success                |                         100% |
| label coverage, part             |                         100% |
| label coverage, face             |                       95% 이상 |
| label coverage, connection       |                         100% |
| dataset generation throughput    | 1 worker당 50 assembly/day 이상 |

---

# 15. 개발 일정

## Phase 0 — Spec 및 schema 고정, 2주

산출물:

```text
- schemas/*.schema.json
- docs/input_package_spec.md
- docs/mesh_recipe_spec.md
- docs/dataset_spec.md
- configs/amg/default_mesh_profile.yaml
- configs/cdf/base_indoor_generation_v001.yaml
```

완료 기준:

```text
- sample input package validation 가능
- mesh_profile validation 가능
- Codex 작업 단위 정의 완료
```

---

## Phase 1 — Deterministic baseline AMG, 6주

산출물:

```text
- input validator
- STEP importer
- feature extractor
- graph builder skeleton
- rule-based mesh recipe generator
- ANSA runner
- BDF validator
- QA report writer
```

완료 기준:

```text
- AI 없이 rule 기반으로 control box assembly 1종 처리
- BDF parse success
- material/property assignment 100%
```

---

## Phase 2 — CDF synthetic data generator, 8주

산출물:

```text
- CadQuery part template 8종
- port-based assembly generator
- defect injector
- persistent face mapper
- oracle label generator
- dataset writer
```

완료 기준:

```text
- synthetic assembly 500개 생성
- part template 8종 동작
- face matching rate >= 99%
- label parquet 생성
- graph.pt 생성
```

---

## Phase 3 — AI model training pipeline, 8주

산출물:

```text
- BRepAssemblyNet
- dataset loader
- multitask loss
- training script
- evaluation script
- model export
```

완료 기준:

```text
- PartStrategy F1 >= 0.95
- FaceSemantic mIoU >= 0.85
- SizeField MAE <= 15%
- trained_model.pt export
```

---

## Phase 4 — AMG AI integration + repair loop, 8주

산출물:

```text
- AI inference integration
- engineering guard
- repair planner
- repair executor
- final mesh_recipe
- repair_history.json
```

완료 기준:

```text
- 대표 full assembly 3종에서 자동 mesh 성공률 >= 70%
- fatal QA error = 0
- BDF parse error = 0
```

---

## Phase 5 — Pilot 운영화, 8주

산출물:

```text
- FastAPI job server
- artifact storage integration
- MLflow model registry integration
- dashboard용 job metadata
- pilot report
```

완료 기준:

```text
- pilot assembly 5종 이상 처리
- 자동 mesh 성공률 >= 80%
- manual 수정 시간 60% 이상 감소
- 동일 입력 재현성 100%
```

---

# 16. Codex 작업 분해 기준

Codex에는 다음 순서로 개발 요청을 전달한다. 각 작업은 독립 PR 단위로 구현한다.

## Task 01 — Shared schema and validators

```text
목표:
- input package, mesh profile, mesh recipe, label, QA metric schema 구현

구현 파일:
- schemas/*.schema.json
- src/cae_mesh_common/schema/models.py
- src/cae_mesh_common/schema/validators.py

테스트:
- tests/unit/test_schema_validation.py
```

완료 조건:

```text
- 정상 sample validation pass
- part_uid 누락 sample validation fail
- material 누락 sample validation fail
```

---

## Task 02 — BDF validation module

```text
목표:
- pyNastran 기반 BDF reader/validator 구현

구현 파일:
- src/cae_mesh_common/bdf/bdf_reader.py
- src/cae_mesh_common/bdf/bdf_validator.py
- src/cae_mesh_common/bdf/bdf_metrics.py

테스트:
- tests/unit/test_bdf_validator.py
```

완료 조건:

```text
- valid BDF parse pass
- missing property detect
- missing material detect
- duplicate ID detect
```

---

## Task 03 — CDF part template base

```text
목표:
- GeneratedPart, FeatureRecord, FaceLabel, AssemblyPort data model 구현
- PlasticBaseTemplate, SheetMetalBoxTemplate 최소 구현

구현 파일:
- src/cae_dataset_factory/cad/templates/base.py
- src/cae_dataset_factory/cad/templates/plastic_base.py
- src/cae_dataset_factory/cad/templates/sheet_metal_box.py

테스트:
- tests/unit/test_cdf_templates.py
```

완료 조건:

```text
- STEP export 가능
- feature_registry 생성
- face label 생성
```

---

## Task 04 — CDF assembly grammar

```text
목표:
- port-based assembly 생성
- mate constraint 적용
- screw connection 생성

구현 파일:
- src/cae_dataset_factory/assembly/port.py
- src/cae_dataset_factory/assembly/mate_constraint.py
- src/cae_dataset_factory/assembly/assembly_grammar.py
- src/cae_dataset_factory/assembly/connection_synthesizer.py

테스트:
- tests/unit/test_assembly_grammar.py
```

완료 조건:

```text
- part 10개 이상 assembly 생성
- connection metadata 생성
- product_tree.json 생성
```

---

## Task 05 — Face ID mapper

```text
목표:
- STEP export/re-import 후 face matching 구현

구현 파일:
- src/cae_mesh_common/cad/face_signature.py
- src/cae_dataset_factory/cad/face_id_mapper.py

테스트:
- tests/unit/test_face_id_mapper.py
```

완료 조건:

```text
- simple part face matching >= 99%
- screw hole face mapping 유지
```

---

## Task 06 — Graph builder

```text
목표:
- B-Rep graph와 assembly graph 생성
- PyG HeteroData export

구현 파일:
- src/cae_mesh_common/graph/hetero_graph.py
- src/ai_mesh_generator/graph/graph_builder.py
- src/cae_dataset_factory/graph/pyg_exporter.py

테스트:
- tests/unit/test_graph_builder.py
```

완료 조건:

```text
- face/edge/part node 생성
- edge_index 생성
- graph.pt 저장/로드 가능
```

---

## Task 07 — BRepAssemblyNet

```text
목표:
- heterogeneous graph encoder와 7개 prediction head 구현

구현 파일:
- src/training_pipeline/models/brep_assembly_net.py
- src/training_pipeline/models/encoders.py
- src/training_pipeline/models/heads.py
- src/training_pipeline/losses/multitask_loss.py

테스트:
- tests/unit/test_brep_assembly_net_forward.py
```

완료 조건:

```text
- dummy HeteroData forward pass
- 모든 head output shape 검증
- loss 계산 가능
```

---

## Task 08 — AMG recipe guard

```text
목표:
- AI prediction과 metadata를 결합하여 guarded mesh recipe 생성

구현 파일:
- src/ai_mesh_generator/recipe/guard.py
- src/ai_mesh_generator/recipe/recipe_writer.py

테스트:
- tests/unit/test_recipe_guard.py
```

완료 조건:

```text
- named boundary defeature 금지
- connection hole 삭제 금지
- confidence 낮은 entity manual review 처리
```

---

## Task 09 — ANSA backend interface

```text
목표:
- ANSA runner와 mock backend 구현
- 실제 ANSA script 호출 interface 구현

구현 파일:
- src/ai_mesh_generator/meshing/backend_interface.py
- src/ai_mesh_generator/meshing/ansa_runner.py
- src/cae_dataset_factory/meshing/ansa_runner.py
- ansa_scripts/common_ansa_utils.py
- ansa_scripts/amg_batch_mesh.py
- ansa_scripts/cdf_batch_mesh.py

테스트:
- tests/integration/test_mock_meshing_backend.py
```

완료 조건:

```text
- mock backend로 BDF fixture 생성
- ANSA command line 구성 검증
- recipe/config 전달 검증
```

---

## Task 10 — AMG E2E workflow

```text
목표:
- LGE_CAE_MESH_JOB.zip 입력에서 MESH_RESULT.zip 출력까지 연결

구현 파일:
- src/ai_mesh_generator/workflow/run_mesh_job.py
- src/ai_mesh_generator/cli.py
- src/ai_mesh_generator/output/result_packager.py

테스트:
- tests/e2e/test_amg_run_mesh.py
```

완료 조건:

```text
- golden sample E2E pass
- MESH_RESULT.zip 구조 검증
- qa_report.html 생성
```

---

## Task 11 — CDF E2E workflow

```text
목표:
- generation_spec.yaml 입력에서 dataset sample 생성까지 연결

구현 파일:
- src/cae_dataset_factory/workflow/build_dataset.py
- src/cae_dataset_factory/cli.py
- src/cae_dataset_factory/dataset/sample_writer.py
- src/cae_dataset_factory/dataset/dataset_validator.py

테스트:
- tests/e2e/test_cdf_build_dataset.py
```

완료 조건:

```text
- sample 10개 생성
- dataset_index.parquet 생성
- label parquet 생성
- graph.pt 생성
```

---

# 17. 최종 개발 방향 요약

본 과제는 다음 구조로 구현한다.

```text
[AMG]
STEP AP242 assembly
+ part/material/thickness/connection metadata
        ↓
B-Rep graph / assembly graph
        ↓
BRepAssemblyNet
        ↓
mesh_recipe_final.json
        ↓
engineering guard
        ↓
ANSA batch meshing
        ↓
repair loop
        ↓
Nastran BDF + QA report
```

```text
[CDF]
generation_spec.yaml
        ↓
parametric CAD template
        ↓
synthetic full assembly
        ↓
oracle labels
        ↓
ANSA batch meshing
        ↓
quality/failure labels
        ↓
graph.pt + label parquet + BDF dataset
```

개발 성공의 핵심은 다음 네 가지다.

```text
1. 입력 package schema를 엄격히 고정한다.
2. AI는 mesh connectivity가 아니라 mesh recipe를 예측한다.
3. ANSA batch meshing을 production backend로 사용한다.
4. CDF를 AMG와 독립된 dataset 생산 시스템으로 구현한다.
```

PoC의 최소 성공 기준은 다음이다.

```text
- CDF synthetic assembly 500개 생성
- face matching rate >= 99%
- graph.pt와 label parquet 생성
- AMG가 golden full assembly 1종 처리
- Nastran BDF parse error 0
- material/property assignment 100%
- in-scope part mesh success rate >= 70%
```

이 기준을 만족하면 이후 pilot에서는 실제 LG CAD 5종 이상에 대해 자동 mesh 성공률 80% 이상, 수작업 mesh 준비 시간 60% 이상 단축을 목표로 확장한다.

[1]: https://www.iso.org/standard/66654.html?utm_source=chatgpt.com "ISO 10303-242:2020 - Industrial automation systems ..."
[2]: https://pynastran-git.readthedocs.io/?utm_source=chatgpt.com "pyNastran's documentation for Main! - Read the Docs"
[3]: https://pytorch-geometric.readthedocs.io/?utm_source=chatgpt.com "PyTorch Geometric - Read the Docs"
[4]: https://dev.opencascade.org/doc/overview/html/?utm_source=chatgpt.com "Open CASCADE Technology: Introduction"
[5]: https://www.beta-cae.com/ansa.htm?utm_source=chatgpt.com "ANSA pre-processor"
[6]: https://cadquery.readthedocs.io/?utm_source=chatgpt.com "CadQuery Documentation — CadQuery Documentation"
[7]: https://fastapi.tiangolo.com/?utm_source=chatgpt.com "FastAPI"
[8]: https://vtk.org/?utm_source=chatgpt.com "VTK - The Visualization Toolkit"
[9]: https://developers.openai.com/codex?utm_source=chatgpt.com "Codex | OpenAI Developers"
## Truthful Production Validation Addendum

The repository must distinguish synthetic bootstrap validation from production
LG/OEM CAD validation.

- Production AMG meshing uses `ANSA_BATCH` only.
- CDF may use a deterministic synthetic oracle to generate bootstrap labels and
  meshes, but this oracle must not be reported as production mesh automation.
- If ANSA is unavailable or fails, production meshing fails explicitly.
- `FINAL_DELIVERY_REPORT.md` must use truthful status labels such as
  `REFINEMENT_SYNTHETIC_BOOTSTRAP_ACCEPTED`, `ANSA_SMOKE_PASSED`,
  `SYNTHETIC_ANSA_REGRESSION_ACCEPTED`, and `LG_PRODUCTION_NOT_VALIDATED`;
  generic `ACCEPTED` is not sufficient unless a real LG/OEM CAD/Mesh regression
  has been supplied and passed.
- Every CAD product/part must be represented in FE output as explicit mesh,
  connector, mass, approved-exclude, or manual-review/failure. Silent omission
  is a validation failure.
- `approved_exclude` requires explicit acceptance metadata. Fasteners are mesh
  targets by default unless engineering intent maps them to connector or mass.
- Real training submissions require `cad/raw.step`, `ansa/final.ansa`,
  `metadata/acceptance.csv`, and `metadata/quality_criteria.yaml`.
- Young's modulus, density, and Poisson ratio are not required for mesh
  automation training unless solver-ready BDF export is explicitly in scope.
## Current Synthetic CAD Integrity Rule

The CDF synthetic bootstrap dataset is accepted only when generated STEP AP242
B-Rep geometry contains actual template features. `plastic_base`,
`ribbed_cover`, `sheet_metal_box`, `bracket`, `screw`, `motor_dummy`, and
`pcb_dummy` must not export as plain rectangular boxes. Feature labels such as
`rib`, `screw_boss`, `mounting_hole`, `flange`, `cylindrical_shank`, and
`cylindrical_body` must have topology evidence in the STEP file. Builder
failures or unsupported templates must fail or be rejected; box fallback is not
permitted. Synthetic success is reported as
`REFINEMENT_SYNTHETIC_BOOTSTRAP_ACCEPTED`, while real LG/OEM production validation
remains `LG_PRODUCTION_NOT_VALIDATED` until external CAD/Mesh pairs are
validated.

## AI-ANSA Refinement Pipeline Addendum

Uniform part-level mesh size is not the production target. The learning target
and AMG output must be region-aware:

- Dataset labels use `mesh_size_labels` for part, face, edge, feature,
  contact-candidate, and connection targets.
- Holes, short edges, thin strips, rib roots, bosses, contact faces, and
  boundary/load regions must produce local refinement targets smaller than the
  parent part baseline when applicable.
- `mesh_recipe_final.json` must include `refinement_zones` with explicit target
  uid/type, local size, growth rate, boundary-preservation flag, ANSA control
  type, and reason.
- BRepAssemblyNet must expose recipe-compatible heads for `face_size`,
  `edge_size`, `contact_size`, and `feature_refinement_class`; part-level size is
  only an auxiliary coarse control.
- ANSA integration must record refinement zone counts and application metadata.
  A required zone that cannot be mapped to ANSA controls must become
  manual-review/failure, not a silent pass.
- Synthetic bootstrap acceptance requires at least five topology families,
  variable part/face/edge/contact graph shapes, retained rejected/failure
  samples, and high feature-level mesh-size label coverage.
- Real supervised production claims require engineer-reviewed CAD/ANSA mesh
  pairs. Without those pairs the report must state
  `REAL_SUPERVISED_DATASET_NOT_AVAILABLE`.
