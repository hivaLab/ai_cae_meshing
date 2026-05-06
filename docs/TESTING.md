# Testing

## Test Philosophy

Unit tests are necessary but not sufficient. Real meshing claims require real ANSA
evidence.

Tests must prevent these failures:

- hidden baseline success
- mock or placeholder mesh counted as success
- fabricated zero quality metric
- target leakage in graph input
- AMG importing CDF
- ANSA API import outside ANSA scripts

## Standard Regression

```powershell
python -m pytest
```

## Dependency Boundary Tests

Required checks:

- CDF code does not import AMG code.
- AMG code does not import CDF code.
- ANSA API imports appear only under ANSA script directories.
- graph input arrays do not contain target labels or quality scores.
- `reference_midsurface.step` is never used as model input.

## Contract Tests

Validate:

- part classification label schema
- face segmentation label schema
- edge segmentation label schema
- mesh size field schema
- ANSA execution report schema
- ANSA quality report schema

## Model Tests

Part classifier:

- deterministic feature extraction
- trained model can be saved and loaded
- confusion matrix is produced
- uncertainty is handled explicitly

Segmentation model:

- forward pass on B-rep graph
- face and edge output shapes
- masked loss ignores unlabeled entities
- per-class metrics are reported

Size-field model:

- direct B-rep model predicts one size per controlled edge
- optional one size per face
- applies `h_min`, `h_max`, and user growth-rate projection
- does not read target size from graph inputs
- reports uncertainty or threshold risk when repeated meshing outcomes vary

## Real ANSA Gates

Use the verified executable when available:

```text
C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
```

Minimum real gate for the new architecture:

```text
1. generate a compact diverse clean CAD set
2. train or load part classifier
3. train or load segmentation model
4. train or load direct entity size-field model
5. infer held-out size fields
6. apply predicted size field in ANSA
7. validate global and local mesh quality
```

Success requires real execution reports, real quality reports, zero hard failed elements,
available local metrics, and non-empty BDF files.

## What Not To Count

Never count these as success:

- dry run
- mock ANSA
- unavailable ANSA
- controlled failure report
- placeholder BDF
- baseline mesh selected instead of AI output
- local metric placeholder
- schema-valid but behaviorally fake report
