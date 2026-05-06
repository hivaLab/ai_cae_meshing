# Next Agent Prompt

## Current Direction

Primary pipeline:

```text
clean STEP CAD
  -> B-rep entity graph
  -> part classifier
  -> face/edge segmentation
  -> entity-local quality surrogate
  -> constrained edge/face size field
  -> real ANSA mesh validation
```

The old feature-action manifest and recommendation/ranker path has been removed from
the active code surface.

## Current Task

Implement:

```text
T-806_ANSA_SIZE_FIELD_CONTROL_GATE
```

## Current T-806 State

The first implementation pass is in place:

- `cdf-entity ansa-evaluate-size-field` launches the v2 ANSA script.
- The script reads `AMG_SIZE_FIELD_SM_V2`, graph arrays, and entity signatures.
- The runner refuses to count success unless execution report, quality report,
  entity-local metrics, zero hard failures, and non-empty BDF all exist.
- Unit tests use a fake ANSA adapter for successful edge-size application and blocked
  entity matching.

Verification already run:

```powershell
python -m pytest
```

Result:

```text
60 passed
```

Real ANSA smoke gate:

```text
runs/t806_size_field_gate/dataset/samples/sample_000001
```

Result:

```text
BLOCKED: entity_matching_failed
```

Diagnostic:

```text
runs/t806_size_field_gate/ansa_eval/reports/ansa_size_field_diagnostics.json
```

The diagnostic shows 17 CDF edges and 17 ANSA edge entities, but the current ANSA
descriptor extraction returns `length=-1.0` and no center/bbox for ANSA edges. Do not
mark T-806 done until this is fixed with real ANSA API evidence.

## Goal

Connect `AMG_SIZE_FIELD_SM_V2` to real ANSA controls.

Minimum payload:

- clean STEP path
- global mesh policy
- user `growth_rate`
- per-edge `target_size_mm`
- optional per-face `target_size_mm`
- quality profile

## Required Behavior

1. Do not create or count a reference mesh as success.
2. Do not fabricate local metrics.
3. Do not use removed manifest/action contracts.
4. Match CDF graph entity signatures to ANSA entities explicitly.
5. If edge/face matching cannot be implemented against ANSA v25.1.0, return `BLOCKED`
   with the exact API/matching failure.
6. Count success only when real execution report, real quality report, zero hard failed
   elements, local entity metrics, and non-empty BDF are present.

## Next Code Step

Implement an ANSA entity descriptor probe/fix:

1. Inside `ansa_scripts`, inspect CONS, FE PERIMETER, CURVE, FACE, and MACRO entities
   after STEP import and Skin.
2. Record available card fields, methods, ids, lengths, related macro/perimeter links,
   and any API calls that return stable length/center/bbox descriptors.
3. Replace the current weak `RealAnsaSizeFieldAdapter.collect_edge_descriptors` and
   `collect_face_descriptors` with the verified descriptor path.
4. Re-run the same real gate. If matching succeeds, continue to edge/face size application
   and local metric extraction. If not, keep `BLOCKED` with the exact missing API.

## Verification

Run:

```powershell
python -m pytest
```

Then run a small real ANSA gate with the installed executable:

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```

T-806 is not done until the real gate passes.
