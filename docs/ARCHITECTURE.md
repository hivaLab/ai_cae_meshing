# Architecture

## Core Principle

The AI model should predict a mesh sizing field over exact CAD entities.

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

The paper supports using AI as a controller around established meshers. For this project,
the controller should predict entity-local mesh sizes directly, then ANSA remains the
real meshing engine. Local quality evidence is still required, and it is used to train
and validate the size predictor.

The resulting model stack is:

```text
part classifier:
  tabular B-rep features -> Random Forest / Gradient Boosting

face/edge segmentation:
  B-rep coedge topology -> BRepNet-style segmentation network

mesh control:
  B-rep entity graph + segmentation probabilities -> direct edge/face size-field GNN
  projection -> bounded AMG_SIZE_FIELD_SM_V2
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
  train direct size-field model
  infer size field for new CAD
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
segmentation-aware heterogeneous B-rep GNN size regressor
```

The model predicts per-edge target size and optional per-face target size. The
postprocessor enforces bounds and user growth rate. Real ANSA/BDF local quality metrics
are used to validate and improve these predictions.

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

## Active API Boundary

The active API and CLI surface should expose only the entity graph, part classifier,
BRepNet segmentation model, direct size-field model, and real ANSA evaluation path.
Graph arrays must remain label-free: no target size, target class, quality, or action
columns are allowed.
