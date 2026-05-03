# DECISIONS.md

This file records fixed architecture decisions for coding agents. Do not reinterpret these decisions during implementation. New decisions require an additional ADR entry and corresponding updates to contracts/tests.

## ADR-001: AMG predicts mesh-control manifest, not mesh connectivity

Status: Accepted

Decision:

```text
AMG predicts `AMG_MANIFEST_SM_V1` controls. ANSA creates mesh nodes and elements.
```

Reason:

```text
Manifest prediction preserves CAD associativity, allows rule projection, and delegates midsurface/washer/quality operations to ANSA.
```

Implementation consequence:

```text
No model output head for node coordinates or element connectivity in AMG-SM-V1.
```

## ADR-002: ANSA Batch Mesh is the execution/oracle backend for SM-ANSA-V1

Status: Accepted

Decision:

```text
AMG execution and CDF oracle validation target ANSA Batch Mesh semantics.
```

Implementation consequence:

```text
Implement ANSA adapter/runner and mocks. Alternative mesh backends are outside SM-ANSA-V1.
```

## ADR-003: CDF and AMG are independent runtime packages

Status: Accepted

Decision:

```text
CDF does not import AMG code. AMG does not import CDF runtime code.
```

Implementation consequence:

```text
Both packages communicate through versioned files and JSON schemas.
```

## ADR-004: Shared canonical enums use AMG-compatible names

Status: Accepted

Decision:

```text
Feature types use HOLE, SLOT, CUTOUT, BEND, FLANGE, OUTER_BOUNDARY.
Actions use KEEP_REFINED, KEEP_WITH_WASHER, SUPPRESS, KEEP_WITH_BEND_ROWS, KEEP_WITH_FLANGE_SIZE.
```

Implementation consequence:

```text
Do not introduce ROUND_HOLE, OBROUND_SLOT, FILL_MICRO, KEEP_REFINE_RING as manifest-level enum values in SM-ANSA-V1.
```

## ADR-005: Graph inputs must not contain target labels

Status: Accepted

Decision:

```text
Graph input may contain expected_action_mask, but not target_action_id or target numeric controls.
```

Implementation consequence:

```text
test_graph_schema_has_no_target_action_column is mandatory.
```

## ADR-006: Rule-only path precedes AI model

Status: Accepted

Decision:

```text
Deterministic manifest generation and schema validation must work before model training.
```

Implementation consequence:

```text
First implementation phase focuses on schemas, formulas, rules, and tests.
```

## ADR-007: ANSA API is isolated to ANSA internal scripts

Status: Accepted

Decision:

```text
General Python modules call ANSA as a subprocess and parse reports. ANSA API import appears only in ansa_scripts.
```

Implementation consequence:

```text
test_ansa_import_scope is mandatory.
```

## ADR-008: Oracle rejection does not rewrite labels

Status: Accepted

Decision:

```text
CDF labels are deterministic from geometry/truth/config. ANSA oracle accepts or rejects samples but does not alter labels.
```

Implementation consequence:

```text
Rejected samples are recorded under rejected/ or rejection reports. Label mutation to pass ANSA is not allowed.
```

## ADR template

```text
## ADR-XXX: Title

Status: Proposed | Accepted | Superseded

Decision:
  ...

Reason:
  ...

Implementation consequence:
  ...

Affected files:
  ...
```
