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
graph/brep_graph.npz
graph/graph_schema.json
graph/entity_signatures.json
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
amg_size_field_ai.json
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

Production model:

```text
CAD-native tabular ensemble: RandomForest, ExtraTrees, HistGradientBoosting
```

This is the most appropriate first model because the part-class problem has a small
number of classes, strong engineered B-rep signals, and a high need for interpretability.
The current trainer evaluates all three model families and stores the selected model,
per-class metrics, confusion matrix, feature importances, uncertainty count, and
calibration status.

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

Primary model:

```text
BRepNetSegmentationModel: BRepNet-style winged-edge coedge message passing
```

This is the most appropriate first segmentation model because ANSA controls are applied
to CAD entities, and B-rep coedge topology preserves the exact boundary structure.
The active model uses coedge `next`, `prev`, and `mate` walks, parent face/edge pooling,
global part-summary context, and direct geometry heads for face/edge semantic logits.

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
HOLE_WALL
SLOT_WALL
CUTOUT_WALL
SIDE_WALL
OTHER
```

`BEND` is intentionally not an active face class until the generated CAD contains true
cylindrical bend-surface support. Bend behavior is currently represented by
`BEND_EDGE`.

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

Primary model:

```text
BRepMeshSizeNet: segmentation-aware B-rep GNN size-field regressor
```

The model predicts per-edge target sizes directly from B-rep entity features,
coedge topology, part probabilities, segmentation probabilities, mesh policy, and user
growth-rate constraints. This is the active path because ANSA ultimately needs entity
controls.

### Input Layer

```text
G_B
X_part
X_face
X_edge
face_segmentation_probabilities
edge_segmentation_probabilities
mesh_policy
part_class_probabilities
face_segmentation_probabilities
edge_segmentation_probabilities
mesh_policy
user_global_growth_rate
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

Model outputs:

```text
log_h_edge in R^(E x 1)
log_h_face in R^(F x 1) optional
uncertainty_edge in R^(E x 1)
uncertainty_face in R^(F x 1) optional
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

Training targets are entity-local size labels derived from CDF generator labels and,
after ANSA/BDF local metrics are available, real quality-evaluated size fields. The
graph input never contains target size, target class, or quality columns.

## ANSA Control Strategy

The first real implementation should stay simple:

1. Apply global shell mesh policy.
2. Apply per-edge target sizes from `amg_size_field.json`.
3. Apply optional per-face target sizes only where ANSA supports stable controls.
4. Use user-specified global growth rate.
5. Run ANSA Batch Mesh.
6. Parse real quality and local feature-boundary metrics.

Do not add a reference-artifact path as a success condition.

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
