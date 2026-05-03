# ANSA_INTEGRATION.md

## 1. Purpose

ANSA is the real execution and oracle backend for AMG/CDF SM-ANSA-V1. The code must keep ANSA Python API imports inside `cad_dataset_factory/cdf/oracle/ansa_scripts/`, but the pipeline completion criteria are based on real ANSA execution, not mocks or dry-run reports.

Verified local ANSA entry point:

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```

The verified batch/script launch pattern is:

```text
ansa64.bat -b -nogui --confirm-license-agreement
  -exec load_script:<script>
  -exec main
  -process_string:<base64-json-payload>
```

## 2. Boundary Model

General Python process:

```text
1. Generate or locate sample files.
2. Validate JSON contracts.
3. Build an ANSA batch command.
4. Invoke ANSA with a timeout.
5. Read ANSA JSON reports and real mesh artifacts.
6. Reject the sample unless every required real-oracle acceptance condition is true.
```

ANSA internal script:

```text
1. Lazily imports ANSA Python API modules.
2. Imports only local adapter code inside ansa_scripts.
3. Executes real ANSA operations.
4. Writes schema-valid execution and quality reports.
5. Writes accepted=false reports on controlled failure.
```

No code outside `ansa_scripts/` may contain `import ansa` or `from ansa`.

## 3. Runtime Probe

Before treating the machine as ANSA-capable, run:

```powershell
python -m cad_dataset_factory.cdf.cli ansa-probe `
  --ansa-executable "C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat" `
  --out runs\ansa_probe\ansa_runtime_probe.json `
  --timeout-sec 90
```

The probe must verify:

```text
ANSA process starts in batch/no-gui mode
license is available
import ansa succeeds inside ANSA Python
base, batchmesh, constants, mesh, session, utils modules are importable
base.Open is available
base.Skin is available
base.OutputNastran is available
batchmesh.GetNewSession is available
batchmesh.AddPartToSession is available
batchmesh.RunSession is available
batchmesh.WriteStatistics is available
```

Probe success proves only runtime availability. It does not prove dataset completion.

## 4. CDF Oracle Execution

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

Required workflow:

```text
1. import STEP
2. run geometry cleanup
3. extract midsurface
4. assign shell thickness
5. match feature signatures
6. create feature/control sets
7. assign Batch Mesh Session
8. apply manifest feature actions and controls
9. run Batch Mesh
10. run quality checks
11. measure feature boundary errors
12. export NASTRAN BDF solver deck
13. save ANSA database when configured
14. write execution and quality JSON reports
```

The oracle must not rewrite labels to make a sample pass. If ANSA cannot apply the manifest, mesh the part, export the solver deck, or produce a passing quality report, the sample is rejected.

## 5. Real Acceptance Gate

An accepted CDF sample must contain:

```text
cad/input.step
graph/brep_graph.npz
graph/graph_schema.json
labels/amg_manifest.json
reports/ansa_execution_report.json
reports/ansa_quality_report.json
meshes/ansa_oracle_mesh.bdf
reports/sample_acceptance.json
```

Every accepted sample must satisfy:

```text
sample_acceptance.accepted = true
sample_acceptance.accepted_by.ansa_oracle = true
execution_report.accepted = true
quality_report.accepted = true
execution_report.ansa_version is not unavailable
execution_report.ansa_version is not mock-ansa
execution_report.outputs has no controlled_failure_reason
quality.num_hard_failed_elements = 0
meshes/ansa_oracle_mesh.bdf exists
meshes/ansa_oracle_mesh.bdf is non-empty
meshes/ansa_oracle_mesh.bdf is not a placeholder/mock file
```

Any missing report, missing mesh, dry-run, mock, controlled-failure report, disabled oracle path, placeholder output, or quality failure is a rejection.

## 6. Test Doubles Policy

Test doubles are allowed only for isolated unit tests that verify command construction, parser behavior, retry logic, or negative validation paths. They are not an oracle, not a dataset source, and not completion evidence for P7.

Allowed:

```text
mock subprocess for timeout/error unit tests
mock adapter for AMG interface mapping unit tests
schema-valid failed reports for parser tests
placeholder files only in tests that assert validation rejects them
```

Forbidden as success evidence:

```text
mock adapter quality success
disabled ANSA oracle
controlled_failure_reason reports
synthetic target labels
placeholder mesh/deck files
pytest smoke tests without real ANSA execution
```

## 7. ANSA Pass Criteria Normalization

Reports normalize to these fields:

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

T-703 must treat missing required metrics as rejection, not as zero or pass.

## 8. AMG Execution

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

The AMG mock adapter remains a unit-test adapter only. A real AMG inference result is complete only after real ANSA execution writes a quality-passing mesh.

## 9. AMG Retry Policy

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

## 10. Failure Reasons

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
ANSA_MESH_MISSING
ANSA_MESH_PLACEHOLDER
```

## 11. Implementation Notes

```text
- ANSA executable path comes from config, CLI, or ANSA_EXECUTABLE.
- Timeouts are mandatory.
- Subprocess stdout/stderr are captured to logs.
- ANSA internal script always writes accepted=false reports on controlled failure.
- requires_ansa tests are real gates, not smoke substitutes for dataset completion.
- P7 tasks are DONE only with real ANSA artifacts and strict dataset validation.
```
