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
66 passed
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

`T-812_DIVERSE_ENTITY_DATASET_AND_MODEL_VALIDATION`

- Added `sm_entity_v2_diverse_quality`, a 32-sample compact profile with case-stratified
  train/test splits.
- Added real ANSA size-field sweeps for `h_min_overrefined`, `fine`, `nominal`, and
  `coarse` variants.
- Added quality-aware size-field training through `--prefer-quality-evidence`.
- Added gate-report learning-signal checks for target-size variance and all-`h_min`
  collapse.

Verification:

```powershell
python -m pytest
```

Result:

```text
69 passed
```

Real T-812 evidence:

```text
dataset: runs/t812_diverse_entity_validation/dataset
profile: sm_entity_v2_diverse_quality
sample count: 32
train/test split: 24/8
size sweep: 32 attempted, 17 completed, 3 failed, 12 blocked
quality rows: 260 total, 248 metric_available
hard_fail rows: 18
near_fail rows: 18
```

Held-out flat sample:

```text
sample: sample_000025
part class: SM_FLAT_PANEL
status: SUCCESS
edge size stats: count=10, min/mean/max/std=0.5/0.5899280985082083/0.625/0.04901566409509156
h_min edge fraction: 0.2
entity metrics: 10/10 available
hard_fail rows: 0
max boundary size error: 0.004648606178533798
BDF bytes: 9528865
```

Held-out bent sample:

```text
sample: sample_000032
part class: SM_HAT_CHANNEL
status: SUCCESS
edge size stats: count=24, min/mean/max/std=0.5/0.5449059218846366/0.625/0.05722437956992055
h_min edge fraction: 0.5
entity metrics: 24/24 available
hard_fail rows: 0
max boundary size error: 0.008064516129032473
BDF bytes: 20326149
```

## Active Task

`T-813_ENTITY_MATCHING_AND_QUALITY_EVIDENCE_COVERAGE`

Why this is the active task:

- T-812 produced real pass and fail/near-fail size sweep evidence, but sweep coverage is
  incomplete.
- Flat slot cases were blocked by `entity_matching_failed`.
- Quality-aware size-field training used only 5 samples with usable evidence.
- The next improvement must increase real evidence coverage before claiming broader
  model generalization.

```text
T-812 blocker:
flat_slot sweep samples sample_000002, sample_000010, and sample_000018 blocked with
entity_matching_failed for every sweep variant.
```

## Known Gaps

1. Entity matching is not robust for flat slot cases.
2. Quality-aware training currently skips samples without usable real sweep metrics.
3. The direct size-field model now predicts nontrivial sizes on two held-out samples, but
   the learned range is still narrow: `0.5..0.625 mm`.
4. Face controls remain secondary until edge-local metric extraction is reliable across
   non-flat families.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
