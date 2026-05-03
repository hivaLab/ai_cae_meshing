# ARCHITECTURE.md

## 1. Workspace layout

The project may be developed as one workspace containing two independent Python packages. Runtime dependency from CDF to AMG is not allowed.

```text
repo_root/
  AMG.md
  CDF.md
  AGENT.md
  STATUS.md
  ROADMAP.md
  TASKS.md
  CONTRACTS.md
  pyproject.toml
  contracts/
    AMG_MANIFEST_SM_V1.schema.json
    AMG_BREP_GRAPH_SM_V1.schema.json
    AMG_CONFIG_SM_V1.schema.json
    AMG_FEATURE_OVERRIDES_SM_V1.schema.json
    CDF_FEATURE_TRUTH_SM_V1.schema.json
    CDF_ANSA_ORACLE_REPORT_SM_V1.schema.json
  configs/
    amg_config.default.json
    cdf_sm_ansa_v1.default.json
    quality/AMG_QA_SHELL_V1.json
    ansa/AMG_SHELL_CONST_THICKNESS_V1.json
  ai_mesh_generator/
    amg/
      brep/
      labels/
      model/
      ansa/
      validation/
      cli.py
  cad_dataset_factory/
    cdf/
      sampling/
      cadgen/
      truth/
      brep/
      labels/
      oracle/
      dataset/
      cli.py
  tests/
```

Separate repositories are also acceptable if the same `contracts/` files are copied into both repositories. In that case the contract version strings must remain identical.

## 2. Package responsibilities

### 2.1 `cad_dataset_factory`

CDF owns synthetic dataset generation.

```text
parameter sampling
CAD solid generation
feature truth generation
reference midsurface generation
B-rep graph extraction for dataset
AMG-compatible manifest label generation
ANSA oracle execution for sample acceptance
sample directory writing
```

CDF does not run AMG inference, does not import AMG, and does not call AMG's ANSA adapter.

### 2.2 `ai_mesh_generator`

AMG owns inference and mesh-control execution.

```text
input STEP validation
B-rep graph extraction
feature detection
AI or rule-only manifest generation
rule projection
ANSA manifest execution
quality report parsing
solver deck export
```

AMG may read CDF-generated dataset files as external training data. AMG does not depend on CDF runtime modules.

## 3. Data flow

### 3.1 CDF generation flow

```text
config + seed
  → sampled part parameters
  → CAD solid + feature truth
  → STEP + reference midsurface
  → B-rep graph extraction
  → deterministic AMG-compatible manifest
  → ANSA oracle validation
  → accepted/rejected sample directory
```

### 3.2 AMG inference flow

```text
input.step + amg_config.json + optional feature_overrides.json
  → geometry validation
  → B-rep graph extraction
  → feature candidate detection
  → model or rule-only prediction
  → rule projection
  → mesh_control_manifest.json
  → ANSA adapter execution
  → quality report and solver deck
```

## 4. Dependency boundaries

```text
CDF core             : may use CadQuery/OCP, numpy, scipy, pydantic/jsonschema, networkx
CDF ANSA runner      : subprocess only outside ANSA
CDF ANSA scripts     : may import ANSA Python API
AMG core             : may use CAD/B-rep extractor, ML framework, jsonschema
AMG ANSA adapter     : subprocess or ANSA internal scripts depending on implementation
Contracts            : JSON files, not Python imports across packages
```

## 5. External dependency strategy

```text
ANSA unavailable:
  Run all pure tests and mocked report parser tests.

CadQuery/OCP unstable:
  Keep P0/P1 pure rules independent of CAD kernel.

ML framework not selected:
  Implement dataset loader and rule-only baseline first.
```

## 6. Status and failure state model

AMG manifest status:

```text
VALID
OUT_OF_SCOPE
MESH_FAILED
```

CDF sample acceptance:

```text
accepted: true/false
accepted_by.geometry_validation
accepted_by.feature_matching
accepted_by.manifest_schema
accepted_by.ansa_oracle
rejection_reason
```

All failures must have structured reason strings. Free-form prose is allowed only in an auxiliary `message` field.
