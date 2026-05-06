# ANSA Integration

## Goal

Use ANSA as the real meshing backend and quality oracle for clean sheet-metal CAD.

The primary controls passed to ANSA should be:

```text
global shell mesh policy
user global growth rate
per-edge target size
optional per-face target size
quality profile
```

## Why Edge Size First

For surface shell meshing, edge sizes are the simplest high-impact control:

- circular holes need enough perimeter segments to capture curvature
- slot ends need small edge size around arcs
- cutout boundaries need controlled boundary length
- close features require smaller local sizes
- bends need enough elements through curvature and along boundaries
- narrow flanges need enough elements across width

Most of these requirements can be represented by per-edge size and a global growth-rate
constraint. Face size is useful as a secondary control when ANSA supports it reliably.

## Runtime Sequence

```text
1. import STEP
2. validate clean sheet-metal scope
3. build entity index and signatures
4. match predicted edge/face signatures to ANSA entities
5. apply global mesh policy
6. apply per-edge sizes
7. apply optional per-face sizes
8. set user global growth rate
9. run Batch Mesh
10. export BDF
11. export execution report
12. export quality report
```

## Current Integration Blocker

The v2 size-field runner and ANSA script now exist, but the first real smoke run is
blocked at entity matching.

Observed on ANSA v25.1.0:

```text
CDF edge descriptors: 17
ANSA edge entities: 17
ANSA reported edge length: -1.0 for every attempted edge descriptor
ANSA reported edge center/bbox: unavailable through the attempted path
```

This means edge/face target sizes must not yet be counted as applied successfully.
The next integration step is a focused ANSA entity descriptor probe for CONS,
FE PERIMETER, CURVE, FACE, and MACRO entities after STEP import and Skin.

## API Boundary

ANSA Python API imports must remain inside ANSA scripts:

```text
cad_dataset_factory/cdf/oracle/ansa_scripts/
ai_mesh_generator/amg/ansa_scripts/
```

Normal Python modules may launch ANSA as a subprocess and parse report files.

## Required Adapter Operations

The next adapter should support:

```python
def import_step(path): ...
def build_entity_index(): ...
def apply_global_shell_policy(policy): ...
def apply_edge_size(edge_ref, size_mm): ...
def apply_face_size(face_ref, size_mm): ...
def set_growth_rate(growth_rate): ...
def run_batch_mesh(): ...
def export_bdf(path): ...
def export_execution_report(path): ...
def export_quality_report(path): ...
```

Operations such as hole fill, small-feature suppression, washer generation, or baseline
selection are not primary success paths. They may be revisited only after the size-field
pipeline works.

## Quality Report Requirements

Global metrics:

```text
num_nodes
num_shell_elements
quad_ratio
tria_ratio
num_hard_failed_elements
min_angle_deg
max_angle_deg
max_aspect_ratio
max_warpage_deg
max_skewness
min_jacobian
runtime_sec
```

Local feature metrics:

```text
feature_id
feature_type
target_edge_length_mm
measured_edge_length_mean_mm
measured_edge_length_max_mm
boundary_size_error
measured_circumferential_divisions
measured_bend_rows
measured_elements_across_width
metric_available
```

Missing local metrics are not success. They are `METRIC_UNAVAILABLE` until a real
measurement path exists.

## Real Mesh Acceptance

`VALID_MESH` means:

- no mock or placeholder outputs
- no controlled failure
- non-empty BDF
- execution report accepted
- quality report accepted
- hard failed element count is zero
- local quality metrics are measured and within threshold
