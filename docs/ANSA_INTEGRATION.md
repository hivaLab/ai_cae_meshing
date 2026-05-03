# ANSA_INTEGRATION.md

## 1. Purpose

ANSA is the execution and oracle backend for AMG/CDF SM-ANSA-V1. Code should isolate ANSA-specific API calls behind adapter scripts so that most tests can run without ANSA installed.

## 2. Boundary model

```text
General Python process:
  builds command
  writes input files
  invokes ANSA batch process
  waits with timeout
  reads JSON reports

ANSA internal script:
  imports ANSA Python API
  imports only local adapter layer inside ansa_scripts
  executes ANSA operations
  writes JSON reports
```

## 3. CDF oracle execution

Inputs:

```text
cad/input.step
cad/reference_midsurface.step
metadata/feature_truth.json
metadata/entity_signatures.json
labels/amg_manifest.json
configs/quality/AMG_QA_SHELL_V1.json
configs/ansa/AMG_SHELL_CONST_THICKNESS_V1.json
```

Workflow:

```text
1. import STEP
2. run geometry cleanup
3. extract midsurface
4. compare extracted midsurface to reference midsurface
5. match feature signatures
6. assign Batch Mesh Session
7. apply manifest feature actions and controls
8. run Batch Mesh
9. run quality checks
10. measure feature boundary errors
11. export solver deck
12. save ANSA database if configured
13. write JSON reports
```

## 4. AMG execution

AMG uses its own adapter interface. The interface mirrors manifest actions and does not expose raw ANSA API names in core code.

Required methods:

```text
import_step
run_geometry_cleanup
build_entity_index
match_entities
create_sets
extract_midsurface
assign_thickness
assign_batch_session
apply_edge_length
apply_hole_washer
fill_hole
apply_bend_rows
apply_flange_size
run_batch_mesh
export_quality_report
export_solver_deck
```

## 5. Mocking strategy

Before real ANSA binding exists, implement mock adapter/report fixtures.

Mock cases:

```text
success_all_checks
step_import_failed
midsurface_failed
entity_matching_failed
batch_mesh_failed
quality_failed_hole
quality_failed_bend
quality_failed_growth
solver_export_failed
```

The mock must not mark a sample accepted unless the manifest validates and mocked quality criteria pass.

## 6. ANSA pass criteria normalization

Reports should normalize to these fields:

```text
step_import_success
geometry_cleanup_success
midsurface_extraction_success
feature_matching_success
batch_mesh_success
solver_export_success
num_hard_failed_elements
min_angle_deg
max_angle_deg
max_aspect_ratio
max_warpage_deg
max_skewness
min_jacobian
feature_boundary_size_error_max
hole_division_error_max
slot_boundary_division_error_max
bend_row_error_max
```

## 7. AMG retry policy

Retry is deterministic and limited to two attempts.

```text
hole perimeter quality fail:
  h_hole <- max(h_min, 0.75*h_hole)
  n_theta <- make_even(ceil(2*pi*r/h_hole))

bend warpage/skew fail:
  bend_rows <- min(max_bend_rows, bend_rows + 1)

flange narrow-face fail:
  h_flange <- max(h_min, 0.80*h_flange)

global growth fail:
  growth_rate_max <- min(1.20, current_growth_rate_max)
```

After retry exhaustion, AMG writes:

```json
{
  "schema_version": "AMG_MANIFEST_SM_V1",
  "status": "MESH_FAILED",
  "reason": "quality_not_satisfied_after_retry"
}
```

## 8. Failure reasons

Use structured reasons:

```text
ANSA_STEP_IMPORT_FAILED
ANSA_GEOMETRY_CLEANUP_FAILED
ANSA_MIDSURFACE_FAILED
ANSA_ENTITY_MATCHING_FAILED
ANSA_BATCH_MESH_FAILED
ANSA_QUALITY_FAILED
ANSA_SOLVER_EXPORT_FAILED
ANSA_TIMEOUT
ANSA_REPORT_MISSING
ANSA_REPORT_SCHEMA_INVALID
```

## 9. Implementation notes

```text
- ANSA executable path comes from config or ANSA_EXECUTABLE.
- Timeouts are mandatory.
- Subprocess stdout/stderr are captured to logs.
- ANSA internal script always writes a report, even on controlled failure.
- Real ANSA smoke tests use pytest marker requires_ansa.
```
