# RUNBOOK.md

This runbook defines target commands. Some commands become available only after their corresponding tasks are implemented.

## 1. Environment setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

ANSA is configured separately:

```bash
export ANSA_EXECUTABLE=/path/to/ansa64.sh
```

## 2. Validate documentation and contracts

```bash
python -m pytest tests/test_contracts.py
python -m pytest tests/test_dependency_boundary.py
```

Expected:

```text
all schema files load
example manifest validates
CDF has no AMG imports
ANSA imports are confined to ansa_scripts
```

## 3. Run pure rule tests

```bash
python -m pytest -m "not requires_ansa and not cad_kernel"
```

## 4. Generate a small CDF dataset

Target command after CDF CLI is implemented:

```bash
cdf generate \
  --config configs/cdf_sm_ansa_v1.default.json \
  --out datasets/sm_ansa_v1_smoke \
  --count 10 \
  --seed 1
```

Validate:

```bash
cdf validate --dataset datasets/sm_ansa_v1_smoke
```

## 5. Run ANSA oracle for one sample

```bash
cdf run-ansa-oracle \
  --sample datasets/sm_ansa_v1_smoke/samples/sample_000001 \
  --config configs/cdf_sm_ansa_v1.default.json
```

Expected outputs:

```text
reports/ansa_execution_report.json
reports/ansa_quality_report.json
meshes/ansa_oracle_mesh.bdf
```

## 6. Run AMG rule-only inference

Target command after AMG CLI is implemented:

```bash
amg run \
  --step path/to/input.step \
  --config path/to/amg_config.json \
  --feature-overrides path/to/feature_overrides.json \
  --out runs/amg_case_001
```

Expected outputs:

```text
runs/amg_case_001/mesh_control_manifest.json
runs/amg_case_001/reports/geometry_validation.json
runs/amg_case_001/reports/ansa_quality_report.json
runs/amg_case_001/mesh/solver_deck.bdf
```

## 7. Train AMG model smoke test

Target command after model components are implemented:

```bash
amg train \
  --dataset datasets/sm_ansa_v1_smoke \
  --config configs/train_smoke.json \
  --out runs/train_smoke
```

Expected:

```text
loss decreases or smoke loop completes
checkpoint saved
metrics.json written
```

## 8. Package generated dataset

```bash
cdf package \
  --dataset datasets/sm_ansa_v1_smoke \
  --out artifacts/cdf_sm_ansa_v1_smoke.tar.gz
```

## 9. Exit codes

CDF CLI target exit codes:

```text
0 success
1 configuration/schema error
2 CAD generation failure
3 STEP export/import failure
4 B-rep extraction failure
5 feature truth matching failure
6 label/schema failure
7 ANSA oracle failure
8 dataset packaging failure
```

AMG CLI target exit codes:

```text
0 success
1 configuration/schema error
2 geometry validation OUT_OF_SCOPE
3 B-rep extraction failure
4 manifest generation failure
5 ANSA execution failure
6 quality failure after retry
7 export failure
```
