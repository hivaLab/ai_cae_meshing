# Architecture

## Core Principle

The AI model should predict a mesh sizing field over exact CAD entities. It should not
primarily choose from a small list of feature manifest actions.

For clean sheet-metal CAD, the practical minimum ANSA control is:

```text
global target size
user global growth rate
per-edge target size
optional per-face target size
quality profile
```

Hole refinement, slot refinement, cutout refinement, bend refinement, and thin-region
refinement can be represented through the edge/face size field plus a growth-rate
projection.

## Survey-Grounded Design Basis

The 2026 survey by Owen et al. frames AI for CAD-to-mesh work as an assistant to
established geometry kernels and meshers, not a replacement for them. The project
therefore uses AI to choose entity-level meshing controls while ANSA remains the real
meshing engine.

The paper also changes one important design choice: direct neural size-field regression
is not the safest MVP. A more deployable first mesh-control model is a local
mesh-quality surrogate trained on B-rep entity features and real ANSA outcomes. That
surrogate can score candidate edge/face sizes, and a constrained optimizer can choose a
smooth size field. A direct B-rep GNN size predictor is still useful, but as a later
distillation or acceleration step after the quality-surrogate loop is proven.

The resulting model stack is:

```text
part classifier:
  tabular B-rep features -> Random Forest / Gradient Boosting

face/edge segmentation:
  B-rep coedge topology -> BRepNet-style segmentation network

mesh control:
  entity features + candidate sizes -> local quality surrogate
  surrogate + constraints -> optimized edge/face size field
  optional later model -> direct B-rep size-field predictor
```

## System Diagram

```text
CDF
  generate clean sheet-metal CAD
  generate part, face, edge, and size labels
  run ANSA with candidate size fields
  record real global/local quality
  publish dataset files

AMG
  load dataset files only
  build B-rep entity tensors
  train part classifier
  train face/edge segmentation model
  train entity-local quality surrogate
  optimize or infer size field for new CAD
  send size field to ANSA
  validate mesh quality
```

CDF and AMG are separated by files, not Python imports.

## Runtime AMG Pipeline

```text
input.step
  -> import and validate clean sheet-metal B-rep
  -> build B-rep graph
  -> classify part
  -> segment faces and edges
  -> predict edge and face sizes
  -> project sizes:
       h_min <= h <= h_max
       h_adjacent_ratio <= user_global_growth_rate
  -> match graph entities to ANSA entities
  -> apply ANSA edge/face size controls
  -> run ANSA Batch Mesh
  -> parse quality report
```

## Model Stack

### Part Classifier

MVP model:

```text
Random Forest or Gradient Boosted Trees
```

Reason:

- robust on small and medium tabular CAD datasets
- interpretable feature importance
- easier to debug than a graph neural network
- consistent with practical CAD classification trends

Upgrade path:

```text
B-rep graph classifier using face/edge/coedge topology
```

### Face/Edge Segmentation Model

MVP model:

```text
BRepNet-style coedge message passing network
```

Reason:

- segmentation needs exact adjacency and orientation
- point clouds and voxels lose CAD boundary semantics
- multi-view approaches are unsuitable for entity-level ANSA controls

### Mesh-Control Predictor

MVP model:

```text
entity-local mesh-quality surrogate + constrained size-field optimizer
```

The surrogate predicts the expected result of meshing a local CAD entity with a
candidate size and growth context:

- hard-fail probability
- local boundary-size error
- local quality violation margin
- element-count or runtime cost proxy

The optimizer then chooses:

- per-edge target size
- optional per-face target size

Later model:

```text
segmentation-aware heterogeneous B-rep GNN distilled from optimized size fields
```

The postprocessor enforces bounds and growth rate.

## Entity Tensors

Part tensor:

```text
part_feature_vector:
  face_count
  edge_count
  vertex_count
  bbox_dims
  bbox_aspect_ratios
  area_volume_thickness_proxy
  analytic_surface_counts
  analytic_curve_counts
  radius_statistics
  curvature_statistics
  proximity_statistics
```

Face tensor:

```text
face_features:
  surface_type
  area
  perimeter
  bbox
  normal
  centroid
  loop_count
  inner_loop_count
  curvature_statistics
  adjacent_face_count
```

Edge tensor:

```text
edge_features:
  curve_type
  length
  radius
  curvature
  endpoint_distance
  midpoint
  tangent
  dihedral_angle
  adjacent_face_surface_types
  loop_membership_flags
  proximity_to_other_edges
```

Coedge topology:

```text
coedge_next
coedge_prev
coedge_mate
coedge_parent_face
coedge_underlying_edge
```

## ANSA Payload

Minimal payload:

```json
{
  "schema_version": "AMG_SIZE_FIELD_SM_V2",
  "cad_file": "cad/input.step",
  "unit": "mm",
  "global_mesh": {
    "h0_mm": 4.0,
    "h_min_mm": 0.5,
    "h_max_mm": 8.0,
    "growth_rate": 1.25,
    "quality_profile": "AMG_QA_SHELL_V2"
  },
  "edge_sizes": [
    {
      "edge_signature_id": "EDGE_SIG_000001",
      "target_size_mm": 0.8
    }
  ],
  "face_sizes": [
    {
      "face_signature_id": "FACE_SIG_000001",
      "target_size_mm": 2.5
    }
  ]
}
```

The user must be able to change `growth_rate`. The model may recommend local sizes, but
the projection must respect the user growth-rate limit.

## What Is Removed From Primary Design

The following ideas are no longer primary architecture:

- AI selecting a baseline/reference mesh
- success based on baseline comparison
- small feature suppression as the main path
- deterministic feature action rules as the model target
- manifest action classification as the primary model output
- synthetic zero feature boundary errors
- graph target columns
- reference midsurface as model input

Some legacy code may remain until replaced, but new work must not deepen those paths.
