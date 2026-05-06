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
