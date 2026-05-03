# CONTRACTS.md

## 1. 목적

이 문서는 AMG와 CDF가 공유하는 implementation-level contract이다. `AMG.md`와 `CDF.md`의 의미를 바꾸지 않고, 코딩 에이전트가 사용할 enum, schema version, 파일 경로, label leakage 방지 기준을 한 곳에 고정한다.

## 2. Schema version strings

```text
AMG_MANIFEST_SM_V1
AMG_CONFIG_SM_V1
AMG_FEATURE_OVERRIDES_SM_V1
AMG_BREP_GRAPH_SM_V1
CDF_CONFIG_SM_ANSA_V1
CDF_FEATURE_TRUTH_SM_V1
CDF_ENTITY_SIGNATURES_SM_V1
CDF_GEOMETRY_VALIDATION_SM_V1
CDF_FEATURE_MATCHING_REPORT_SM_V1
CDF_ANSA_EXECUTION_REPORT_SM_V1
CDF_ANSA_QUALITY_REPORT_SM_V1
CDF_SAMPLE_ACCEPTANCE_SM_ANSA_V1
```

## 3. Canonical enums

### 3.1 Part class

```text
SM_FLAT_PANEL
SM_SINGLE_FLANGE
SM_L_BRACKET
SM_U_CHANNEL
SM_HAT_CHANNEL
```

### 3.2 Feature type

```text
HOLE
SLOT
CUTOUT
BEND
FLANGE
OUTER_BOUNDARY
```

### 3.3 Feature role

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

### 3.4 Manifest action

```text
KEEP_REFINED
KEEP_WITH_WASHER
SUPPRESS
KEEP_WITH_BEND_ROWS
KEEP_WITH_FLANGE_SIZE
```

### 3.5 Manifest status

```text
VALID
OUT_OF_SCOPE
MESH_FAILED
```

### 3.6 Rejection or failure reason examples

```text
not_single_connected_solid
non_constant_thickness
midsurface_pairing_failed
entity_matching_failed
ambiguous_entity_matching
quality_not_satisfied_after_retry
FEATURE_CLEARANCE
CAD_KERNEL_SOLID
GEOMETRY_VALIDATION
FEATURE_TRUTH_MATCHING
ANSA_ORACLE
MAX_TOTAL_ATTEMPTS_EXCEEDED
```

Reason enums may be extended only when the new reason is structured and added to schema/tests.

## 4. AMG manifest contract

Required top-level keys for `status=VALID`:

```text
schema_version
status
cad_file
unit
part
global_mesh
features
entity_matching
```

Required `part` keys:

```text
part_name
part_class
idealization
thickness_mm
element_type
batch_session
```

Allowed fixed values:

```text
idealization = midsurface_shell
element_type = quad_dominant_shell
batch_session = AMG_SHELL_CONST_THICKNESS_V1
unit = mm
```

Required `global_mesh` keys:

```text
h0_mm
h_min_mm
h_max_mm
growth_rate_max
quality_profile
```

Required feature keys:

```text
feature_id
type
role
action
geometry_signature
controls
```

Feature control requirements:

```text
HOLE + KEEP_REFINED:
  edge_target_length_mm
  circumferential_divisions
  radial_growth_rate

HOLE + KEEP_WITH_WASHER:
  edge_target_length_mm
  circumferential_divisions
  washer_rings
  washer_outer_radius_mm
  radial_growth_rate

HOLE + SUPPRESS:
  reason or suppression_rule

SLOT + KEEP_REFINED:
  edge_target_length_mm
  end_arc_divisions or slot_end_divisions
  straight_edge_divisions
  growth_rate

CUTOUT + KEEP_REFINED:
  edge_target_length_mm
  perimeter_growth_rate

BEND + KEEP_WITH_BEND_ROWS:
  bend_rows
  bend_target_length_mm
  growth_rate

FLANGE + KEEP_WITH_FLANGE_SIZE:
  flange_target_length_mm or free_edge_target_length_mm
  min_elements_across_width
```

`status=OUT_OF_SCOPE` manifest:

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "OUT_OF_SCOPE",
  "reason": "non_constant_thickness"
}
```

`status=MESH_FAILED` manifest:

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "MESH_FAILED",
  "reason": "quality_not_satisfied_after_retry"
}
```

## 5. CDF sample directory contract

```text
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

Accepted sample must contain all required files. Rejected samples may contain partial files plus a rejection record.

## 6. Graph input contract

Allowed node types:

```text
PART
FACE
EDGE
COEDGE
VERTEX
FEATURE_CANDIDATE
```

Allowed edge types:

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

Feature candidate input columns may include:

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

Feature candidate input columns must not include:

```text
target_action_id
target_edge_length_mm
circumferential_divisions
washer_rings
bend_rows
any field copied from labels/*.json
```

## 7. CDF profile contract

Allowed dataset profiles:

```text
SM_KEEP_ALL_CUT_FEATURES_V1
SM_RULED_SMALL_FEATURE_SUPPRESSION_V1
```

Profile behavior:

```text
SM_KEEP_ALL_CUT_FEATURES_V1:
  allow_small_feature_suppression = false
  HOLE/SLOT/CUTOUT boundaries are retained and refined.

SM_RULED_SMALL_FEATURE_SUPPRESSION_V1:
  allow_small_feature_suppression = true
  RELIEF or DRAIN small features may be suppressed by AMG-SM-V1 rules.
```

## 8. Quality profile contract

Canonical quality profile name:

```text
AMG_QA_SHELL_V1
```

Core thresholds:

```text
quad fraction >= 0.85
tria fraction <= 0.15
aspect ratio <= 5.0
skew angle <= 60 deg
warpage <= 15 deg
min angle >= 30 deg
max angle <= 150 deg
Jacobian >= 0.50
negative Jacobian = 0
duplicate elements = 0
unmeshed face = 0
```

ANSA oracle may use slightly different parser field names, but report normalization must produce comparable fields.
