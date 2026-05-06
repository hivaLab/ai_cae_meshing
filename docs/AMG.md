# AMG: AI Mesh Generator

## Scope

AMG converts a clean constant-thickness sheet-metal STEP part into ANSA mesh controls and
then validates the resulting shell mesh.

The next-generation AMG target is entity-based:

```text
B-rep entities in, edge/face size field out
```

AMG does not solve defeaturing in the current phase. Clean CAD is assumed.

## Inputs

Required:

```text
cad/input.step
amg_config.json
```

Optional:

```text
entity_overrides.json
```

`entity_overrides.json` may contain user-supplied semantic hints such as bolt-hole
roles, but AMG must still be able to run without them.

## Outputs

Primary prediction output:

```text
labels/amg_size_field.json
```

Primary execution outputs:

```text
meshes/ansa_mesh.bdf
reports/ansa_execution_report.json
reports/ansa_quality_report.json
reports/amg_inference_report.json
```

## Part Classification

### Model

Initial production model:

```text
CAD-native tabular Random Forest or Gradient Boosted Trees
```

This is the most appropriate first model because the part-class problem has a small
number of classes, strong engineered B-rep signals, and a high need for interpretability.

Later upgrade:

```text
B-rep graph neural classifier
```

### Input Layer

```text
x_part in R^d
```

Feature groups:

- face, edge, vertex, loop counts
- bounding-box dimensions and aspect ratios
- surface area, volume, and thickness proxy
- analytic surface counts: plane, cylinder, cone, spline
- analytic curve counts: line, circle, arc, spline
- radius and curvature statistics
- loop and hole evidence
- dihedral-angle statistics
- proximity statistics

### Output Layer

```text
p_part in R^6
```

Classes:

```text
SM_FLAT_PANEL
SM_SINGLE_FLANGE
SM_L_BRACKET
SM_U_CHANNEL
SM_HAT_CHANNEL
OTHER
```

If confidence is below threshold, AMG reports `OUT_OF_SCOPE` or `UNCERTAIN_PART_CLASS`
instead of guessing silently.

## Part Segmentation

### Model

Initial model:

```text
BRepSegNet: BRepNet-style coedge message passing with face/edge heads
```

This is the most appropriate first segmentation model because ANSA controls are applied
to CAD entities, and B-rep coedge topology preserves the exact boundary structure.

### Input Layer

```text
G = (faces, edges, coedges, vertices, topology)
X_face in R^(F x d_f)
X_edge in R^(E x d_e)
X_coedge in R^(C x d_c)
```

Topology:

```text
face_has_coedge
coedge_has_edge
edge_has_vertex
coedge_next
coedge_prev
coedge_mate
face_adjacent_face
```

### Output Layer

Face semantic logits:

```text
Y_face in R^(F x C_face)
```

Face classes:

```text
BASE_PANEL
FLANGE
BEND
HOLE_WALL
SLOT_WALL
CUTOUT_WALL
SIDE_WALL
OTHER
```

Edge semantic logits:

```text
Y_edge in R^(E x C_edge)
```

Edge classes:

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

Optional instance outputs:

```text
face_instance_embedding in R^(F x d_i)
same_segment_edge_logits for adjacent faces
```

## Mesh Size Prediction

### Model

Initial deployable model:

```text
EntityQualitySurrogate + constrained size-field optimizer
```

The surrogate predicts local mesh outcome for candidate controls. This follows the
survey's practical mesh-quality prediction pattern: B-rep entities receive local feature
vectors, candidate meshing settings are evaluated, and the model predicts risk or
quality before committing to a full mesh.

Direct `BRepMeshSizeNet` regression is a later acceleration path. It should be trained
after enough optimized size-field labels exist.

### Input Layer

```text
G_B
X_part
X_face
X_edge
face_segmentation_probabilities
edge_segmentation_probabilities
mesh_policy
candidate_edge_size
candidate_face_size optional
candidate_growth_context
```

Mesh policy:

```text
h0_mm
h_min_mm
h_max_mm
user_global_growth_rate
quality_profile
optional_element_budget
```

### Output Layer

Surrogate outputs:

```text
hard_fail_probability in R^(E x 1)
local_boundary_error_quantiles in R^(E x q)
local_quality_margin in R^(E x 1)
element_count_cost in R^(E x 1)
uncertainty in R^(E x 1)
```

Optimizer outputs:

```text
log_h_edge in R^(E x 1)
log_h_face in R^(F x 1) optional
```

Decoded sizes:

```text
h_edge = exp(log_h_edge)
h_face = exp(log_h_face)
```

Projection:

```text
h_min_mm <= h <= h_max_mm
h_i / h_j <= user_global_growth_rate for adjacent entities
```

Optimization objective:

```text
minimize:
  predicted hard-fail risk
  + local boundary error penalty
  + global quality violation penalty
  + element-count/runtime soft cost
  + size discontinuity penalty

subject to:
  h_min_mm <= h_entity <= h_max_mm
  adjacent size ratio <= user_global_growth_rate
```

## ANSA Control Strategy

The first real implementation should stay simple:

1. Apply global shell mesh policy.
2. Apply per-edge target sizes from `amg_size_field.json`.
3. Apply optional per-face target sizes only where ANSA supports stable controls.
4. Use user-specified global growth rate.
5. Run ANSA Batch Mesh.
6. Parse real quality and local feature-boundary metrics.

Do not add a baseline mesh path as a success condition.

## Quality Objective

AMG optimizes for:

- zero hard failed elements
- acceptable aspect, skew, warpage, angle, Jacobian metrics
- local boundary size satisfaction around holes, slots, cutouts, bends, and flanges
- reasonable element count and runtime
- smooth size transition bounded by user growth rate

The loss and benchmark must include local refinement quality, not only global pass/fail.
When repeated ANSA runs show nondeterministic or noisy quality, AMG should learn
threshold risk, quantiles, or uncertainty instead of pretending that a single scalar
quality target is exact.

## Failure Semantics

Valid statuses:

```text
VALID_MESH
OUT_OF_SCOPE
MESH_FAILED
MODEL_UNCERTAIN
ANSA_FAILED
METRIC_UNAVAILABLE
```

`VALID_MESH` requires real ANSA execution report, real quality report, zero hard failed
elements, and a non-empty solver deck.
