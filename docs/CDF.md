# CAD_DATASET_FACTORY: CDF-SM-ANSA-V1 설계 문서

```text
Version              : CDF-SM-ANSA-V1
Scope                : constant-thickness sheet-metal single-part synthetic dataset factory
Compatibility target : AMG-SM-V1
Manifest target      : AMG_MANIFEST_SM_V1
Graph target         : AMG_BREP_GRAPH_SM_V1
Primary CAD backend  : CadQuery / OpenCASCADE through OCP
Meshing oracle       : ANSA Batch Mesh
```

## 1. 목적

`CAD_DATASET_FACTORY`, 이하 `CDF`, 는 `AMG-SM-V1` 학습용 synthetic CAD dataset을 자동 생성하는 독립 실행형 도구이다. CDF는 AI 모델이 아니며 AMG의 하위 모듈도 아니다. CDF는 일정 두께 판금 단품에 대해 다음 산출물을 코드로 생성한다.

```text
1. 일정 두께 판금 단품 solid STEP
   cad/input.step

2. 생성 시점의 feature truth
   metadata/feature_truth.json
   metadata/entity_signatures.json

3. AMG-SM-V1 학습 입력과 같은 B-rep graph tensor
   graph/brep_graph.npz
   graph/graph_schema.json

4. AMG-SM-V1이 예측해야 할 정답 manifest
   labels/amg_manifest.json

5. ANSA Batch Mesh 기반 validation 결과
   meshes/ansa_oracle_mesh.bdf
   reports/ansa_execution_report.json
   reports/ansa_quality_report.json
   reports/sample_acceptance.json
```

CDF가 해결하는 문제는 사람이 mesh label을 붙이는 문제가 아니라, CAD 형상과 AMG-compatible label을 동시에 생성하고, 그 label이 ANSA에서 실제 격자 생성에 사용 가능한지 검증하는 절차적 데이터 생성 문제이다.

```text
parameter sampler
  → sheet-metal CAD generator
  → solid STEP export
  → feature truth writer
  → independent B-rep extractor
  → deterministic AMG-compatible label generator
  → CDF-owned ANSA oracle runner
  → ANSA quality report parser
  → dataset writer
```

CDF는 AMG inference를 실행하지 않는다. CDF는 AMG가 나중에 학습 데이터로 읽을 수 있는 versioned files를 생성한다.

---

## 2. ANSA Oracle 기준

CDF-SM-ANSA-V1의 meshing oracle은 ANSA Batch Mesh이다. 이 선택은 AMG-SM-V1의 최종 실행 계층과 학습 label의 의미를 일치시키기 위한 구현 기준이다.

```text
AMG의 최종 실행 엔진 = ANSA Batch Mesh
AMG의 예측 목표     = ANSA에 전달할 mesh-control manifest
CDF의 label 검증    = ANSA workflow에서 실행 가능한 manifest 판정
```

따라서 CDF의 sample acceptance는 다음 ANSA workflow의 성공 여부로 결정한다.

```text
1. STEP import
2. geometry cleanup
3. midsurface extraction
4. feature entity matching
5. manifest local control application
6. Batch Mesh execution
7. quality criteria check
8. solver deck export
```

CDF의 oracle mesh는 학습 target connectivity가 아니다. 학습 target은 `labels/amg_manifest.json`이다. Oracle mesh는 manifest 실행 가능성과 quality satisfaction을 검증하는 수치 증거로 저장된다.

---

## 3. CDF와 AMG의 파일 계약

### 3.1 독립성 원칙

CDF와 AMG는 versioned file contract만 공유한다.

```text
contracts/
  AMG_MANIFEST_SM_V1.schema.json
  AMG_BREP_GRAPH_SM_V1.schema.json
  CDF_FEATURE_TRUTH_SM_V1.schema.json
  CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json
  CDF_ANSA_QUALITY_REPORT_SM_V1.schema.json
```

CDF repository는 위 schema 사본에 맞춰 dataset files를 생성한다. AMG repository는 같은 schema에 맞춰 dataset files를 읽는다.

### 3.2 코드 의존성 경계

CDF core code의 dependency boundary는 다음과 같다.

```text
CDF core:
  cdf/config/
  cdf/sampling/
  cdf/cadgen/
  cdf/truth/
  cdf/brep/
  cdf/labels/
  cdf/dataset/

CDF ANSA subprocess runner:
  cdf/oracle/ansa_runner.py

CDF ANSA internal script:
  cdf/oracle/ansa_scripts/
```

구현 assertion:

```python
from pathlib import Path

FORBIDDEN_AMG_IMPORT_TOKENS = ["import amg", "from amg"]

def test_cdf_has_no_amg_import():
    for path in Path("cdf").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_AMG_IMPORT_TOKENS:
            assert token not in text, f"AMG dependency found in {path}: {token}"
```

ANSA Python API import는 ANSA 내부에서 실행되는 script directory에 배치한다.

```python
from pathlib import Path

ALLOWED_ANSA_DIR = Path("cdf/oracle/ansa_scripts")
ANSA_IMPORT_TOKENS = ["import ansa", "from ansa"]

def test_ansa_import_scope():
    for path in Path("cdf").rglob("*.py"):
        if path.is_relative_to(ALLOWED_ANSA_DIR):
            continue
        text = path.read_text(encoding="utf-8")
        for token in ANSA_IMPORT_TOKENS:
            assert token not in text, f"ANSA API import outside ANSA script in {path}"
```

---

## 4. 수학적 정의

CDF config를 \(c\), random seed를 \(s\)라고 한다. CDF는 parameter vector \(p\)를 sampling한다.

\[
p\sim P_c(p;s)
\]

CAD 생성 연산자 \(G_{CAD}\)는 constant-thickness sheet-metal B-rep solid를 만든다.

\[
B=G_{CAD}(p)
\]

동시에 feature truth를 생성한다.

\[
T=G_{truth}(p)
\]

CDF의 deterministic rule \(R_{SM}\)은 AMG-compatible mesh-control label을 만든다.

\[
\theta=R_{SM}(B,T,c)
\]

ANSA oracle은 label을 수정하지 않고 sample acceptance만 판정한다.

\[
M_{ansa}=\mathcal{A}_{ANSA}(B,\theta)
\]

Accepted sample 조건은 다음이다.

\[
\operatorname{valid\_cad}(B)=1
\]

\[
\operatorname{valid\_truth\_match}(B,T)=1
\]

\[
\operatorname{valid\_schema}(\theta)=1
\]

\[
\operatorname{valid\_ansa\_mesh}(M_{ansa})=1
\]

여기서 `valid_ansa_mesh`는 다음 조건을 모두 포함한다.

```text
1. ANSA STEP import success
2. ANSA midsurface extraction success
3. feature entity matching success
4. manifest local control application success
5. ANSA Batch Mesh success
6. ANSA quality criteria hard fail count = 0
7. feature boundary control error within tolerance
```

---

## 5. CDF-SM-ANSA-V1 범위

### 5.1 생성 형상

CDF-SM-ANSA-V1은 단일 constant-thickness sheet-metal part를 생성한다.

```text
part count          : 1
body type           : closed manifold constant-thickness solid
unit                : mm
thickness t         : 0.8 mm ≤ t ≤ 3.0 mm
idealization target : midsurface shell
element family      : SHELL_QUAD_DOMINANT
meshing oracle      : ANSA Batch Mesh
```

허용 part class:

```text
SM_FLAT_PANEL
SM_SINGLE_FLANGE
SM_L_BRACKET
SM_U_CHANNEL
SM_HAT_CHANNEL
```

허용 feature type:

```text
HOLE
SLOT
CUTOUT
BEND
FLANGE
OUTER_BOUNDARY
```

허용 feature role:

```text
BOLT
MOUNT
RELIEF
DRAIN
VENT
PASSAGE
STRUCTURAL
UNKNOWN
```

허용 manifest action:

```text
KEEP_REFINED
KEEP_WITH_WASHER
SUPPRESS
KEEP_WITH_BEND_ROWS
KEEP_WITH_FLANGE_SIZE
```

### 5.2 Scope status

CDF generator와 validator는 다음 형상 조건을 생성 대상에서 제외하고 rejection reason으로 기록한다.

```text
multi_part_assembly
variable_thickness_part
non_sheet_bulk_solid_part
shell_solid_hybrid_part
solid_tetra_or_hex_volume_mesh_label
cfd_mesh_target
crash_specific_mesh_target
externally_supplied_cad_import
freeform_plastic_housing
rib_boss_louver_emboss_feature
undocumented_external_decision_rule
```

CDF-SM-ANSA-V1의 모든 label은 geometry, numeric rule, feature truth, ANSA oracle validation으로만 결정된다.

---

## 6. Part Name 규칙

CDF는 모든 part에 canonical part name을 부여한다.

```text
SMT_<CLASS>_T<TTT>_<ID>
```

필드 정의:

```text
SMT    = sheet metal target
CLASS  = SM_FLAT_PANEL, SM_SINGLE_FLANGE, SM_L_BRACKET, SM_U_CHANNEL, SM_HAT_CHANNEL
TTT    = round(thickness_mm × 100), 3자리 정수. 예: 1.20 mm → T120
ID     = P000001, P000002, ...
```

예시:

```text
SMT_SM_FLAT_PANEL_T120_P000001
SMT_SM_L_BRACKET_T160_P000381
```

다음 파일의 part name은 반드시 동일해야 한다.

```text
metadata/generator_params.json
metadata/feature_truth.json
metadata/entity_signatures.json
graph/brep_graph.npz
labels/amg_manifest.json
reports/ansa_quality_report.json
```

---

## 7. Dataset Directory 구조

CDF가 생성하는 dataset은 다음 구조를 가진다.

```text
dataset_root/
  dataset_index.json
  dataset_stats.json
  config_used.json
  contracts/
    AMG_MANIFEST_SM_V1.schema.json
    AMG_BREP_GRAPH_SM_V1.schema.json
    CDF_FEATURE_TRUTH_SM_V1.schema.json
    CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json
    CDF_ANSA_QUALITY_REPORT_SM_V1.schema.json
  splits/
    train.txt
    validation.txt
    test_seen.txt
    test_l_bracket_holdout.txt
    test_u_channel_holdout.txt
    test_dense_perforation_holdout.txt
  rejected/
    rejected_index.json
  samples/
    sample_000001/
      cad/
        input.step
        reference_midsurface.step
      metadata/
        generator_params.json
        feature_truth.json
        entity_signatures.json
      graph/
        brep_graph.npz
        graph_schema.json
        face_features.npy
        edge_features.npy
        coedge_features.npy
        feature_features.npy
        adjacency.json
      labels/
        amg_manifest.json
        face_labels.json
        edge_labels.json
        feature_labels.json
      meshes/
        ansa_oracle_mesh.bdf
        ansa_oracle_model.ansa
      reports/
        geometry_validation.json
        feature_matching_report.json
        ansa_execution_report.json
        ansa_quality_report.json
        sample_acceptance.json
```

`cad/input.step`은 AMG의 CAD input과 동일한 solid STEP이다. `cad/reference_midsurface.step`은 CDF가 생성한 reference midsurface이며 다음 검증에 사용한다.

```text
1. CDF geometry validation
2. ANSA midsurface extraction 결과와의 오차 측정
3. sample debugging visualization
```

AMG 학습 입력은 `cad/input.step`과 `graph/brep_graph.npz`이다. AMG 학습 pipeline은 `reference_midsurface.step`을 model input으로 사용하지 않는다.

---

## 8. CDF Configuration

CDF generation은 하나의 config로 재현 가능해야 한다.

```json
{
  "schema": "CDF_CONFIG_SM_ANSA_V1",
  "seed": 20260502,
  "unit": "mm",
  "num_accepted_samples": 10000,
  "amg_manifest_schema": "AMG_MANIFEST_SM_V1",
  "dataset_profile": "SM_KEEP_ALL_CUT_FEATURES_V1",
  "global_mesh_rule": {
    "element_family": "SHELL_QUAD_DOMINANT",
    "quality_profile": "AMG_QA_SHELL_V1",
    "allow_small_feature_suppression": false,
    "growth_rate_max": 1.35,
    "curvature_sagitta_ratio": 0.02,
    "min_length_factor": 0.30,
    "max_length_factor": 1.80
  },
  "part_sampling": {
    "class_weights": {
      "SM_FLAT_PANEL": 0.30,
      "SM_SINGLE_FLANGE": 0.20,
      "SM_L_BRACKET": 0.20,
      "SM_U_CHANNEL": 0.20,
      "SM_HAT_CHANNEL": 0.10
    },
    "width_mm": {"distribution": "uniform", "min": 80.0, "max": 300.0},
    "height_mm": {"distribution": "uniform", "min": 60.0, "max": 240.0},
    "thickness_mm": {"distribution": "uniform", "min": 0.8, "max": 3.0},
    "corner_radius_mm": {"distribution": "uniform", "min": 0.0, "max": 12.0},
    "bend_inner_radius_factor_t": {"distribution": "uniform", "min": 1.0, "max": 4.0},
    "flange_width_mm": {"distribution": "uniform", "min": 10.0, "max": 60.0}
  },
  "feature_sampling": {
    "hole_count": {"distribution": "integer_uniform", "min": 0, "max": 12},
    "slot_count": {"distribution": "integer_uniform", "min": 0, "max": 4},
    "cutout_count": {"distribution": "integer_uniform", "min": 0, "max": 3},
    "hole_radius_mm": {"distribution": "uniform", "min": 1.0, "max": 12.0},
    "slot_width_mm": {"distribution": "uniform", "min": 3.0, "max": 24.0},
    "slot_length_over_width": {"distribution": "uniform", "min": 2.0, "max": 8.0},
    "cutout_width_mm": {"distribution": "uniform", "min": 12.0, "max": 80.0},
    "cutout_height_mm": {"distribution": "uniform", "min": 12.0, "max": 80.0},
    "minimum_feature_clearance_factor_h0": 0.75,
    "hole_role_weights": {
      "BOLT": 0.40,
      "MOUNT": 0.10,
      "RELIEF": 0.15,
      "DRAIN": 0.10,
      "VENT": 0.10,
      "UNKNOWN": 0.15
    },
    "slot_role_weights": {
      "MOUNT": 0.35,
      "PASSAGE": 0.25,
      "RELIEF": 0.15,
      "DRAIN": 0.10,
      "UNKNOWN": 0.15
    },
    "cutout_role_weights": {
      "PASSAGE": 0.40,
      "STRUCTURAL": 0.20,
      "RELIEF": 0.15,
      "DRAIN": 0.10,
      "UNKNOWN": 0.15
    }
  },
  "validation": {
    "thickness_tolerance_abs_mm": 0.05,
    "thickness_tolerance_rel": 0.03,
    "position_tolerance_mm": 0.05,
    "angle_tolerance_deg": 2.0,
    "radius_tolerance_mm": 0.03,
    "max_generation_attempts_per_sample": 50
  },
  "ansa_oracle": {
    "enabled": true,
    "ansa_executable": "${ANSA_EXECUTABLE}",
    "batch_script": "cdf/oracle/ansa_scripts/cdf_ansa_oracle.py",
    "batch_mesh_session": "AMG_SHELL_CONST_THICKNESS_V1",
    "quality_profile": "AMG_QA_SHELL_V1",
    "solver_deck": "NASTRAN",
    "save_ansa_database": true,
    "timeout_sec_per_sample": 180,
    "max_failed_elements": 0,
    "max_feature_boundary_size_error": 0.50,
    "max_midsurface_distance_error_factor_t": 0.10
  }
}
```

허용 dataset profile:

```text
SM_KEEP_ALL_CUT_FEATURES_V1
  allow_small_feature_suppression = false
  HOLE, SLOT, CUTOUT boundary를 유지하고 refinement label을 생성한다.

SM_RULED_SMALL_FEATURE_SUPPRESSION_V1
  allow_small_feature_suppression = true
  RELIEF 또는 DRAIN role의 작은 HOLE/SLOT/CUTOUT에 대해 AMG-SM-V1 suppression rule을 적용한다.
```

---

## 9. 좌표계

모든 sample은 part-local coordinate를 사용한다.

```text
unit                         : mm
flat panel reference surface : XY plane, z = 0
thickness direction          : ±Z
solid thickness interval     : z ∈ [-t/2, +t/2]
feature center               : midsurface coordinate
hole/slot/cutout axis         : local patch normal
```

각 planar patch는 local frame을 가진다.

```json
{
  "patch_id": "PATCH_MAIN_0001",
  "patch_type": "PLANAR",
  "origin": [0.0, 0.0, 0.0],
  "u_dir": [1.0, 0.0, 0.0],
  "v_dir": [0.0, 1.0, 0.0],
  "normal": [0.0, 0.0, 1.0]
}
```

Bent sheet는 여러 planar patch와 cylindrical bend patch로 표현한다. 모든 feature 위치는 feature가 속한 patch local coordinate `(u, v)`로 sampling하고, global coordinate는 patch frame으로 변환한다.

---

## 10. 형상 Grammar

### 10.1 Part class

```text
SM_FLAT_PANEL
  one planar rectangular plate with optional corner radius.

SM_SINGLE_FLANGE
  base panel + one edge flange with cylindrical bend.

SM_L_BRACKET
  two planar plates connected by one bend.

SM_U_CHANNEL
  base panel + two opposed flanges connected by two bends.

SM_HAT_CHANNEL
  top web + side walls + two flange feet connected by four bends.
```

### 10.2 HOLE

```json
{
  "feature_id": "HOLE_BOLT_0001",
  "type": "HOLE",
  "role": "BOLT",
  "center_uv_mm": [80.0, 50.0],
  "radius_mm": 4.0,
  "patch_id": "PATCH_MAIN_0001",
  "axis_source": "patch_normal"
}
```

Role별 deterministic action:

```text
BOLT, MOUNT:
  KEEP_WITH_WASHER

RELIEF, DRAIN:
  SUPPRESS when allow_small_feature_suppression = true and d <= min(0.60 h0, 2.0 t)
  otherwise KEEP_REFINED

VENT, PASSAGE, STRUCTURAL, UNKNOWN:
  KEEP_REFINED
```

### 10.3 SLOT

```json
{
  "feature_id": "SLOT_MOUNT_0001",
  "type": "SLOT",
  "role": "MOUNT",
  "center_uv_mm": [110.0, 50.0],
  "width_mm": 8.0,
  "length_mm": 32.0,
  "angle_deg": 0.0,
  "patch_id": "PATCH_MAIN_0001",
  "axis_source": "patch_normal"
}
```

Role별 deterministic action:

```text
MOUNT, PASSAGE, STRUCTURAL:
  KEEP_REFINED

RELIEF, DRAIN:
  SUPPRESS when allow_small_feature_suppression = true and width <= min(0.60 h0, 2.0 t)
  otherwise KEEP_REFINED

VENT, UNKNOWN:
  KEEP_REFINED
```

### 10.4 CUTOUT

```json
{
  "feature_id": "CUTOUT_PASSAGE_0001",
  "type": "CUTOUT",
  "role": "PASSAGE",
  "center_uv_mm": [100.0, 60.0],
  "width_mm": 32.0,
  "height_mm": 20.0,
  "corner_radius_mm": 4.0,
  "angle_deg": 0.0,
  "patch_id": "PATCH_MAIN_0001",
  "axis_source": "patch_normal"
}
```

Role별 deterministic action:

```text
PASSAGE, STRUCTURAL, UNKNOWN:
  KEEP_REFINED

RELIEF, DRAIN:
  SUPPRESS when allow_small_feature_suppression = true and cutout_area / midsurface_area < 0.01
  otherwise KEEP_REFINED
```

### 10.5 BEND and FLANGE

```json
{
  "feature_id": "BEND_STRUCTURAL_0001",
  "type": "BEND",
  "role": "STRUCTURAL",
  "inner_radius_mm": 2.4,
  "angle_deg": 90.0,
  "thickness_mm": 1.2,
  "adjacent_patch_ids": ["PATCH_MAIN_0001", "PATCH_FLANGE_0001"]
}
```

```json
{
  "feature_id": "FLANGE_STRUCTURAL_0001",
  "type": "FLANGE",
  "role": "STRUCTURAL",
  "width_mm": 24.0,
  "free_edge_id": "EDGE_FLANGE_FREE_0001",
  "bend_id": "BEND_STRUCTURAL_0001"
}
```

Action:

```text
BEND   -> KEEP_WITH_BEND_ROWS
FLANGE -> KEEP_WITH_FLANGE_SIZE
```

---

## 11. Feature Placement Constraints

모든 feature layout은 생성 단계에서 다음 조건을 만족해야 한다.

### 11.1 Boundary clearance

각 feature의 bounding radius를 \(\rho_i\), patch boundary까지 최단거리를 \(d_{boundary,i}\)라 한다.

\[
d_{boundary,i}\ge \rho_i+c_{boundary}
\]

```text
c_boundary = max(0.75 h0, 2t)
```

### 11.2 Feature-feature clearance

두 feature \(i,j\) 사이 center distance를 \(d_{ij}\)라 한다.

\[
d_{ij}\ge \rho_i+\rho_j+c_{ff}
\]

```text
c_ff = max(0.75 h0, 2t)
```

### 11.3 Bend clearance

Feature는 bend neutral line 근처에 배치하지 않는다.

\[
d_{bend,i}\ge \rho_i+c_{bend}
\]

```text
c_bend = max(1.0 h0, 3t)
```

### 11.4 Minimum patch size

각 planar patch는 shell mesh를 생성할 수 있을 만큼 충분히 커야 한다.

\[
\min(W_{patch},H_{patch})\ge 4h_0
\]

조건을 만족하지 않는 parameter draw는 resampling한다.

---

## 12. CAD 생성 절차

CDF는 다음 순서로 CAD를 생성한다.

```text
1. part_class sampling
2. base midsurface sketch 생성
3. thickness t sampling
4. bend/flange topology 생성
5. feature layout sampling
6. clearance validation
7. solid sheet body 생성
8. feature cut operation 수행
9. optional corner fillet 적용
10. reference midsurface body 생성
11. STEP export
12. STEP re-import validation
```

CadQuery/OCP 기준 내부 함수는 다음 이름으로 고정한다.

```python
def build_sheet_part(params: SheetPartParams) -> GeneratedCad:
    """Return solid_shape, reference_midsurface_shape, feature_truth."""

def export_step(shape, path: Path, part_name: str) -> None:
    """Export STEP with canonical part name metadata when backend supports it."""

def validate_constant_thickness(
    shape,
    expected_t: float,
    tol_abs: float,
    tol_rel: float
) -> ThicknessReport:
    """Measure opposite-face distances and validate constant thickness."""
```

---

## 13. B-rep Graph 자동 추출

B-rep extractor는 `cad/input.step`을 읽고 다음 node와 edge를 생성한다.

### 13.1 Node types

```text
PART
FACE
EDGE
COEDGE
VERTEX
FEATURE_CANDIDATE
```

### 13.2 Edge types

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

### 13.3 Face feature columns

```text
surface_type_id
area_over_Lref2
perimeter_over_Lref
bbox_dx_over_Lref
bbox_dy_over_Lref
bbox_dz_over_Lref
num_outer_loops
num_inner_loops
num_edges
normal_x
normal_y
normal_z
k1_min_times_Lref
k1_max_times_Lref
k2_min_times_Lref
k2_max_times_Lref
mean_curvature_times_Lref
gaussian_curvature_times_Lref2
estimated_thickness_over_Lref
is_top_sheet_face
is_bottom_sheet_face
is_bend_face
is_flange_face
```

### 13.4 Edge feature columns

```text
curve_type_id
length_over_Lref
radius_over_Lref
center_x_over_Lref
center_y_over_Lref
center_z_over_Lref
axis_x
axis_y
axis_z
dihedral_angle_rad
is_inner_loop_edge
is_outer_boundary_edge
is_circular
is_slot_arc
is_bend_edge
is_sharp
```

### 13.5 Feature candidate columns

```text
feature_type_id
role_id
size_1_over_Lref
size_2_over_Lref
radius_over_Lref
width_over_Lref
length_over_Lref
center_x_over_Lref
center_y_over_Lref
center_z_over_Lref
distance_to_outer_boundary_over_Lref
distance_to_nearest_feature_over_Lref
clearance_ratio
expected_action_mask
```

`expected_action_mask`는 config와 role로부터 계산되는 허용 action mask이다. 정답 action은 `labels/feature_labels.json`과 `labels/amg_manifest.json`에만 저장한다.

`graph/brep_graph.npz`는 sparse adjacency와 dense feature matrices를 포함한다. `graph/graph_schema.json`은 column order를 명시한다.

---

## 14. Entity Signature와 Truth Matching

STEP import 후 face/edge ID는 바뀔 수 있으므로 CDF는 stable signature를 사용한다.

### 14.1 HOLE signature

```json
{
  "feature_id": "HOLE_BOLT_0001",
  "type": "HOLE",
  "role": "BOLT",
  "signature": {
    "geom_type": "circular_inner_loop",
    "part_name": "SMT_SM_FLAT_PANEL_T120_P000001",
    "center_mm": [80.0, 50.0, 0.0],
    "axis": [0.0, 0.0, 1.0],
    "radius_mm": 4.0,
    "patch_id": "PATCH_MAIN_0001",
    "adjacent_surface_types": ["plane", "cylinder"],
    "loop_type": "inner_loop"
  }
}
```

### 14.2 Matching score

후보 feature \(q\)와 truth feature \(t\)의 normalized error score는 다음으로 계산한다. 낮을수록 좋은 match이다.

\[
S(t,q)=w_c e_c+w_r e_r+w_a e_a+w_{type}e_{type}
\]

각 항은 다음이다.

\[
e_c=\frac{\|c_t-c_q\|_2}{\tau_c}
\]

\[
e_r=\frac{|r_t-r_q|}{\tau_r}
\]

\[
e_a=\frac{\arccos(|a_t\cdot a_q|)}{\tau_a}
\]

```text
e_type = 0 if feature types match, else 10
τc = position_tolerance_mm
τr = radius_tolerance_mm
τa = angle_tolerance_rad
weights: wc = 1, wr = 1, wa = 1, wtype = 1
```

Matching acceptance:

```text
S <= 3.0 and e_type = 0 -> matched
otherwise                -> unmatched
```

Accepted sample 조건:

```text
HOLE truth recall = 100%
SLOT truth recall = 100%
CUTOUT truth recall = 100%
BEND truth recall = 100%
FLANGE truth recall = 100%
false match count = 0
```

---

## 15. Mesh-Control Label 규칙

CDF label은 deterministic rule로 생성된다. ANSA oracle은 label을 수정하지 않는다.

### 15.1 Reference length

Planar midsurface 총 면적을 \(A_{mid}\)라고 한다.

\[
L_{ref}=\sqrt{A_{mid}}
\]

Base target length:

\[
h_0=\operatorname{clip}(0.035L_{ref},3.0,6.0)
\]

Minimum and maximum length:

\[
h_{min}=0.30h_0
\]

\[
h_{max}=1.80h_0
\]

Growth-rate limit:

\[
g_{max}=1.35
\]

### 15.2 Curvature rule

곡률 반경을 \(R\)이라고 한다.

\[
\delta_{max}=\min(0.05t,0.02h_0)
\]

\[
h_{curv}=\operatorname{clip}
\left(
\sqrt{8R\delta_{max}},
h_{min},
h_0
\right)
\]

판금 `BEND`에서는 \(R\)을 bend neutral radius로 사용한다.

### 15.3 HOLE rule

Hole radius를 \(r\), diameter를 \(d=2r\)라고 한다.

#### 15.3.1 Action

```text
if role in {BOLT, MOUNT}:
    action = KEEP_WITH_WASHER

elif role in {RELIEF, DRAIN}
     and allow_small_feature_suppression = true
     and d <= min(0.60*h0, 2.0*t):
    action = SUPPRESS

else:
    action = KEEP_REFINED
```

#### 15.3.2 Circumferential divisions

```text
if role in {BOLT, MOUNT}: n_min = 24
else:                     n_min = 12
```

\[
n_\theta=
\operatorname{make\_even}
\left(
\max
\left(
n_{min},
\left\lceil\frac{2\pi r}{h_0}\right\rceil
\right)
\right)
\]

\[
h_{hole}=\frac{2\pi r}{n_\theta}
\]

#### 15.3.3 Washer control

```text
washer_rings = 2
R_w_raw = max(2.0*r, r + washer_rings*h_hole)
R_w_limit = 0.45 * min(clearance_to_boundary, clearance_to_nearest_feature)
R_w = min(R_w_raw, R_w_limit)
```

Projection:

```text
if action == KEEP_WITH_WASHER and R_w < r + 1.5*h_hole:
    action = KEEP_REFINED
    washer_rings = 0
```

### 15.4 SLOT rule

Slot width를 \(w_s\), length를 \(L_s\), end radius를 \(r_e=w_s/2\)라고 한다.

Action:

```text
if role in {MOUNT, PASSAGE, STRUCTURAL}:
    action = KEEP_REFINED

elif role in {RELIEF, DRAIN}
     and allow_small_feature_suppression = true
     and w_s <= min(0.60*h0, 2.0*t):
    action = SUPPRESS

else:
    action = KEEP_REFINED
```

Target size:

```text
h_slot = min(h0, w_s / 3)
n_end = make_even(max(12, ceil(pi*r_e / h_slot)))
straight_edge_divisions = max(2, ceil((L_s - w_s) / h_slot))
```

### 15.5 CUTOUT rule

Cutout width를 \(w_c\), height를 \(h_c\)라고 한다.

```text
h_cutout = min(h0, min(w_c, h_c) / 4)
perimeter_growth_rate = 1.25
```

Action:

```text
if cutout_area / midsurface_area >= 0.01:
    action = KEEP_REFINED

elif role in {RELIEF, DRAIN}
     and allow_small_feature_suppression = true:
    action = SUPPRESS

else:
    action = KEEP_REFINED
```

### 15.6 BEND rule

Bend inner radius를 \(R_i\), thickness를 \(t\), neutral radius를 \(R_n=R_i+t/2\)라고 한다.

\[
s_b=\phi R_n
\]

\[
h_{bend}=
\operatorname{clip}
\left(
\sqrt{8R_n\delta_{max}},
h_{min},
h_0
\right)
\]

\[
n_{bend}=
\operatorname{clamp}
\left(
\left\lceil\frac{s_b}{h_{bend}}\right\rceil,
2,
6
\right)
\]

```text
action = KEEP_WITH_BEND_ROWS
growth_rate = 1.25
```

### 15.7 FLANGE rule

Flange width를 \(w_f\)라고 한다.

\[
n_f=\max\left(2,\left\lceil\frac{w_f}{h_0}\right\rceil\right)
\]

\[
h_{flange}=\operatorname{clip}\left(\frac{w_f}{n_f},h_{min},h_0\right)
\]

```text
action = KEEP_WITH_FLANGE_SIZE
```

### 15.8 Growth-rate smoothing

Feature별 target size가 인접 영역에서 급격히 변하지 않도록 graph smoothing을 수행한다. 각 face 또는 feature region의 raw size를 \(\hat{h}_i\)라고 한다.

\[
\min_{\tilde{h}_i}
\sum_i
(\log\tilde{h}_i-\log\hat{h}_i)^2
\]

subject to:

\[
h_{min}\le\tilde{h}_i\le h_{max}
\]

\[
|\log\tilde{h}_i-\log\tilde{h}_j|
\le \log g_{max}
\quad \forall(i,j)\in E_{adj}
\]

CDF implementation은 iterative projection으로 구현한다.

```python
def smooth_log_sizes(raw_h, adjacency, h_min, h_max, g_max, num_iter=20):
    h = np.clip(raw_h.copy(), h_min, h_max)
    log_g = np.log(g_max)

    for _ in range(num_iter):
        for i, j in adjacency:
            li, lj = np.log(h[i]), np.log(h[j])
            if li - lj > log_g:
                h[i] = np.exp(lj + log_g)
            elif lj - li > log_g:
                h[j] = np.exp(li + log_g)

        h = np.clip(h, h_min, h_max)

    return h
```

---

## 16. AMG-Compatible Manifest

CDF의 핵심 label은 AMG-compatible manifest이다.

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "VALID",
  "cad_file": "cad/input.step",
  "unit": "mm",
  "part": {
    "part_name": "SMT_SM_FLAT_PANEL_T120_P000001",
    "part_class": "SM_FLAT_PANEL",
    "idealization": "midsurface_shell",
    "thickness_mm": 1.2,
    "element_type": "quad_dominant_shell",
    "batch_session": "AMG_SHELL_CONST_THICKNESS_V1"
  },
  "global_mesh": {
    "h0_mm": 4.216,
    "h_min_mm": 1.265,
    "h_max_mm": 7.589,
    "growth_rate_max": 1.35,
    "quality_profile": "AMG_QA_SHELL_V1"
  },
  "features": [
    {
      "feature_id": "HOLE_BOLT_0001",
      "type": "HOLE",
      "role": "BOLT",
      "action": "KEEP_WITH_WASHER",
      "geometry_signature": {
        "center_mm": [80.0, 50.0, 0.0],
        "axis": [0.0, 0.0, 1.0],
        "radius_mm": 4.0
      },
      "controls": {
        "edge_target_length_mm": 1.047,
        "circumferential_divisions": 24,
        "washer_rings": 2,
        "washer_outer_radius_mm": 9.0,
        "radial_growth_rate": 1.25
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

CDF는 이 manifest를 ANSA oracle에 전달하여 실행 가능성을 검증한다. 이 과정은 AMG inference가 아니라 CDF deterministic label validation이다.

---

## 17. Auxiliary Training Labels

CDF는 supervised learning을 쉽게 하기 위해 중복 label도 저장한다.

### 17.1 `face_labels.json`

```json
{
  "schema": "CDF_FACE_LABELS_SM_V1",
  "sample_id": "sample_000001",
  "labels": [
    {
      "face_signature_id": "FACE_SIG_000001",
      "face_category": "PLANAR_MAIN_FACE",
      "target_length_mm": 4.216,
      "min_length_mm": 1.265,
      "max_length_mm": 7.589,
      "mesh_priority": "NORMAL"
    }
  ]
}
```

### 17.2 `edge_labels.json`

```json
{
  "schema": "CDF_EDGE_LABELS_SM_V1",
  "sample_id": "sample_000001",
  "labels": [
    {
      "edge_signature_id": "EDGE_SIG_HOLE_BOLT_0001_TOP",
      "feature_id": "HOLE_BOLT_0001",
      "target_length_mm": 1.047,
      "number_of_divisions": 24,
      "preserve_edge": true,
      "boundary_capture": true
    }
  ]
}
```

### 17.3 `feature_labels.json`

```json
{
  "schema": "CDF_FEATURE_LABELS_SM_V1",
  "sample_id": "sample_000001",
  "labels": [
    {
      "feature_id": "HOLE_BOLT_0001",
      "type": "HOLE",
      "role": "BOLT",
      "action": "KEEP_WITH_WASHER",
      "target_edge_length_mm": 1.047,
      "circumferential_divisions": 24,
      "washer_rings": 2,
      "washer_outer_radius_mm": 9.0,
      "growth_rate": 1.25
    }
  ]
}
```

---

## 18. ANSA Oracle

CDF-SM-ANSA-V1은 ANSA Batch Mesh를 validation oracle로 사용한다. Oracle mesh는 학습 target connectivity가 아니다. 학습 target은 `labels/amg_manifest.json`이다.

### 18.1 Oracle input

```text
cad/input.step
cad/reference_midsurface.step
metadata/feature_truth.json
metadata/entity_signatures.json
labels/amg_manifest.json
configs/quality/AMG_QA_SHELL_V1.json
configs/ansa/AMG_SHELL_CONST_THICKNESS_V1.json
```

### 18.2 ANSA execution workflow

ANSA script `cdf/oracle/ansa_scripts/cdf_ansa_oracle.py`는 다음 순서로 실행한다.

```text
1. input.step import
2. canonical part name 확인
3. geometry cleanup 실행
4. solid sheet에서 midsurface 자동 추출
5. reference_midsurface.step과 midsurface distance error 측정
6. entity_signatures.json 기반 feature entity matching
7. Batch Mesh Session 배정
8. manifest feature action 적용
   - HOLE KEEP_REFINED
   - HOLE KEEP_WITH_WASHER
   - HOLE SUPPRESS
   - SLOT KEEP_REFINED
   - SLOT SUPPRESS
   - CUTOUT KEEP_REFINED
   - CUTOUT SUPPRESS
   - BEND KEEP_WITH_BEND_ROWS
   - FLANGE KEEP_WITH_FLANGE_SIZE
9. ANSA Batch Mesh 실행
10. ANSA quality criteria check 실행
11. feature boundary size error 측정
12. solver deck export
13. ANSA database 저장
14. reports/*.json 생성
```

### 18.3 CDF internal ANSA adapter interface

아래 함수명은 CDF 내부 adapter interface이다. 실제 ANSA Python API 함수명은 설치된 ANSA version의 scripting API에 binding한다.

```python
def ansa_import_step(step_path: str) -> AnsaModelRef: ...

def ansa_run_geometry_cleanup(
    model: AnsaModelRef,
    cleanup_profile: str
) -> CleanupReport: ...

def ansa_extract_midsurface(
    model: AnsaModelRef,
    thickness_mm: float
) -> MidsurfaceReport: ...

def ansa_match_entities(
    model: AnsaModelRef,
    signatures: dict,
    tolerances: dict
) -> EntityMatchReport: ...

def ansa_assign_batch_session(
    model: AnsaModelRef,
    session_name: str,
    entity_set: EntitySetRef
) -> None: ...

def ansa_apply_hole_control(
    feature_ref: EntitySetRef,
    control: HoleControl
) -> None: ...

def ansa_apply_slot_control(
    feature_ref: EntitySetRef,
    control: SlotControl
) -> None: ...

def ansa_apply_cutout_control(
    feature_ref: EntitySetRef,
    control: CutoutControl
) -> None: ...

def ansa_apply_bend_control(
    feature_ref: EntitySetRef,
    control: BendControl
) -> None: ...

def ansa_apply_flange_control(
    feature_ref: EntitySetRef,
    control: FlangeControl
) -> None: ...

def ansa_run_batch_mesh(
    model: AnsaModelRef,
    session_name: str
) -> BatchMeshReport: ...

def ansa_run_quality_checks(
    model: AnsaModelRef,
    quality_profile: str
) -> QualityReport: ...

def ansa_export_solver_deck(
    model: AnsaModelRef,
    deck: str,
    out_path: str
) -> None: ...
```

### 18.4 Feature control mapping

| Manifest action | ANSA oracle operation |
|---|---|
| `KEEP_REFINED` on `HOLE` | preserve hole boundary, set circumferential divisions, set local growth rate |
| `KEEP_WITH_WASHER` on `HOLE` | preserve hole boundary, create radial washer zone, set ring count and growth rate |
| `SUPPRESS` on `HOLE` | fill circular hole after role/size rule assertion |
| `KEEP_REFINED` on `SLOT` | preserve slot boundary, set straight/arc divisions |
| `SUPPRESS` on `SLOT` | fill slot after role/size rule assertion |
| `KEEP_REFINED` on `CUTOUT` | preserve cutout boundary, set boundary target length |
| `SUPPRESS` on `CUTOUT` | fill cutout after role/area rule assertion |
| `KEEP_WITH_BEND_ROWS` | enforce bend rows and curvature-based target length |
| `KEEP_WITH_FLANGE_SIZE` | enforce minimum elements across flange width |

### 18.5 Oracle pass criteria

ANSA oracle pass criteria는 다음과 같다.

```text
ANSA STEP import success = true
ANSA midsurface extraction success = true
midsurface max distance error ≤ 0.10t
all feature signatures matched = true
Batch Mesh success = true
solver deck export success = true
num_hard_failed_elements = 0
min_angle_deg ≥ 20
max_angle_deg ≤ 160
max_aspect_ratio ≤ 6.0
max_warpage_deg ≤ 15
max_skewness ≤ 0.85
min_jacobian ≥ 0.60
feature_boundary_size_error_max ≤ 0.50
hole_division_error_max ≤ 1 segment
slot_boundary_division_error_max ≤ 2 segments
bend_row_error_max ≤ 1 row
```

Feature boundary size error:

\[
e_f=
\left|
\frac{\bar{h}_{boundary,f}-h_{target,f}}{h_{target,f}}
\right|
\]

Accepted sample은 위 조건을 모두 만족해야 한다. Oracle 실패 sample은 `rejected/`에 저장하고 label을 수정하지 않는다.

---

## 19. Main Generation Algorithm

Dataset generation은 requested accepted sample count를 목표로 실행한다.

```python
def generate_dataset(config, out_dir):
    rng = np.random.default_rng(config.seed)
    accepted = []
    rejected = []

    max_total_attempts = (
        config.num_accepted_samples
        * config.validation.max_generation_attempts_per_sample
    )

    attempt_seq = 0
    sample_seq = 1

    while len(accepted) < config.num_accepted_samples:
        if attempt_seq >= max_total_attempts:
            raise RuntimeError("MAX_TOTAL_ATTEMPTS_EXCEEDED")

        attempt_seq += 1
        result = generate_one_candidate(sample_seq, config, rng)

        if result.accepted:
            accepted.append(result.sample_id)
            sample_seq += 1
        else:
            rejected.append(result.rejection_record)

    write_dataset_index(out_dir, accepted, rejected, config)
    write_splits(out_dir, accepted, config)
```

Single-candidate generation:

```python
def generate_one_candidate(sample_seq, config, rng):
    params = sample_part_parameters(config, rng)
    h0 = compute_h0(params)

    layout = sample_feature_layout(params, h0, rng)
    if not layout_satisfies_clearance(layout, params, h0):
        return reject(sample_seq, "FEATURE_CLEARANCE", layout.report)

    cad_model, reference_midsurface_model, truth = build_cad_and_truth(
        params,
        layout
    )

    if not validate_cad_kernel_solid(cad_model):
        return reject(sample_seq, "CAD_KERNEL_SOLID", None)

    sample_dir = make_sample_dir(sample_seq)

    export_step(cad_model, sample_dir / "cad/input.step")
    export_step(reference_midsurface_model, sample_dir / "cad/reference_midsurface.step")

    geometry_report = validate_step_reimport_and_thickness(
        sample_dir / "cad/input.step",
        expected_t=params.thickness_mm,
        config=config
    )

    if not geometry_report.accepted:
        return reject(sample_seq, "GEOMETRY_VALIDATION", geometry_report)

    brep_graph = extract_brep_graph(sample_dir / "cad/input.step")

    detected = detect_features_from_brep(brep_graph)
    match_report = match_truth_to_detected(truth, detected)

    if not match_report.accepted:
        return reject(sample_seq, "FEATURE_TRUTH_MATCHING", match_report)

    manifest = build_amg_manifest(params, truth, brep_graph, config)
    validate_json_schema(manifest, "AMG_MANIFEST_SM_V1")

    labels = build_training_labels(manifest, brep_graph, truth)

    if config.ansa_oracle.enabled:
        oracle = run_ansa_oracle(sample_dir, manifest, config.ansa_oracle)
        if not oracle.accepted:
            return reject(sample_seq, "ANSA_ORACLE", oracle.report)
    else:
        oracle = make_disabled_oracle_report()

    write_sample_files(
        sample_dir=sample_dir,
        params=params,
        truth=truth,
        brep_graph=brep_graph,
        manifest=manifest,
        labels=labels,
        geometry_report=geometry_report,
        match_report=match_report,
        oracle_report=oracle.report
    )

    return Accepted(sample_id=f"sample_{sample_seq:06d}")
```

---

## 20. Validation Reports

### 20.1 `geometry_validation.json`

```json
{
  "schema": "CDF_GEOMETRY_VALIDATION_SM_V1",
  "checks": {
    "cad_export_success": true,
    "step_reimport_success": true,
    "closed_solid": true,
    "manifold": true,
    "volume_positive": true,
    "constant_thickness_pass": true,
    "feature_clearance_pass": true,
    "bend_radius_pass": true,
    "no_cut_on_bend_pass": true
  },
  "measured": {
    "volume_mm3": 19200.0,
    "mean_thickness_mm": 1.2,
    "max_thickness_error_mm": 0.018,
    "num_faces": 26,
    "num_edges": 64
  }
}
```

Thickness tolerance:

\[
\tau_t=\max(0.05,0.03t)\ \text{mm}
\]

### 20.2 `feature_matching_report.json`

```json
{
  "schema": "CDF_FEATURE_MATCHING_REPORT_SM_V1",
  "sample_id": "sample_000001",
  "accepted": true,
  "truth_feature_count": 4,
  "detected_feature_count": 4,
  "unmatched_truth_features": [],
  "unmatched_detected_features": [],
  "matches": [
    {
      "feature_id": "HOLE_BOLT_0001",
      "detected_feature_id": "DETECTED_HOLE_000017",
      "score": 0.42,
      "center_error_mm": 0.01,
      "radius_error_mm": 0.004,
      "axis_error_deg": 0.0
    }
  ]
}
```

### 20.3 `ansa_execution_report.json`

```json
{
  "schema": "CDF_ANSA_EXECUTION_REPORT_SM_V1",
  "sample_id": "sample_000001",
  "accepted": true,
  "ansa_version": "<filled_by_ansa_script>",
  "step_import_success": true,
  "geometry_cleanup_success": true,
  "midsurface_extraction_success": true,
  "feature_matching_success": true,
  "batch_mesh_success": true,
  "solver_export_success": true,
  "runtime_sec": 41.2,
  "outputs": {
    "solver_deck": "meshes/ansa_oracle_mesh.bdf",
    "ansa_database": "meshes/ansa_oracle_model.ansa"
  }
}
```

### 20.4 `ansa_quality_report.json`

```json
{
  "schema": "CDF_ANSA_QUALITY_REPORT_SM_V1",
  "sample_id": "sample_000001",
  "accepted": true,
  "mesh_stats": {
    "num_nodes": 821,
    "num_shell_elements": 764,
    "quad_ratio": 0.92,
    "tria_ratio": 0.08
  },
  "quality": {
    "num_hard_failed_elements": 0,
    "min_angle_deg": 24.6,
    "max_angle_deg": 151.0,
    "max_aspect_ratio": 4.8,
    "max_warpage_deg": 8.4,
    "max_skewness": 0.63,
    "min_jacobian": 0.78
  },
  "feature_checks": [
    {
      "feature_id": "HOLE_BOLT_0001",
      "type": "HOLE",
      "target_divisions": 24,
      "measured_divisions": 24,
      "target_edge_length_mm": 1.047,
      "measured_boundary_length_mm": 1.09,
      "boundary_size_error": 0.038
    }
  ]
}
```

### 20.5 `sample_acceptance.json`

```json
{
  "schema": "CDF_SAMPLE_ACCEPTANCE_SM_ANSA_V1",
  "sample_id": "sample_000001",
  "accepted": true,
  "accepted_by": {
    "geometry_validation": true,
    "feature_matching": true,
    "manifest_schema": true,
    "ansa_oracle": true
  },
  "rejection_reason": null
}
```

---

## 21. Dataset Quality Targets

### 21.1 Geometry

```text
STEP export success rate ≥ 98% on 1,000 requested candidates
STEP re-import success rate ≥ 98%
closed solid validation pass rate ≥ 95%
constant thickness validation pass rate ≥ 95%
```

### 21.2 Feature detection

```text
HOLE truth/detected matching recall ≥ 98%
SLOT truth/detected matching recall ≥ 95%
CUTOUT truth/detected matching recall ≥ 95%
BEND truth/detected matching recall ≥ 95%
FLANGE truth/detected matching recall ≥ 95%
false matched feature rate ≤ 2%
```

### 21.3 Label

```text
100% accepted samples have valid AMG_MANIFEST_SM_V1
100% feature actions belong to allowed enum
100% h values satisfy h_min ≤ h ≤ h_max
100% adjacent feature sizes satisfy growth rate after smoothing
100% SUPPRESS labels satisfy role and size policy
```

### 21.4 ANSA oracle

```text
ANSA oracle pass rate ≥ 85% on generated valid CADs
ANSA STEP import success = 100% for accepted samples
ANSA midsurface extraction success = 100% for accepted samples
ANSA Batch Mesh success = 100% for accepted samples
invalid or hard-failed element count = 0 for accepted samples
feature boundary size error max ≤ 0.50 for accepted samples
solver deck export success = 100% for accepted samples
```

---

## 22. Repository Implementation Plan

```text
cad_dataset_factory/
  pyproject.toml
  configs/
    cdf_sm_ansa_v1.default.json
    cdf_sm_ansa_v1.small_feature_suppression.json
    quality/
      amg_qa_shell_v1.json
    ansa/
      amg_shell_const_thickness_v1.json
      ansa_oracle_runtime.json
  contracts/
    AMG_MANIFEST_SM_V1.schema.json
    AMG_BREP_GRAPH_SM_V1.schema.json
    CDF_FEATURE_TRUTH_SM_V1.schema.json
    CDF_ANSA_EXECUTION_REPORT_SM_V1.schema.json
    CDF_ANSA_QUALITY_REPORT_SM_V1.schema.json
  cdf/
    cli.py
    config/
      load_config.py
      schema_validate.py
    sampling/
      distributions.py
      sample_part.py
      poisson_disk.py
    cadgen/
      flat_panel.py
      single_flange.py
      l_bracket.py
      u_channel.py
      hat_channel.py
      cut_features.py
      export_step.py
    truth/
      feature_truth.py
      signatures.py
      canonical_names.py
    brep/
      read_step.py
      topology.py
      face_features.py
      edge_features.py
      coedge_features.py
      feature_detector.py
      graph_writer.py
    labels/
      sizing.py
      amg_rules.py
      manifest_writer.py
      label_writer.py
    oracle/
      ansa_runner.py
      ansa_report_parser.py
      ansa_scripts/
        cdf_ansa_oracle.py
        cdf_ansa_api_layer.py
      mesh_quality_schema.py
    dataset/
      sample_writer.py
      index_writer.py
      split_writer.py
      package_writer.py
      validate_dataset.py
    tests/
      test_dependency_boundary.py
      test_ansa_import_scope.py
      test_sampling_constraints.py
      test_geometry_generation.py
      test_feature_truth_matching.py
      test_amg_manifest_schema.py
      test_ansa_report_schema.py
```

Recommended Python dependencies:

```toml
[project]
requires-python = ">=3.11"
dependencies = [
  "cadquery>=2.5,<3",
  "numpy>=1.26,<3",
  "scipy>=1.11,<2",
  "networkx>=3.2,<4",
  "pydantic>=2.7,<3",
  "jsonschema>=4.22,<5",
  "meshio>=5.3,<6",
  "tqdm>=4.66,<5"
]
```

ANSA 실행 파일은 환경변수로 지정한다.

```bash
export ANSA_EXECUTABLE=/path/to/ansa64.sh
```

---

## 23. Required CLI

```bash
cdf generate \
  --config configs/cdf_sm_ansa_v1.default.json \
  --out datasets/sm_ansa_v1 \
  --count 10000 \
  --seed 20260502
```

```bash
cdf validate --dataset datasets/sm_ansa_v1
```

```bash
cdf run-ansa-oracle \
  --sample datasets/sm_ansa_v1/samples/sample_000001 \
  --config configs/cdf_sm_ansa_v1.default.json
```

```bash
cdf package \
  --dataset datasets/sm_ansa_v1 \
  --out artifacts/cdf_sm_ansa_v1.tar.gz
```

Exit codes:

```text
0 success
1 configuration/schema error
2 CAD generation failure
3 STEP export/import failure
4 B-rep extraction failure
5 feature truth matching failure
6 label/schema failure
7 ANSA oracle failure
8 dataset packaging failure
```

---

## 24. Test Plan

Unit tests:

```text
test_make_even
test_clamp
test_h0_formula
test_curvature_formula
test_hole_label_rule
test_slot_label_rule
test_cutout_label_rule
test_bend_label_rule
test_flange_label_rule
test_feature_clearance_inequality
test_canonical_part_name
test_feature_id_sequence
test_json_schema_validation
```

CAD tests:

```text
test_flat_panel_export_step
test_single_flange_constant_thickness
test_l_bracket_bend_radius
test_u_channel_two_bends
test_hat_channel_four_bends
test_no_feature_intersects_boundary
test_no_feature_intersects_bend
```

Graph tests:

```text
test_graph_has_required_node_types
test_coedge_next_prev_cycles
test_coedge_mate_pairs
test_face_edge_adjacency_consistency
test_feature_contains_entities
test_graph_schema_column_count
test_graph_has_no_target_action_column
```

ANSA oracle tests:

```text
test_ansa_command_line_build
  목적: ANSA batch command가 config에서 정확히 구성되는지 확인한다.
  ANSA license 불필요.

test_ansa_report_parser
  목적: schema-valid failed ANSA JSON report를 정확히 parsing하는지 확인한다.
  ANSA license 불필요.

test_ansa_oracle_smoke_requires_ansa
  목적: 실제 ANSA 환경에서 1개 sample을 import, midsurface, mesh, quality check까지 수행한다.
  pytest marker: requires_ansa
```

Independence tests:

```text
test_no_amg_import
test_ansa_import_scope
test_cdf_runs_without_amg_installed
test_manifest_validates_against_copied_contract
```

---

## 25. Development Milestones

### Milestone 1: Schema and rule engine

Deliverables:

```text
contracts/*.schema.json
configs/cdf_sm_ansa_v1.default.json
cdf/labels/sizing.py
cdf/labels/amg_rules.py
unit tests for all formulas
```

Exit criteria:

```text
manifest JSON validates against AMG_MANIFEST_SM_V1
all label formula tests pass
```

### Milestone 2: Flat panel dataset

Deliverables:

```text
SM_FLAT_PANEL generator
HOLE, SLOT, CUTOUT generator
feature_truth.json writer
input.step and reference_midsurface.step export
```

Exit criteria:

```text
1,000 SM_FLAT_PANEL accepted samples generated
STEP export/re-import success ≥ 98%
HOLE truth matching recall ≥ 98%
```

### Milestone 3: B-rep graph

Deliverables:

```text
face/edge/coedge/feature graph extractor
graph/brep_graph.npz writer
graph_schema.json writer
```

Exit criteria:

```text
all accepted flat samples have graph files
coedge cycle and mate tests pass
feature input matrix has no target action column
```

### Milestone 4: ANSA oracle

Deliverables:

```text
cdf/oracle/ansa_runner.py
cdf/oracle/ansa_scripts/cdf_ansa_oracle.py
ANSA import of cad/input.step
ANSA midsurface extraction
manifest-based feature matching
manifest-based local control application
ANSA Batch Mesh execution
ansa_quality_report.json writer
ansa_oracle_mesh.bdf writer
```

Exit criteria:

```text
ANSA oracle pass ≥ 85% on valid flat panel samples
all ANSA reports validate schema
accepted samples have zero hard failed elements
```

### Milestone 5: Bent sheet families

Deliverables:

```text
SM_SINGLE_FLANGE generator
SM_L_BRACKET generator
SM_U_CHANNEL generator
SM_HAT_CHANNEL generator
BEND and FLANGE truth/label generation
ANSA bend/flange control validation
```

Exit criteria:

```text
BEND truth matching recall ≥ 95%
FLANGE truth matching recall ≥ 95%
ANSA oracle pass ≥ 80% on bent sheet samples
```

### Milestone 6: Dataset scale-up

Deliverables:

```text
10,000 accepted samples
train/validation/test split
holdout class split
dataset_stats.json
rejected_index.json
```

Exit criteria:

```text
cdf generate produces 10,000 accepted samples with fixed seed
cdf validate passes all accepted samples
AMG can load graph and manifest files without CDF runtime dependency
```

---

## 26. Minimal Accepted Sample Example

```json
{
  "generator_params": {
    "schema": "CDF_GENERATOR_PARAMS_SM_V1",
    "sample_id": "sample_000001",
    "part_class": "SM_FLAT_PANEL",
    "canonical_part_name": "SMT_SM_FLAT_PANEL_T120_P000001",
    "W_mm": 160.0,
    "H_mm": 100.0,
    "thickness_mm": 1.2,
    "corner_radius_mm": 0.0,
    "features": [
      {
        "feature_id": "HOLE_BOLT_0001",
        "type": "HOLE",
        "role": "BOLT",
        "center_uv_mm": [80.0, 50.0],
        "radius_mm": 4.0
      }
    ]
  },
  "computed_mesh_rule": {
    "A_mid_mm2": 16000.0,
    "L_ref_mm": 126.491,
    "h0_mm": 4.216,
    "h_min_mm": 1.265,
    "h_max_mm": 7.589,
    "hole_action": "KEEP_WITH_WASHER",
    "hole_circumferential_divisions": 24,
    "hole_target_edge_length_mm": 1.047,
    "washer_rings": 2,
    "washer_outer_radius_mm": 9.0
  },
  "ansa_acceptance": {
    "step_import_success": true,
    "midsurface_extraction_success": true,
    "batch_mesh_success": true,
    "num_hard_failed_elements": 0,
    "feature_boundary_size_error_max": 0.038
  }
}
```

---

## 27. References

1. CadQuery documentation, importing and exporting files: https://cadquery.readthedocs.io/en/latest/importexport.html  
2. Open CASCADE BRep format documentation: https://dev.opencascade.org/doc/occt-6.7.0/overview/html/occt_brep_format.html  
3. Open CASCADE technical overview, local properties of B-rep shapes: https://dev.opencascade.org/doc/occt-6.8.0/overview/html/technical_overview.html  
4. BRepNet: A topological message passing system for solid models: https://arxiv.org/abs/2104.00706  
5. UV-Net: Learning from Boundary Representations: https://arxiv.org/abs/2006.10211  
6. BETA CAE Systems, ANSA automatic meshing brochure: https://www.beta-cae.com/brochure/ansa_for_automatic_meshing.pdf  
7. BETA CAE Systems, ANSA scripting basic course: https://www.beta-cae.com/courses/ansa_scripting_basic.pdf  

---

## 28. Final Implementation Criterion

CDF-SM-ANSA-V1 is complete when the following commands work without AMG installed.

```bash
pip install -e .
export ANSA_EXECUTABLE=/path/to/ansa64.sh
cdf generate --config configs/cdf_sm_ansa_v1.default.json --out datasets/demo --count 1000 --seed 1
cdf validate --dataset datasets/demo
```

Every accepted sample must contain:

```text
cad/input.step
cad/reference_midsurface.step
metadata/feature_truth.json
metadata/entity_signatures.json
graph/brep_graph.npz
graph/graph_schema.json
labels/amg_manifest.json
labels/face_labels.json
labels/edge_labels.json
labels/feature_labels.json
meshes/ansa_oracle_mesh.bdf
reports/ansa_execution_report.json
reports/ansa_quality_report.json
reports/sample_acceptance.json
```

AMG may consume these files as external training data. CDF remains a separate dataset factory defined by file contracts, schema validation, deterministic geometry generation, deterministic AMG-compatible label rules, and ANSA oracle validation.
