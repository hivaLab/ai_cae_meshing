# CDF: CAD Dataset Factory

## Scope

CDF creates training and validation data for AMG. The data must teach models how CAD
geometry relates to mesh controls and real ANSA quality.

The dataset is not valuable because it is large. It is valuable when it contains:

- diverse clean sheet-metal CAD
- reliable part-class labels
- reliable face/edge segmentation labels
- edge/face target size labels
- real ANSA quality measurements
- pass, near-fail, and fail examples

## Clean CAD Assumption

Defeaturing is out of scope for the current phase. CDF should generate or accept clean
constant-thickness sheet-metal parts with preserved boundaries.

Small holes, slots, cutouts, bends, and flanges are not removed as the default path.
Their boundaries become segmentation and sizing targets.

## Dataset Output

Each sample should support the new AMG pipeline:

```text
sample_000001/
  cad/
    input.step
  metadata/
    generator_params.json
    part_class_label.json
  graph/
    brep_graph.npz
    graph_schema.json
    entity_signatures.json
  labels/
    face_segmentation.json
    edge_segmentation.json
    mesh_size_field.json
  meshes/
    ansa_mesh.bdf
  reports/
    ansa_execution_report.json
    ansa_quality_report.json
    sample_acceptance.json
```

`reference_midsurface.step` may exist for debugging, but it is not an AMG model input.

## Labels

### Part Classification Label

```json
{
  "schema_version": "CDF_PART_CLASS_LABEL_SM_V2",
  "sample_id": "sample_000001",
  "part_class": "SM_L_BRACKET",
  "source": "generator_truth"
}
```

### Face Segmentation Label

```json
{
  "schema_version": "CDF_FACE_SEGMENTATION_SM_V2",
  "sample_id": "sample_000001",
  "labels": [
    {
      "face_signature_id": "FACE_SIG_000001",
      "semantic_label": "BASE_PANEL",
      "instance_id": "PANEL_0001"
    }
  ]
}
```

### Edge Segmentation Label

```json
{
  "schema_version": "CDF_EDGE_SEGMENTATION_SM_V2",
  "sample_id": "sample_000001",
  "labels": [
    {
      "edge_signature_id": "EDGE_SIG_000001",
      "semantic_label": "HOLE_BOUNDARY",
      "instance_id": "HOLE_0001"
    }
  ]
}
```

### Mesh Size Field Label

```json
{
  "schema_version": "CDF_MESH_SIZE_FIELD_SM_V2",
  "sample_id": "sample_000001",
  "global_mesh": {
    "h0_mm": 4.0,
    "h_min_mm": 0.5,
    "h_max_mm": 8.0,
    "growth_rate": 1.25
  },
  "edge_sizes": [
    {
      "edge_signature_id": "EDGE_SIG_000001",
      "target_size_mm": 0.8,
      "label_source": "ansa_quality_search"
    }
  ],
  "face_sizes": []
}
```

## Generation Strategy

CDF should generate small but diverse datasets first.

Required diversity axes:

- part family
- thickness
- dimensions
- bend angle and radius
- flange width
- hole radius and proximity
- slot width, length, and end radius
- cutout size and corner radius
- feature count
- feature spacing
- global growth rate
- local size choices

The user controls dataset size with `--count`. Development defaults should favor fast
iteration, not large counts.

## Quality Exploration

For each clean geometry, CDF should evaluate multiple size fields through real ANSA.
The goal is not to accept only perfect samples. The goal is to learn which controls
improve or degrade quality.

Each evaluated size field records:

- global quality metrics
- local feature-boundary metrics
- element count
- runtime
- status: `PASSED`, `NEAR_FAIL`, `FAILED`, or `BLOCKED`

Failed and near-failed cases are label-side evidence. They must not be hidden.

## Entity Quality Evaluation Corpus

The paper emphasizes that mesh-quality prediction is naturally supervised at the
B-rep entity level: each vertex, curve, or surface receives local geometry/topology
features, and labels come from meshing the CAD under multiple target sizes and
settings.

CDF therefore must store not only the best size field, but also evaluated candidate
controls:

```text
quality_evaluations/
  evaluation_000001/
    size_field.json
    ansa_execution_report.json
    ansa_quality_report.json
    mesh.bdf
    entity_quality_labels.json
```

Each `entity_quality_labels.json` records, per edge/face:

- entity signature id
- candidate target size
- local growth context
- measured local quality
- measured local boundary error
- threshold pass/fail
- uncertainty or repeated-run statistics when available

This evidence is used to validate and improve AMG's direct entity size-field model.

## Local Quality Metrics

At minimum:

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
reason when unavailable
```

If a metric cannot be measured, record it as unavailable. Do not write a fabricated
zero error.

## Part Naming

Part names are metadata. Models must not rely on names for classification.

Recommended form:

```text
SMT_<CLASS>_T<thickness100>_<sample_id>
```

Example:

```text
SMT_SM_L_BRACKET_T120_sample_000042
```

The true label remains in `part_class_label.json`.

## Completion Criteria For CDF

CDF is useful when it can:

1. generate clean sheet-metal CAD with varied geometry,
2. produce entity-level labels,
3. generate several mesh-size candidates per geometry,
4. run real ANSA,
5. record global and local quality,
6. preserve evaluated good, near-fail, and failed candidate controls,
7. publish files AMG can consume without importing CDF.
