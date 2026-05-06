# Project Status

## Current State

The repository has been cut over to the B-rep entity AI meshing direction.

Removed from the active path:

- feature-action manifest generation
- deterministic action-head models
- quality ranker recommendation and fresh proposal CLIs
- old manifest/ranker tests
- old primary console scripts

Primary path now uses:

```text
clean STEP CAD
  -> B-rep entity graph
  -> part classifier
  -> face/edge segmentation
  -> entity-local quality surrogate
  -> constrained edge/face size field
  -> ANSA real size-field mesh gate
```

## Recently Completed

`T-802_TO_T804_PRIMARY_ENTITY_PIPELINE_SCAFFOLD`

- Added `cdf-entity generate` and `cdf-entity validate`.
- Added `amg-train-part-classifier`.
- Added `amg-train-entity-segmentation`.
- Added `amg-train-quality-surrogate`.
- Added `amg-optimize-size-field`.
- Removed active legacy manifest/recommendation modules and tests.
- Rebased configs and schemas around v2 size-field control.

Verification:

```powershell
python -m pytest
```

Result:

```text
56 passed
```

## Active Task

`T-806_ANSA_SIZE_FIELD_CONTROL_GATE`

The remaining critical gap is the real ANSA binding for `AMG_SIZE_FIELD_SM_V2`.
`cdf-entity ansa-evaluate-size-field` currently fails closed and does not count success.

## Known Gaps

1. Part classifier, segmentation, and quality surrogate train on v2 entity files, but
   only compact/local fixtures have been verified in tests.
2. Entity quality labels still need real ANSA/BDF measured rows for production learning.
3. ANSA edge/face size application for `AMG_SIZE_FIELD_SM_V2` is not complete.
4. No held-out real ANSA end-to-end valid mesh has been counted for the new v2 path yet.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
