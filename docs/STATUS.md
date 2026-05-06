# Project Status

## Current State

The repository is now on the B-rep entity AI meshing path. The legacy feature-action
manifest, ranker recommendation, baseline selection, and surrogate optimizer primary
paths have been removed from active scripts and exports.

Primary path:

```text
clean STEP CAD
  -> CDF B-rep entity graph and entity labels
  -> AMG part classifier
  -> AMG face/edge segmentation
  -> AMG direct segmentation-aware size-field GNN
  -> AMG_SIZE_FIELD_SM_V2
  -> ANSA real edge/face size controls
  -> BDF + real quality/entity-local evidence
```

## Recently Completed

`T-806B_ENTITY_IDENTITY_REBASE`

- `entity_signatures.json` now stores geometry fingerprints, not only row hashes.
- Edge fingerprints include curve type, length, bbox, center, vertex anchor points,
  adjacent faces, coedge count, and loop role.
- Face fingerprints include area, bbox, center, normal, loop count, edge descriptors,
  and adjacent faces.
- Weak row hashes remain only as `debug_row_hash`.
- Added `cdf-entity ansa-probe-entities`.
- Real ANSA probe succeeded at:

```text
runs/t806b_identity_probe/ansa_entity_probe_v2.json
```

Probe evidence:

- `CONS` count: 17
- `FACE` count: 8
- usable `CONS` card fields include `Length`, `Start Point`, `End Point`, and
  `Min Radius`

`T-809_DIRECT_SIZE_FIELD_MODEL`

- Added `BrepSizeFieldModel`, a coedge-aware direct edge/face size-field regressor.
- Added `amg-train-size-field`.
- Added `amg-infer-size-field`.
- Removed the old quality-surrogate optimizer from the active AMG model/training/script
  surface.

Verification:

```powershell
python -m pytest
```

Result:

```text
64 passed
```

`T-810_ENTITY_LOCAL_BDF_METRIC_EXTRACTION`

- Added BDF-based local edge metric extraction from exported NASTRAN GRID/CQUAD4/CTRIA3 data.
- The metric path measures real mesh segment mean/min/max/count per controlled edge.
- `CDF_ENTITY_QUALITY_EVALUATION_SM_V2` now carries measured edge length statistics.
- CDF size-field labels now exclude solid-only seam/thickness edges that are not shell
  mesh-control entities.

Real gate evidence:

```text
sample: runs/t806b_identity_probe_v3/dataset/samples/sample_000001
result: COMPLETED
edge_match_count: 10
BDF: runs/t806b_identity_probe_v3/ansa_eval/meshes/ansa_size_field_mesh.bdf
BDF size: 469274 bytes
entity quality rows: 10
metric_available rows: 10
hard_fail rows: 0
max boundary size error: 0.012345679012345881
```

## Active Task

`T-811_REAL_AI_SIZE_FIELD_GATE`

Why this is the active task:

- The real ANSA size-field control path is now proven on a generated label size field.
- The next missing proof is that AMG's direct size-field model can train/infer an
  `AMG_SIZE_FIELD_SM_V2` and pass the same real ANSA gate on held-out clean CAD.

```text
minimum next gate:
1. generate compact v2 dataset
2. train part classifier, segmentation model, and direct size-field model
3. infer size field on held-out sample
4. run cdf-entity ansa-evaluate-size-field on the AI output
5. require real accepted reports, non-empty BDF, and entity-local metrics
```

## Known Gaps

1. Direct size-field GNN is implemented and trainable, but it has not yet been evaluated
   through real ANSA with accepted local metrics.
2. Current compact CDF labels are generator-derived. Real learning quality still needs
   pass, near-fail, and fail evidence from size-field sweeps.
3. Face controls remain secondary until edge-local metric extraction is reliable across
   non-flat families.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
