# Next Agent Prompt

## Current Direction

The primary path is fixed:

```text
clean STEP CAD
  -> CDF B-rep entity graph
  -> AMG part classifier
  -> AMG face/edge segmentation
  -> AMG direct size-field GNN
  -> AMG_SIZE_FIELD_SM_V2
  -> real ANSA edge/face controls
  -> BDF + real entity-local quality metrics
```

Do not revive feature-action manifests, recommendation/ranker selection, baseline mesh
selection, quality-surrogate optimizer success, mock reports, or fabricated metrics.

## Current State

Completed:

- `T-806B_ENTITY_IDENTITY_REBASE`
- `T-809_DIRECT_BREP_SIZE_FIELD_MODEL`
- `T-810_ENTITY_LOCAL_BDF_METRIC_EXTRACTION`
- `T-806_ANSA_SIZE_FIELD_CONTROL_GATE` for one clean flat-panel smoke sample

Important implementation facts:

- `entity_signatures.json` contains geometry fingerprints and `debug_row_hash`.
- `cdf-entity ansa-probe-entities` probes real ANSA entity descriptor availability.
- `BrepSizeFieldModel` is the primary AMG mesh-control model.
- `amg-train-size-field` and `amg-infer-size-field` are active scripts.
- Local edge metrics are measured from exported NASTRAN BDF GRID/CQUAD4/CTRIA3 data.
- CDF excludes solid-only seam/thickness edges from active shell size-field labels.

Regression command:

```powershell
python -m pytest
```

Latest targeted result:

```text
14 passed for primary entity pipeline + ANSA size-field control tests
```

Latest full regression:

```text
64 passed
```

Real ANSA gate evidence:

```text
dataset: runs\t806b_identity_probe_v3\dataset
sample: runs\t806b_identity_probe_v3\dataset\samples\sample_000001
evaluation: runs\t806b_identity_probe_v3\ansa_eval
status: COMPLETED
edge_match_count: 10
BDF: runs\t806b_identity_probe_v3\ansa_eval\meshes\ansa_size_field_mesh.bdf
BDF size: 469274 bytes
entity quality rows: 10
metric_available rows: 10
hard_fail rows: 0
max boundary size error: 0.012345679012345881
```

## Next Task

Implement:

```text
T-811_REAL_AI_SIZE_FIELD_GATE
```

## Required Work

1. Generate a compact v2 dataset with at least train/held-out samples.
2. Train or load:
   - part classifier
   - face/edge segmentation model
   - direct `BrepSizeFieldModel`
3. Infer `AMG_SIZE_FIELD_SM_V2` on a held-out clean CAD sample using AMG only.
4. Run:

```powershell
python -m cad_dataset_factory.cdf.entity_cli ansa-evaluate-size-field --sample-dir <held-out-sample> --size-field <ai-output-size-field.json> --out <real-eval-out> --ansa-executable "C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat" --timeout-sec 300
```

5. Mark success only if:
   - execution report accepted
   - quality report accepted
   - BDF exists and is non-empty
   - `num_hard_failed_elements == 0`
   - every controlled entity has `metric_available=true`
   - no mock, placeholder, baseline, fallback, or fabricated metric participates

## If Blocked

If the direct model predicts a size field that fails ANSA quality, keep `T-811` as
`IN_PROGRESS` and record:

- sample id
- predicted size-field path
- execution/quality report paths
- BDF path
- entity rows with largest boundary errors
- whether the failure is model quality, segmentation quality, descriptor matching, or
  ANSA control application
