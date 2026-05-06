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

Implemented in this session:

- `cdf-entity ansa-evaluate-size-field` now launches a v2 ANSA size-field script.
- The payload carries `AMG_SIZE_FIELD_SM_V2`, graph arrays, entity signatures, report paths, and BDF path.
- The normal Python runner post-validates reports, entity-local metrics, hard-fail count, and BDF existence.
- A zero ANSA process return code is no longer counted as success unless reports and mesh evidence pass.

Current real gate result:

```text
python -m pytest -> 60 passed
cdf-entity ansa-evaluate-size-field sample_000001 -> BLOCKED
blocked reason: entity_matching_failed
diagnostic path: runs/t806_size_field_gate/ansa_eval/reports/ansa_size_field_diagnostics.json
```

ANSA imported the STEP and created midsurface entities, but CDF edge descriptors could
not yet be matched to ANSA entities. The diagnostic shows 17 CDF edges and 17 ANSA edge
entities, but ANSA edge descriptors currently expose `length=-1.0` and no usable
center/bbox values through the attempted API path.

## Known Gaps

1. Part classifier, segmentation, and quality surrogate train on v2 entity files, but
   only compact/local fixtures have been verified in tests.
2. Entity quality labels still need real ANSA/BDF measured rows for production learning.
3. ANSA edge/face size application for `AMG_SIZE_FIELD_SM_V2` is wired but blocked by
   stable ANSA entity descriptor extraction/matching.
4. No held-out real ANSA end-to-end valid mesh has been counted for the new v2 path yet.
5. Next code work must probe ANSA entity card fields/API methods for CONS, FE PERIMETER,
   FACE, and MACRO descriptors, then replace the current weak descriptor extractor.

## Verified ANSA Path

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```
