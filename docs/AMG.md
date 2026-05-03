# AMG-SM-V1: AI Mesh-Control Manifest Generator for Constant-Thickness Sheet-Metal Parts

## 0. 문서 목적과 구현 계약

AMG-SM-V1은 일정 두께 판금 단품의 STEP solid CAD를 입력받아 구조해석용 shell mesh 생성을 자동화하는 도구이다. AMG의 AI 모델은 node 좌표나 element connectivity가 아니라, ANSA Batch Mesh가 실행할 수 있는 `mesh_control_manifest.json`을 예측한다. ANSA는 이 manifest를 사용해 midsurface 생성, shell thickness assignment, local refinement, washer, hole treatment, bend treatment, flange treatment, batch mesh, quality check를 수행한다.

이 문서는 AMG-SM-V1의 구현 범위를 다음으로 고정한다.

```text
대상 형상          : 일정 두께 판금 단품
입력 CAD           : STEP solid B-rep
해석 idealization  : shell midsurface
격자 실행 엔진     : ANSA Batch Mesh
AI 예측 대상       : mesh-control manifest
최종 산출물        : solver-ready shell mesh + quality report
```

AMG-SM-V1의 모든 판단은 다음 데이터에서만 나온다.

```text
1. input.step에서 추출한 B-rep geometry/topology
2. amg_config.json의 수치 policy
3. feature_overrides.json의 명시적 feature role
4. ANSA quality report의 수치 결과
```

문서에 정의되지 않은 회사별 품질 기준, 수정 이력, 수동 승인 이력, 사람이 임의로 판단하는 feature label은 AMG-SM-V1의 입력 또는 학습 target으로 사용하지 않는다.

---

## 1. 문제 정의

### 1.1 입력, 예측값, 실행값, 검증값

AMG의 수학적 문제는 다음과 같다.

```text
Input:
  B = STEP에서 추출한 일정 두께 판금 B-rep graph
  C = AMG configuration

Predict:
  θ_hat = raw mesh-control prediction

Project:
  θ = Π_rules(θ_hat, B, C)

Execute:
  M = A_ANSA(B, θ)

Validate:
  Q(M) satisfies AMG_QA_SHELL_V1
```

여기서 각 기호는 다음을 의미한다.

```text
B        : face, edge, coedge, vertex, loop, body로 구성된 B-rep graph
C        : 두께, element size, feature policy, 품질 기준, ANSA session을 담은 JSON
θ_hat    : AI가 예측한 raw manifest parameter
θ        : rule projection을 통과한 실행 가능한 mesh-control manifest
Π_rules  : geometry, role, size, growth, clearance, quality constraint projector
A_ANSA   : ANSA import, cleanup, midsurface, batch mesh, quality check 실행기
M        : shell mesh
Q(M)     : shell mesh quality metric 집합
```

AMG가 최소화하려는 목표는 다음이다.

\[
\theta^* = \arg\min_{\theta \in \Theta}
\left[
  \lambda_q V_q(M)
  + \lambda_n \frac{N_e(M)}{N_{ref}}
  + \lambda_s V_s(\theta)
  + \lambda_f V_f(\theta)
\right]
\]

subject to:

\[
M = A_{ANSA}(B,\theta)
\]

\[
h_{min} \le h_i \le h_{max}
\]

\[
\left|\log h_i-\log h_j\right| \le \log g_{max}
\quad \forall (i,j)\in E_{adj}
\]

\[
Q_k(e)\le Q_{k,max}
\quad \forall e\in M,\ \forall k
\]

각 항은 다음을 의미한다.

```text
V_q      : quality violation penalty
N_e      : shell element count
N_ref    : 기준 shell element count
V_s      : size discontinuity penalty
V_f      : feature rule violation penalty
h_i      : face, edge, feature region i의 local target length
g_max    : 인접 영역 growth ratio 상한
Q_k      : aspect, skew, warpage, Jacobian, angle 등 shell quality metric
```

### 1.2 Manifest 기반 parameterization

AMG-SM-V1의 예측 변수는 ANSA가 실행할 수 있는 mesh-control manifest이다. 이 parameterization은 다음 속성을 만족한다.

```text
1. 입력 형상마다 달라지는 node 수와 element 수를 manifest dimension으로 직접 표현하지 않는다.
2. STEP face/edge와 mesh perimeter 사이의 associativity를 ANSA entity matching으로 유지한다.
3. midsurface, washer, bend row, flange sizing, quality improvement를 ANSA 실행 계층에 위임한다.
4. 실패 원인을 feature action, local size, growth rate, bend row 같은 manifest parameter로 환원한다.
```

AMG-SM-V1의 AI는 다음 항목을 예측하거나 보정한다.

```text
part idealization       : midsurface_shell
face target length      : h_face
edge target length      : h_edge
feature action          : KEEP_REFINED, KEEP_WITH_WASHER, SUPPRESS, KEEP_WITH_BEND_ROWS, KEEP_WITH_FLANGE_SIZE
feature numeric control : n_divisions, washer_rings, washer_radius, bend_rows, growth_rate
ANSA session mapping    : shell batch session, local control set
```

---

## 2. 형상 범위와 이름 규칙

### 2.1 허용 part class

AMG-SM-V1은 다음 part class를 지원한다.

| class | 설명 | 판정 기준 |
|---|---|---|
| `SM_FLAT_PANEL` | 평판 | midsurface 주요 planar patch 수 = 1 |
| `SM_SINGLE_FLANGE` | 한쪽 flange가 있는 판금 | 주요 planar patch 수 = 2, bend patch 수 = 1 |
| `SM_L_BRACKET` | L형 브래킷 | 주요 planar patch 수 = 2, patch normal angle 70°~110°, bend patch 수 = 1 |
| `SM_U_CHANNEL` | U형 채널 | 주요 planar patch 수 = 3, bend patch 수 = 2, 양쪽 flange patch normal이 서로 평행 |
| `SM_HAT_CHANNEL` | hat channel | 주요 planar patch 수 = 5, bend patch 수 = 4 |

Geometry validation 단계는 다음 형상에 대해 `OUT_OF_SCOPE` manifest를 반환한다.

```text
variable_thickness_body
multi_body_assembly
solid_boss_or_standoff
non_sheet_rib_with_local_thickness_increase
casting_like_blend_network
freeform_double_curvature_shell_without_sheet_pairing
closed_thin_wall_plastic_housing
solid_tetra_or_hex_mesh_target
```

### 2.2 Part name schema

Part name은 geometry classification을 대체하지 않는다. Part name은 sample 추적성과 sidecar metadata 연결에만 사용한다. 형상 분류는 항상 B-rep geometry에서 다시 계산한다.

```text
SMT_<CLASS>_W<width_mm>_H<height_mm>_T<thickness_mm>_<UID>
```

예시:

```text
SMT_SM_FLAT_PANEL_W180_H120_T1p2_A83F
SMT_SM_L_BRACKET_W160_H90_T1p6_B12C
SMT_SM_U_CHANNEL_W220_H80_T2p0_D91E
```

규칙:

```text
T1p2  : 1.2 mm
UID   : STEP import 후 entity id가 바뀌어도 sidecar metadata와 연결하기 위한 짧은 식별자
CLASS : geometry validation에서 재계산한 class와 일치해야 함
```

수정 이력이나 회사 내부 revision은 part name에 포함하지 않는다.

### 2.3 Feature name schema

```text
<FEATURE_TYPE>_<ROLE>_<INDEX>
```

허용 feature type은 다음과 같다.

```text
FEATURE_TYPE ∈ {HOLE, SLOT, CUTOUT, BEND, FLANGE, OUTER_BOUNDARY}
```

허용 role은 다음과 같다.

```text
ROLE ∈ {BOLT, MOUNT, RELIEF, DRAIN, VENT, PASSAGE, STRUCTURAL, UNKNOWN}
```

예시:

```text
HOLE_BOLT_0001
HOLE_DRAIN_0002
SLOT_MOUNT_0003
CUTOUT_PASSAGE_0004
BEND_STRUCTURAL_0005
FLANGE_STRUCTURAL_0006
```

`ROLE=UNKNOWN`이면 action mask에서 `SUPPRESS`를 비활성화한다. Geometry만으로 bolt hole, drain hole, relief hole의 기능을 확정하지 않는다.

---

## 3. 입력 데이터 구조

AMG-SM-V1의 입력은 다음 파일로 구성된다.

```text
input.step
amg_config.json
feature_overrides.json    # optional
```

### 3.1 `input.step`

조건:

```text
format       : STEP AP203/AP214/AP242 중 ANSA와 B-rep extractor가 import 가능한 형식
unit         : mm
body count   : 1 connected solid body
thickness    : constant within tolerance
features     : through holes, slots, cutouts, bends, flanges
```

### 3.2 `amg_config.json`

```json
{
  "schema_version": "AMG_CONFIG_SM_V1",
  "part_name": "SMT_SM_L_BRACKET_W160_H90_T1p2_A83F",
  "unit": "mm",
  "thickness_mm": 1.2,
  "mesh_policy": {
    "element_type": "quad_dominant_shell",
    "h0_mm": 4.0,
    "h_min_mm": 0.6,
    "h_max_mm": 8.0,
    "growth_rate_max": 1.30,
    "tria_fraction_max": 0.15
  },
  "feature_policy": {
    "unknown_feature_action": "KEEP_REFINED",
    "small_relief_hole_suppress": true,
    "small_drain_hole_suppress": true,
    "washer_roles": ["BOLT", "MOUNT"],
    "retained_hole_min_divisions": 12,
    "bolt_hole_min_divisions": 24,
    "slot_end_min_divisions": 12,
    "min_flange_elements_across_width": 2,
    "min_bend_rows": 2,
    "max_bend_rows": 6
  },
  "quality_profile": "AMG_QA_SHELL_V1",
  "ansa": {
    "batch_session": "AMG_SHELL_CONST_THICKNESS_V1",
    "quality_template": "AMG_QA_SHELL_V1",
    "export_solver": "NASTRAN"
  }
}
```

### 3.3 `feature_overrides.json`

이 파일은 code-generated dataset 또는 사용자가 명시적으로 부여한 feature role을 담는다. STEP entity name에서 role을 안정적으로 얻을 수 없을 때 사용한다.

```json
{
  "schema_version": "AMG_FEATURE_OVERRIDES_SM_V1",
  "features": [
    {
      "feature_id": "HOLE_BOLT_0001",
      "type": "HOLE",
      "role": "BOLT",
      "signature": {
        "center_mm": [42.0, 30.0, 0.0],
        "axis": [0.0, 0.0, 1.0],
        "radius_mm": 3.2,
        "tolerance_mm": 0.05
      }
    },
    {
      "feature_id": "HOLE_RELIEF_0002",
      "type": "HOLE",
      "role": "RELIEF",
      "signature": {
        "center_mm": [110.0, 75.0, 0.0],
        "axis": [0.0, 0.0, 1.0],
        "radius_mm": 1.0,
        "tolerance_mm": 0.05
      }
    }
  ]
}
```

---

## 4. Geometry Validation

AMG는 AI inference 전에 입력 형상이 AMG-SM-V1 범위에 속하는지 판정한다.

### 4.1 단일 connected solid 검사

```text
body_count == 1
solid_is_closed == true
connected_components == 1
```

실패 manifest:

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "OUT_OF_SCOPE",
  "reason": "not_single_connected_solid"
}
```

### 4.2 일정 두께 검사

B-rep face sample point 집합을 \(P=\{p_i\}\)로 둔다. 각 sample point에서 inward normal 방향으로 반대쪽 face까지의 거리 \(d_i\)를 계산한다.

\[
\hat{t}=\operatorname{median}_i(d_i)
\]

\[
\epsilon_t=\frac{P_{95}(d_i)-P_5(d_i)}{\hat{t}}
\]

허용 조건:

```text
|t_config - t_hat| / t_config <= 0.05
epsilon_t <= 0.08
```

통과하면 다음 값을 사용한다.

```text
thickness_mm = t_hat
```

실패 manifest:

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "OUT_OF_SCOPE",
  "reason": "non_constant_thickness"
}
```

### 4.3 Midsurface 가능성 검사

반대 face pair graph \(G_{pair}\)를 구성한다. 전체 유효 sheet area 중 pair가 형성된 비율을 \(\rho_{pair}\)라고 한다.

\[
\rho_{pair}=
\frac{A_{paired}}{A_{solid\ surface}/2}
\]

허용 조건:

```text
rho_pair >= 0.90
```

실패 manifest:

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "OUT_OF_SCOPE",
  "reason": "midsurface_pairing_failed"
}
```

---

## 5. B-rep Graph와 AI Input Layer

### 5.1 Graph 구조

AMG는 STEP file text를 직접 학습 입력으로 사용하지 않는다. STEP을 CAD kernel 또는 ANSA import 결과로 해석한 뒤 다음 graph를 구성한다.

\[
G_B=(V,E)
\]

Node type:

```text
PART
FACE
EDGE
COEDGE
VERTEX
FEATURE_CANDIDATE
```

Edge type:

```text
PART_HAS_FACE
FACE_HAS_COEDGE
COEDGE_HAS_EDGE
EDGE_HAS_VERTEX
COEDGE_NEXT
COEDGE_PREV
COEDGE_MATE
FACE_ADJACENT_FACE
FEATURE_CONTAINS_FACE
FEATURE_CONTAINS_EDGE
```

### 5.2 Part tensor

\[
X_P\in\mathbb{R}^{1\times d_P}
\]

```text
x_part = [
  class_one_hot,
  W / L_ref,
  H / L_ref,
  t / L_ref,
  A_mid / L_ref^2,
  num_faces_norm,
  num_edges_norm,
  num_holes_norm,
  num_slots_norm,
  num_bends_norm,
  h0 / L_ref,
  h_min / L_ref,
  h_max / L_ref,
  growth_rate_max
]
```

정규화 길이:

\[
L_{ref}=\sqrt{A_{mid}}
\]

여기서 \(A_{mid}\)는 midsurface 예상 면적이다.

### 5.3 Face tensor

\[
X_F\in\mathbb{R}^{N_F\times d_F}
\]

```text
x_face = [
  surface_type_one_hot,             # PLANE, CYLINDER, CONE, NURBS
  area / L_ref^2,
  perimeter / L_ref,
  bbox_dx / L_ref,
  bbox_dy / L_ref,
  bbox_dz / L_ref,
  centroid_x / L_ref,
  centroid_y / L_ref,
  centroid_z / L_ref,
  normal_x,
  normal_y,
  normal_z,
  outer_loop_count,
  inner_loop_count,
  edge_count_norm,
  min_curvature * L_ref,
  max_curvature * L_ref,
  mean_curvature * L_ref,
  gaussian_curvature * L_ref^2,
  is_major_planar_patch,
  is_bend_patch,
  is_thickness_side_face,
  local_feature_size / L_ref
]
```

### 5.4 Edge / coedge tensor

\[
X_E\in\mathbb{R}^{N_E\times d_E}
\]

```text
x_edge = [
  curve_type_one_hot,               # LINE, CIRCLE, ARC, ELLIPSE, SPLINE
  length / L_ref,
  radius / L_ref,
  center_x / L_ref,
  center_y / L_ref,
  center_z / L_ref,
  tangent_x,
  tangent_y,
  tangent_z,
  dihedral_angle_rad / pi,
  is_inner_loop,
  is_outer_boundary,
  is_circular_loop_member,
  is_slot_member,
  is_bend_boundary,
  adjacent_face_type_1,
  adjacent_face_type_2
]
```

Coedge는 oriented edge이다. 다음 topology walk를 모델 입력으로 제공한다.

```text
coedge_next
coedge_prev
coedge_mate
coedge_parent_face
coedge_parent_loop
```

### 5.5 Feature tensor

Feature candidate마다 다음 vector를 만든다.

```text
x_feature = [
  feature_type_one_hot,             # HOLE, SLOT, CUTOUT, BEND, FLANGE
  role_one_hot,                     # BOLT, MOUNT, RELIEF, DRAIN, ... UNKNOWN
  size_1 / L_ref,
  size_2 / L_ref,
  radius / L_ref,
  width / L_ref,
  length / L_ref,
  distance_to_outer_boundary / L_ref,
  distance_to_nearest_feature / L_ref,
  clearance_ratio,
  expected_action_mask
]
```

`expected_action_mask`는 configuration과 role로부터 계산한다. 예를 들어 `ROLE=UNKNOWN`인 feature는 `SUPPRESS=0`이다.

---

## 6. Deterministic Feature Detection Rules

Feature detection은 AI 이전에 deterministic하게 수행한다. AI는 feature를 처음부터 발견하는 모델이 아니라, 검출된 feature candidate의 action과 numeric control을 예측하는 모델이다.

### 6.1 Circular through hole

검출 조건:

```text
1. planar sheet face 또는 midsurface candidate face에 inner loop 존재
2. inner loop edge가 circle 또는 arc 집합
3. loop를 하나의 circle로 fitting했을 때 RMS error <= 0.03 * radius
4. loop normal이 sheet normal과 5° 이내
5. solid 두께 방향으로 관통
```

추출 parameter:

```text
center c
axis a
radius r
diameter d = 2r
clearance_to_boundary c_b
clearance_to_nearest_feature c_f
role from feature_overrides or STEP name, otherwise UNKNOWN
```

### 6.2 Slot

검출 조건:

```text
1. inner loop 존재
2. loop가 line 2개 + semicircle/arc 2개로 구성
3. 두 arc radius 차이 <= 5%
4. 두 line segment가 서로 평행
```

추출 parameter:

```text
center c
orientation vector u
slot_width w_s = 2r_end
slot_length L_s
end_radius r_end
role
```

### 6.3 General cutout

검출 조건:

```text
1. inner loop 존재
2. HOLE 또는 SLOT 조건을 만족하지 않음
3. loop area / part midsurface area >= 0.01 이면 CUTOUT으로 분류
```

추출 parameter:

```text
area A_cutout
bbox width w_c
bbox height h_c
corner radius candidates
role
```

### 6.4 Bend patch

검출 조건:

```text
1. cylindrical surface 또는 near-cylindrical NURBS strip
2. radius R_b within [0.3t, 10t]
3. 양쪽에 major planar patch가 연결됨
4. bend axis가 두 planar patch의 교선 방향과 일치
```

추출 parameter:

```text
inside_radius R_i
mid_radius R_m = R_i + t/2
bend_angle phi
arc_length s_b = phi * R_m
adjacent_planar_faces
```

### 6.5 Flange

검출 조건:

```text
1. bend patch 한쪽에 연결된 planar patch
2. 해당 planar patch의 free outer boundary 존재
3. patch width w_f가 주요 web width보다 작음
```

추출 parameter:

```text
flange_width w_f
flange_length L_f
connected_bend_id
free_edge_ids
```

---

## 7. Mesh-Control Manifest Schema

AMG AI와 Rule Projector의 최종 출력은 `mesh_control_manifest.json`이다.

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "VALID",
  "cad_file": "input.step",
  "unit": "mm",
  "part": {
    "part_name": "SMT_SM_L_BRACKET_W160_H90_T1p2_A83F",
    "part_class": "SM_L_BRACKET",
    "idealization": "midsurface_shell",
    "thickness_mm": 1.2,
    "element_type": "quad_dominant_shell",
    "batch_session": "AMG_SHELL_CONST_THICKNESS_V1"
  },
  "global_mesh": {
    "h0_mm": 4.0,
    "h_min_mm": 0.6,
    "h_max_mm": 8.0,
    "growth_rate_max": 1.3,
    "quality_profile": "AMG_QA_SHELL_V1"
  },
  "features": [
    {
      "feature_id": "HOLE_BOLT_0001",
      "type": "HOLE",
      "role": "BOLT",
      "action": "KEEP_WITH_WASHER",
      "geometry_signature": {
        "center_mm": [42.0, 30.0, 0.0],
        "axis": [0.0, 0.0, 1.0],
        "radius_mm": 3.2
      },
      "controls": {
        "edge_target_length_mm": 0.84,
        "circumferential_divisions": 24,
        "washer_rings": 2,
        "washer_outer_radius_mm": 7.5,
        "radial_growth_rate": 1.25
      }
    },
    {
      "feature_id": "BEND_STRUCTURAL_0005",
      "type": "BEND",
      "role": "STRUCTURAL",
      "action": "KEEP_WITH_BEND_ROWS",
      "controls": {
        "bend_rows": 3,
        "bend_target_length_mm": 1.8,
        "growth_rate": 1.25
      }
    }
  ],
  "entity_matching": {
    "position_tolerance_mm": 0.05,
    "angle_tolerance_deg": 2.0,
    "radius_tolerance_mm": 0.03,
    "use_geometry_signature": true,
    "use_topology_signature": true
  }
}
```

`status=OUT_OF_SCOPE`이면 다음 구조를 사용한다.

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "OUT_OF_SCOPE",
  "reason": "non_constant_thickness"
}
```

`status=MESH_FAILED`이면 다음 구조를 사용한다.

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "MESH_FAILED",
  "reason": "quality_not_satisfied_after_retry"
}
```

---

## 8. Refinement Rules

### 8.1 Global sizing field

AMG의 local target size field는 다음과 같이 정의한다.

\[
h(x)=\operatorname{clip}
\left(
\min[
  h_0,
  h_{curv}(x),
  h_{feature}(x),
  h_{flange}(x),
  h_{bend}(x)
],
h_{min},
h_{max}
\right)
\]

여기서:

```text
h0          : global target shell element length
h_curv      : curvature capture size
h_feature   : hole, slot, cutout perimeter size
h_flange    : flange width-based size
h_bend      : bend arc row size
h_min/max   : AMG_QA_SHELL_V1의 size bound
```

### 8.2 Curvature rule

반지름 \(R\)인 곡선/곡면을 길이 \(h\)의 chord로 근사할 때 chord error \(\delta\)는 다음과 같이 근사된다.

\[
\delta \approx \frac{h^2}{8R}
\]

허용 chord error \(\delta_{max}\)를 만족하려면 다음을 사용한다.

\[
h_{curv}\le \sqrt{8R\delta_{max}}
\]

AMG-SM-V1의 기본값:

```text
delta_max = min(0.05 * t, 0.02 * h0)
h_curv = sqrt(8 * R * delta_max)
```

Flat face에서는 \(R=\infty\)로 처리하여 curvature refinement 항을 적용하지 않는다.

### 8.3 Circular hole rule

Hole diameter를 \(d=2r\)라고 한다.

#### 8.3.1 Action rule

```text
if role in {BOLT, MOUNT}:
    action = KEEP_WITH_WASHER

elif role in {RELIEF, DRAIN}
     and config.feature_policy.small_relief_or_drain_suppress == true
     and d <= min(0.60*h0, 2.0*t):
    action = SUPPRESS

else:
    action = KEEP_REFINED
```

`role=UNKNOWN`이면 action은 `KEEP_REFINED`이다.

#### 8.3.2 Circumferential divisions

```text
if role in {BOLT, MOUNT}: n_min = bolt_hole_min_divisions
else:                     n_min = retained_hole_min_divisions
```

\[
n_\theta =
\operatorname{make\_even}
\left(
\max
\left(
n_{min},
\left\lceil \frac{2\pi r}{h_0} \right\rceil
\right)
\right)
\]

\[
h_{hole}=\frac{2\pi r}{n_\theta}
\]

`make_even(n)`은 홀수 \(n\)을 \(n+1\)로 올리고, 짝수 \(n\)은 그대로 둔다.

#### 8.3.3 Washer rule

Washer는 `BOLT` 또는 `MOUNT` role에 적용한다.

```text
washer_rings = 2
R_w_raw = max(2.0*r, r + washer_rings*h_hole)
R_w_limit = 0.45 * min(clearance_to_boundary, clearance_to_nearest_feature)
R_w = min(R_w_raw, R_w_limit)
```

Washer 공간이 부족하면 다음 action으로 projection한다.

```text
if R_w < r + 1.5*h_hole:
    action = KEEP_REFINED
    washer_rings = 0
```

### 8.4 Slot rule

Slot width를 \(w_s\), length를 \(L_s\), end radius를 \(r_e=w_s/2\)라고 한다.

```text
h_slot = min(h0, w_s / 3)
n_end = make_even(max(slot_end_min_divisions, ceil(pi*r_e / h_slot)))
straight_edge_divisions = max(2, ceil((L_s - w_s) / h_slot))
```

Action:

```text
if role in {MOUNT, PASSAGE, STRUCTURAL}:
    action = KEEP_REFINED

elif role in {RELIEF, DRAIN}
     and config.feature_policy.small_relief_or_drain_suppress == true
     and w_s <= min(0.60*h0, 2.0*t):
    action = SUPPRESS

else:
    action = KEEP_REFINED
```

### 8.5 Cutout rule

Cutout bounding box dimensions를 \(w_c\), \(h_c\)라고 한다.

```text
h_cutout = min(h0, min(w_c, h_c) / 4)
perimeter_growth_rate = 1.25
```

Action:

```text
if cutout_area / midsurface_area >= 0.01:
    action = KEEP_REFINED

elif role in {RELIEF, DRAIN}
     and config.feature_policy.small_relief_or_drain_suppress == true:
    action = SUPPRESS

else:
    action = KEEP_REFINED
```

### 8.6 Bend rule

Bend mid-radius:

\[
R_m=R_i+\frac{t}{2}
\]

Bend arc length:

\[
s_b=\phi R_m
\]

Bend rows:

\[
n_b=
\operatorname{clamp}
\left(
\left\lceil \frac{s_b}{h_{curv}} \right\rceil,
n_{bend,min},
n_{bend,max}
\right)
\]

Bend target length:

\[
h_{bend}=\frac{s_b}{n_b}
\]

기본값:

```text
n_bend_min = 2
n_bend_max = 6
growth_rate = 1.25
action = KEEP_WITH_BEND_ROWS
```

### 8.7 Flange rule

Flange width를 \(w_f\)라고 한다.

\[
n_f=\max\left(2,\left\lceil \frac{w_f}{h_0}\right\rceil\right)
\]

\[
h_{flange}=\frac{w_f}{n_f}
\]

Free edge에는 다음 길이를 적용한다.

```text
h_free_edge = min(h0, h_flange)
action = KEEP_WITH_FLANGE_SIZE
```

### 8.8 Growth-rate smoothing

AI가 예측한 raw size를 \(\hat{h}_i\)라고 할 때, AMG는 다음 convex projection을 수행한다.

\[
\min_{\tilde{h}_i}
\sum_i w_i
\left(
\log \tilde{h}_i-\log \hat{h}_i
\right)^2
\]

subject to:

\[
h_{min}\le \tilde{h}_i \le h_{max}
\]

\[
\left|\log \tilde{h}_i-\log \tilde{h}_j\right|
\le \log g_{max}
\quad \forall(i,j)\in E_{adj}
\]

실행 방식:

```text
1. hole, slot, bend control은 높은 weight를 둔다.
2. 일반 face는 낮은 weight를 둔다.
3. constraint를 위반하는 size jump는 큰 h를 줄이거나 작은 h 주변 transition zone을 확장한다.
4. projection 결과 h_tilde를 ANSA local size control로 전달한다.
```

---

## 9. AI Model Design

### 9.1 Model role

AMG-SM-V1에서 AI 모델은 다음 mapping을 학습한다.

\[
F_\psi:(G_B,C)\rightarrow \hat{\theta}
\]

AI 출력은 Rule Projector를 통과한 뒤 manifest가 된다.

\[
\theta=\Pi_{rules}(\hat{\theta},B,C)
\]

`Π_rules`는 다음을 강제한다.

```text
constant thickness validation result
feature role별 action mask
h_min / h_max
growth_rate_max
washer clearance
bend row bound
unknown feature suppress mask
```

### 9.2 Architecture

```text
B-rep Extractor
    ↓
Deterministic Feature Candidate Generator
    ↓
Heterogeneous B-rep GNN
    ↓
Feature Aggregation Layer
    ↓
Multi-head Predictor
    ↓
Rule Projector
    ↓
mesh_control_manifest.json
```

GNN node update 예시는 다음과 같다.

\[
z_i^{(l+1)}=
\phi_{type(i)}
\left(
z_i^{(l)},
\sum_{r\in R}
\sum_{j\in \mathcal{N}_r(i)}
\alpha_r
\psi_r(z_i^{(l)},z_j^{(l)},e_{ij}^{(r)})
\right)
\]

여기서:

```text
r        : edge relation type
N_r(i)   : relation r로 연결된 이웃 node 집합
phi      : node type별 MLP
psi_r    : relation type별 message MLP
alpha_r  : relation attention weight
```

### 9.3 Output heads

| head | target | loss |
|---|---|---|
| `part_class_head` | `SM_FLAT_PANEL`, `SM_L_BRACKET`, ... | cross entropy |
| `feature_type_head` | `HOLE`, `SLOT`, `CUTOUT`, `BEND`, `FLANGE` | cross entropy |
| `feature_action_head` | `KEEP_REFINED`, `KEEP_WITH_WASHER`, `SUPPRESS`, `KEEP_WITH_BEND_ROWS`, `KEEP_WITH_FLANGE_SIZE` | masked cross entropy |
| `log_h_head` | `log(h_face)`, `log(h_edge)` | Huber loss |
| `division_head` | `n_theta`, `slot divisions`, `bend rows` | ordinal CE 또는 Huber |
| `quality_risk_head` | quality failure probability | BCE |

### 9.4 Loss function

\[
L =
\lambda_c L_{class}
+\lambda_a L_{action}
+\lambda_h L_h
+\lambda_d L_{division}
+\lambda_q L_{quality}
+\lambda_r L_{rule}
\]

where:

\[
L_h=\operatorname{Huber}(\log\hat{h}-\log h^*)
\]

\[
L_{rule}=
\sum_i \max(0,h_{min}-\hat{h}_i)^2
+\sum_i \max(0,\hat{h}_i-h_{max})^2
+\sum_{(i,j)}
\max\left(0,\frac{\hat{h}_i}{\hat{h}_j}-g_{max}\right)^2
\]

---

## 10. Code-Generated Dataset Contract

AMG-SM-V1의 supervised 학습 데이터는 CDF-SM-ANSA-V1이 생성한다. AMG는 CDF code를 import하지 않고, versioned files와 JSON schema만 읽는다.

### 10.1 Dataset pipeline

```text
[1] sample geometry parameters
[2] build constant-thickness sheet-metal CAD
[3] export STEP
[4] write feature_truth.json
[5] extract B-rep graph
[6] detect feature candidates
[7] generate AMG-compatible rule manifest
[8] run ANSA oracle
[9] evaluate mesh quality
[10] save accepted sample
```

### 10.2 Geometry families

| family | parameters | included features |
|---|---|---|
| `FLAT_PANEL` | W, H, t, corner radius | holes, slots, cutouts |
| `SINGLE_FLANGE` | W, H, t, flange width, bend radius, bend angle | holes, slots, one bend |
| `L_BRACKET` | web width, flange width, t, bend radius, bend angle | holes on each leg, bend |
| `U_CHANNEL` | base width, side width, t, two bend radii | holes, slots, two flanges |
| `HAT_CHANNEL` | top width, side width, flange width, t, four bend radii | holes, slots, bends |

### 10.3 Parameter ranges

```text
W, H                : 60 ~ 300 mm
t                   : 0.8 ~ 3.0 mm
h0                  : 3.0 ~ 6.0 mm
bend inside radius  : 0.5t ~ 6t
bend angle          : 45° ~ 120°
hole radius         : 0.5 ~ 8.0 mm
slot width          : 3.0 ~ 20.0 mm
slot length         : 2*width ~ 8*width
cutout area ratio   : 0.005 ~ 0.20
```

### 10.4 Geometry validity constraints

```text
hole_distance_to_boundary >= r + 2*h_min
hole_distance_to_hole     >= r_i + r_j + 2*h_min
slot_distance_to_boundary >= slot_width/2 + 2*h_min
bend_radius >= 0.5*t
flange_width >= 2*h_min
no self-intersection
single connected solid
constant thickness test pass
```

### 10.5 Auto label generation

For each generated feature:

```text
CAD operation creates geometry
CAD operation writes feature_truth record
rule_labeler computes action and numeric controls
ANSA oracle validates the rule label
quality report is attached
```

Feature truth example:

```json
{
  "feature_id": "HOLE_BOLT_0001",
  "type": "HOLE",
  "role": "BOLT",
  "center_mm": [42.0, 30.0, 0.0],
  "axis": [0.0, 0.0, 1.0],
  "radius_mm": 3.2,
  "created_by": "cadgen.circular_cut"
}
```

### 10.6 Dataset directory layout

```text
sample_000001/
  cad/
    input.step
  metadata/
    amg_config.json
    feature_truth.json
    geometry_params.json
  graph/
    brep_graph.npz
    graph_schema.json
    face_features.npy
    edge_features.npy
    coedge_features.npy
    feature_features.npy
  labels/
    mesh_control_manifest.json
    face_labels.json
    edge_labels.json
    feature_labels.json
  mesh/
    ansa_oracle_mesh.bdf
  reports/
    geometry_validation.json
    feature_matching_report.json
    ansa_quality_report.json
    sample_acceptance.json
```

### 10.7 Dataset phases

| phase | samples | goal |
|---|---:|---|
| `D0_SANITY` | 1,000 | flat panels + circular holes only |
| `D1_FEATURES` | 10,000 | holes, slots, cutouts |
| `D2_BENDS` | 20,000 | L-bracket, U-channel, bends, flanges |
| `D3_ANSA_ORACLE` | 10,000 | ANSA quality-validated manifest |
| `D4_SCOPE_CHECK` | 100~300 | 실제 일정 두께 판금 STEP에 대한 scope validation |

---

## 11. ANSA Integration

### 11.1 Adapter interface

AMG는 ANSA 내부 API 이름에 직접 종속되지 않도록 adapter interface를 고정한다. 실제 ANSA Python 함수명은 설치 버전의 scripting documentation에 맞춰 adapter 내부에서 binding한다.

```python
class AnsaAdapter:
    def import_step(self, step_path: str) -> None: ...
    def run_geometry_cleanup(self) -> None: ...
    def build_entity_index(self) -> dict: ...
    def match_entities(self, manifest: dict) -> dict: ...
    def create_sets(self, entity_map: dict) -> None: ...
    def extract_midsurface(self, part_spec: dict) -> None: ...
    def assign_thickness(self, thickness_mm: float) -> None: ...
    def assign_batch_session(self, session_name: str) -> None: ...
    def apply_edge_length(self, edge_set: str, h_mm: float) -> None: ...
    def apply_hole_washer(self, feature_set: str, controls: dict) -> None: ...
    def fill_hole(self, feature_set: str) -> None: ...
    def apply_bend_rows(self, feature_set: str, controls: dict) -> None: ...
    def apply_flange_size(self, feature_set: str, controls: dict) -> None: ...
    def run_batch_mesh(self, quality_template: str) -> None: ...
    def export_quality_report(self, path: str) -> None: ...
    def export_solver_deck(self, solver: str, path: str) -> None: ...
```

### 11.2 Entity matching

STEP import 후 entity id가 바뀔 수 있으므로 AMG는 geometry signature와 topology signature를 사용한다.

Geometry signature:

```json
{
  "entity_type": "circular_loop",
  "center_mm": [42.0, 30.0, 0.0],
  "axis": [0.0, 0.0, 1.0],
  "radius_mm": 3.2,
  "bbox_mm": [38.8, 26.8, -0.1, 45.2, 33.2, 0.1]
}
```

Topology signature:

```json
{
  "loop_type": "inner",
  "edge_count": 1,
  "adjacent_surface_types": ["PLANE", "CYLINDER"],
  "parent_face_surface_type": "PLANE"
}
```

Matching score:

\[
S=
w_c\exp\left(-\frac{\|c-c'\|}{\tau_c}\right)
+w_r\exp\left(-\frac{|r-r'|}{\tau_r}\right)
+w_a|a\cdot a'|
+w_tI_{topology}
\]

기본 weight:

```text
w_c = 0.35
w_r = 0.25
w_a = 0.20
w_t = 0.20
```

자동 적용 기준:

```text
S >= 0.90 : apply
S < 0.90  : manifest status = OUT_OF_SCOPE, reason = entity_matching_failed
```

동일 signature 후보가 2개 이상이면 다음 결과를 반환한다.

```json
{
  "status": "OUT_OF_SCOPE",
  "reason": "ambiguous_entity_matching"
}
```

### 11.3 Manifest to ANSA mapping

| AMG manifest 항목 | ANSA adapter operation |
|---|---|
| `idealization=midsurface_shell` | midsurface extraction |
| `thickness_mm` | shell property thickness assignment |
| `batch_session` | Batch Mesh Session 지정 |
| `h0_mm` | global shell target length |
| `growth_rate_max` | mesh gradation / growth setting |
| `HOLE KEEP_REFINED` | circular edge perimeter length control |
| `HOLE KEEP_WITH_WASHER` | hole treatment + controlled washer |
| `HOLE SUPPRESS` | fill hole / defeature |
| `SLOT KEEP_REFINED` | slot perimeter local length control |
| `SLOT SUPPRESS` | fill slot / defeature |
| `CUTOUT KEEP_REFINED` | cutout loop local length control |
| `BEND KEEP_WITH_BEND_ROWS` | bend/fillet treatment with element rows |
| `FLANGE KEEP_WITH_FLANGE_SIZE` | flange treatment + free-edge length control |
| `AMG_QA_SHELL_V1` | quality criteria template |

### 11.4 ANSA execution sequence

```text
1. import STEP
2. run geometry check and cleanup
3. verify constant thickness from ANSA geometry
4. extract midsurface
5. assign shell thickness
6. build entity index
7. match manifest feature signatures to ANSA entities
8. create feature sets
9. apply global shell session
10. apply local edge and feature controls
11. run Batch Mesh
12. run quality check
13. apply deterministic retry policy when quality report maps to a retry case
14. export solver deck and quality report
```

### 11.5 Retry policy

Retry는 최대 2회 수행한다.

```text
Case A: hole perimeter quality fail
  h_hole <- max(h_min, 0.75*h_hole)
  n_theta <- make_even(ceil(2*pi*r/h_hole))

Case B: bend warpage/skew fail
  bend_rows <- min(max_bend_rows, bend_rows + 1)

Case C: flange narrow-face fail
  h_flange <- max(h_min, 0.80*h_flange)

Case D: global growth fail
  growth_rate_max <- min(1.20, current_growth_rate_max)
```

두 번째 retry 후에도 실패하면 다음 manifest를 기록한다.

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "MESH_FAILED",
  "reason": "quality_not_satisfied_after_retry"
}
```

---

## 12. Quality Criteria: `AMG_QA_SHELL_V1`

AMG-SM-V1은 다음 shell mesh quality 기준을 사용한다. 모든 수치는 명시적 baseline이다.

| metric | condition |
|---|---:|
| element type | CQUAD4 dominant, CTRIA3 allowed |
| quad fraction | >= 0.85 |
| tria fraction | <= 0.15 |
| aspect ratio | <= 5.0 |
| skew angle | <= 60° |
| warpage | <= 15° |
| min angle | >= 30° |
| max angle | <= 150° |
| Jacobian | >= 0.50 |
| edge length min | >= h_min |
| edge length max | <= h_max |
| free edge | only geometric boundary allowed |
| duplicate elements | 0 |
| negative Jacobian | 0 |
| unmeshed face | 0 |

Feature-level checks:

| feature | check |
|---|---|
| retained circular hole | achieved `n_theta` exactly or ±1 after ANSA reconstruction |
| washer hole | washer ring count >= requested count unless clearance downgrade was triggered |
| slot | both semicircular ends have at least `slot_end_min_divisions` |
| bend | bend rows >= requested `bend_rows` |
| flange | elements across flange width >= 2 |

---

## 13. Repository Structure and Milestones

### 13.1 Repository structure

```text
ai_mesh_generator/
  configs/
    amg_config.schema.json
    quality_amg_shell_v1.json
  brep/
    import_step.py
    graph_builder.py
    thickness_check.py
    midsurface_check.py
    curvature.py
    feature_detect.py
  labels/
    rule_manifest.py
    sizing_field.py
    smoothing_projection.py
  model/
    dataset.py
    hetero_brep_gnn.py
    heads.py
    losses.py
    train.py
    infer.py
  ansa/
    ansa_adapter_interface.py
    ansa_adapter_vXX.py
    manifest_runner.py
  validation/
    geometry_validation.py
    mesh_quality.py
    report_parser.py
    acceptance.py
  scripts/
    train_amg.py
    run_amg_inference.py
    run_ansa_batch.py
```

### 13.2 Milestones

#### M0: Rule-only prototype

```text
input.step + amg_config.json
  → B-rep extraction
  → feature detection
  → deterministic manifest
  → ANSA mesh
  → quality report
```

Acceptance:

```text
100 flat panel samples
STEP import success >= 98%
feature detection F1 >= 0.95
mesh success >= 90%
```

#### M1: Code-generated dataset ingestion

```text
CDF-SM-ANSA-V1 generated dataset
feature_truth.json for all samples
AMG-compatible manifest labels
ANSA quality report attached
```

Acceptance:

```text
accepted dataset samples >= 8,000
OUT_OF_SCOPE rejection reason logged
feature-label consistency >= 0.98
```

#### M2: AI manifest predictor

```text
B-rep graph input
feature action + numeric control output
rule projector enforced
```

Acceptance:

```text
feature type accuracy >= 0.95
feature action accuracy >= 0.90
log(h) median relative error <= 0.20
n_theta within ±2 accuracy >= 0.90
```

#### M3: ANSA execution

```text
AI manifest
  → ANSA adapter
  → midsurface shell mesh
  → quality report
  → solver deck export
```

Acceptance:

```text
unseen generated STEP 200개
first-pass mesh success >= 0.85
after-retry mesh success >= 0.95
hard quality violation = 0 for accepted samples
feature-level control satisfaction >= 0.90
```

#### M4: Scope validation on real constant-thickness sheet-metal STEP

```text
실제 단일 판금 STEP 100~300개
AMG scope validation
manifest generation
ANSA mesh execution
```

Acceptance:

```text
valid constant-thickness part correctly accepted
variable-thickness or assembly part correctly rejected
accepted real part mesh success >= 0.80
```

---

## 14. Implementation Algorithms

### 14.1 Main pipeline pseudocode

```python
def run_amg(step_path: str, config_path: str, overrides_path: str | None):
    config = read_json(config_path)
    overrides = read_json(overrides_path) if overrides_path else {"features": []}

    brep = import_step_as_brep(step_path)

    validation = validate_constant_thickness_sheet(brep, config)
    if not validation.valid:
        return write_out_of_scope_manifest(validation.reason)

    graph = build_brep_graph(brep, config)
    features = detect_sheet_metal_features(brep, graph, overrides)

    x = build_model_input(graph, features, config)
    raw_pred = model_inference(x)

    manifest = project_to_valid_manifest(raw_pred, graph, features, config)
    write_json(manifest, "mesh_control_manifest.json")

    ansa_result = run_ansa_manifest(manifest)
    quality = parse_quality_report(ansa_result.report)

    if quality.pass_all:
        return export_success(manifest, ansa_result)

    current_manifest = manifest
    for _ in range(2):
        retry_manifest = deterministic_retry(current_manifest, quality)
        retry_result = run_ansa_manifest(retry_manifest)
        retry_quality = parse_quality_report(retry_result.report)

        if retry_quality.pass_all:
            return export_success(retry_manifest, retry_result)

        current_manifest = retry_manifest
        quality = retry_quality

    return export_failure(current_manifest, quality)
```

### 14.2 Manifest projection pseudocode

```python
def project_to_valid_manifest(raw_pred, graph, features, config):
    manifest = init_manifest(config)

    for feat in features:
        action = decode_action(raw_pred, feat)

        if feat.role == "UNKNOWN" and action == "SUPPRESS":
            action = "KEEP_REFINED"

        if feat.type == "HOLE":
            controls, action = circular_hole_controls(feat, action, config)
        elif feat.type == "SLOT":
            controls, action = slot_controls(feat, action, config)
        elif feat.type == "CUTOUT":
            controls, action = cutout_controls(feat, action, config)
        elif feat.type == "BEND":
            action = "KEEP_WITH_BEND_ROWS"
            controls = bend_controls(feat, config)
        elif feat.type == "FLANGE":
            action = "KEEP_WITH_FLANGE_SIZE"
            controls = flange_controls(feat, config)
        else:
            continue

        controls = enforce_bounds(controls, config.mesh_policy)
        manifest.features.append(make_feature_record(feat, action, controls))

    manifest = smooth_size_field(manifest, graph, config)
    return manifest
```

---

## 15. Research Basis

AMG-SM-V1의 기술 선택은 다음 근거에 기반한다.

1. **STEP/B-rep extraction**  
   ISO 10303-42는 geometric and topological representation resource를 정의하며, B-rep, parametric curves/surfaces, topological connectivity를 CAD shape exchange의 기반으로 제공한다.  
   Reference: https://www.iso.org/standard/89538.html

2. **B-rep graph neural network**  
   BRepNet은 B-rep의 oriented coedge topology를 이용해 solid model에 직접 작동하는 neural architecture를 제안했다. 이는 STEP을 voxel/point cloud로 변환하지 않고 face/edge/coedge graph를 직접 사용하는 AMG 구조의 근거이다.  
   Reference: https://arxiv.org/abs/2104.00706

3. **UV surface representation**  
   UV-Net은 B-rep surface/curve의 UV parameter domain과 adjacency graph를 결합해 CAD B-rep를 학습하는 방법을 제안했다. AMG는 analytical face/edge feature를 기본으로 사용하고, NURBS 또는 complex trim에는 UV patch tensor를 추가할 수 있다.  
   Reference: https://arxiv.org/abs/2006.10211

4. **Mesh graph and adaptivity**  
   MeshGraphNets는 mesh graph에서 message passing과 adaptive discretization을 학습할 수 있음을 보였다. AMG는 mesh를 직접 생성하지 않고 local mesh size와 refinement control을 graph prediction 문제로 정의한다.  
   Reference: https://arxiv.org/abs/2010.03409

5. **ANSA execution layer**  
   ANSA Batch Meshing은 middle surface extraction, shell/volume meshing, feature treatment rules, local refinement/coarsening, controlled washers, element rows on fillets/flanges, quality criteria 기반 자동 correction을 제공한다.  
   Reference: https://www.beta-cae.com/brochure/ansa_for_automatic_meshing.pdf

6. **ANSA scripting**  
   ANSA scripting training material은 Python, ANSA Python API, ANSA entity interaction, script editor, text file handling을 다룬다. AMG manifest를 ANSA adapter가 읽어 자동 실행하는 구조는 이 기능 범위와 일치한다.  
   Reference: https://www.beta-cae.com/courses/ansa_scripting_basic.pdf

---

## 16. Final Definition

AMG-SM-V1은 다음 pipeline으로 완결된다.

```text
STEP solid of constant-thickness sheet-metal part
  + AMG config
  + optional feature role overrides
    ↓
geometry validation
    ↓
B-rep graph extraction
    ↓
deterministic sheet-metal feature detection
    ↓
AI manifest prediction
    ↓
rule projection and sizing-field smoothing
    ↓
mesh_control_manifest.json
    ↓
ANSA Python adapter
    ↓
midsurface extraction + shell thickness assignment
    ↓
Batch Mesh + hole/slot/cutout/bend/flange local controls
    ↓
AMG_QA_SHELL_V1 quality check
    ↓
VALID_MESH, OUT_OF_SCOPE, or MESH_FAILED
```

이 정의에서 입력, 출력, feature class, action enum, refinement rule, quality 기준, ANSA 연계 방식은 모두 명시적 규칙으로 표현된다. AMG-SM-V1의 실행 결과는 다음 세 상태 중 하나이다.

```text
VALID_MESH    : solver-ready shell mesh와 quality report가 생성됨
OUT_OF_SCOPE  : 입력 형상이 AMG-SM-V1 범위 밖으로 판정됨
MESH_FAILED   : 범위 내 형상이지만 ANSA quality 기준을 retry 후에도 만족하지 못함
```
