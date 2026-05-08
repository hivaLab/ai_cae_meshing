# Dataset

## Purpose

The dataset exists to train and validate AI models for CAD-native meshing decisions.

The dataset must answer:

```text
Given this B-rep entity and its context, what mesh size should it receive?
```

## Required Sample Files

```text
sample_000001/
  cad/
    input.step
  graph/
    brep_graph.npz
    graph_schema.json
    entity_signatures.json
  metadata/
    generator_params.json
    part_class_label.json
  labels/
    face_segmentation.json
    edge_segmentation.json
    mesh_size_field.json
  quality_evaluations/
    evaluation_000001/
      size_field.json
      entity_quality_labels.json
      ansa_execution_report.json
      ansa_quality_report.json
      mesh.bdf
  reports/
    ansa_execution_report.json
    ansa_quality_report.json
    sample_acceptance.json
  meshes/
    ansa_mesh.bdf
```

## Dataset Index

```json
{
  "schema": "CDF_DATASET_INDEX_SM_V2",
  "dataset_id": "example",
  "samples": [
    {
      "sample_id": "sample_000001",
      "sample_dir": "samples/sample_000001",
      "part_class": "SM_FLAT_PANEL",
      "status": "PASSED"
    }
  ]
}
```

Statuses:

```text
PASSED
NEAR_FAIL
FAILED
BLOCKED
```

Failed and near-failed samples are valuable for quality learning when their metrics are
real and complete.

## Splits

```text
splits/train.txt
splits/val.txt
splits/test.txt
```

Splits must preserve part-family and feature coverage when the dataset is small.

## Diversity Metrics

Every dataset generation run should report:

- part-class histogram
- face-label histogram
- edge-label histogram
- edge target-size distribution
- global growth-rate distribution
- feature count per sample
- local quality score distribution
- pass, near-fail, fail, blocked counts

## Quality Score

A quality score may combine:

```text
hard failure penalty
global shell quality violation margin
local boundary-size error
element count penalty
runtime penalty
size-field smoothness penalty
```

The score is label-side only. It must not enter model input graphs.

## Direct Size-Field Training And Evaluation Rows

The direct size-field model is supervised by `mesh_size_field.json`. Real ANSA
quality evaluations then verify whether the predicted edge and face sizes actually
produce usable local mesh statistics:

```text
sample_id
evaluation_id
entity_signature_id
entity_type
entity_features reference
candidate_target_size_mm
candidate_growth_context
semantic_label
measured_quality_margin
hard_fail
near_fail
metric_available
```

Rows from the same CAD but different size fields are intentionally preserved. This is
what lets later training rounds improve the direct size predictor without putting
quality or target columns into the graph arrays.

## Scaling Policy

Do not scale to large sample counts until these conditions hold:

1. required classes and entity labels are covered,
2. local quality metrics are available,
3. quality score variance is nonzero,
4. both good and bad controls exist for similar geometries,
5. a small held-out real ANSA gate shows meaningful learning signal.

The user controls sample count through CLI options.
