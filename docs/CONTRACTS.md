# Contracts

## Contract Policy

Versioned files are the boundary between CDF, AMG, ANSA scripts, and tests.

Contracts must prevent target leakage. Graph input files must not include:

- target part class
- target face or edge segmentation labels
- target edge or face sizes
- target quality scores
- reference mesh decision flags

Targets belong under `labels/` or `reports/`, never inside model input arrays.

## Canonical Part Classes

```text
SM_FLAT_PANEL
SM_SINGLE_FLANGE
SM_L_BRACKET
SM_U_CHANNEL
SM_HAT_CHANNEL
OTHER
```

`OTHER` is used for out-of-scope or uncertain clean CAD.

## Face Segmentation Classes

```text
BASE_PANEL
FLANGE
HOLE_WALL
SLOT_WALL
CUTOUT_WALL
SIDE_WALL
OTHER
```

`BEND` is not part of the active face-label contract because the current clean CAD
generator does not yet provide true cylindrical bend-face support. Bend-related control
is represented by `BEND_EDGE` in the edge semantic labels.

## Edge Segmentation Classes

```text
OUTER_BOUNDARY
HOLE_BOUNDARY
SLOT_BOUNDARY
CUTOUT_BOUNDARY
BEND_EDGE
FREE_EDGE
INTERNAL
OTHER
```

## Mesh Size Field Contract

Schema name:

```text
AMG_SIZE_FIELD_SM_V2
```

Required top-level fields:

```text
schema_version
sample_id
cad_file
unit
global_mesh
edge_sizes
face_sizes
```

Required global mesh fields:

```text
h0_mm
h_min_mm
h_max_mm
growth_rate
quality_profile
```

Edge size record:

```text
edge_signature_id
target_size_mm
confidence optional
source optional
```

Face size record:

```text
face_signature_id
target_size_mm
confidence optional
source optional
```

## CDF Label Contracts

```text
CDF_PART_CLASS_LABEL_SM_V2
CDF_FACE_SEGMENTATION_SM_V2
CDF_EDGE_SEGMENTATION_SM_V2
CDF_MESH_SIZE_FIELD_SM_V2
CDF_ENTITY_QUALITY_EVALUATION_SM_V2
CDF_ANSA_EXECUTION_REPORT_SM_V1
CDF_ANSA_QUALITY_REPORT_SM_V1
```

## Entity Quality Evaluation Contract

Schema name:

```text
CDF_ENTITY_QUALITY_EVALUATION_SM_V2
```

Required fields:

```text
schema_version
sample_id
evaluation_id
size_field_path
entity_quality
global_quality_summary
```

Entity quality record:

```text
entity_signature_id
entity_type                 # EDGE or FACE
semantic_label optional
candidate_target_size_mm
candidate_neighbor_size_ratio_max
candidate_growth_rate
measured_quality_margin
measured_boundary_size_error optional
hard_fail
near_fail
metric_available
metric_unavailable_reason optional
```

These records are labels. They must not be copied into graph input arrays.

## ANSA Quality Contract

The quality report must separate:

```text
global_mesh_quality
local_feature_quality
metric_availability
artifacts
```

Hard acceptance for `VALID_MESH`:

- real ANSA execution report exists
- real quality report exists
- solver deck exists and is non-empty
- hard failed element count is zero
- required local metrics are available
- local boundary error is within configured threshold

## Active Contract Boundary

New code must publish graph inputs, entity labels, size fields, and real quality evidence.
Graph arrays remain label-free, and meshing success is judged only from real ANSA
artifacts and measured quality rows.
