# RISK_REGISTER.md

## Risk levels

```text
Low
Medium
High
Critical
```

## Active risks

| ID | risk | level | trigger | mitigation | owner doc |
|---|---|---:|---|---|---|
| R-001 | ANSA executable/license unavailable | Medium | `ANSA_EXECUTABLE` missing, license failure, or `requires_ansa` gate skipped | keep pure tests for development feedback, but keep P7 tasks IN_PROGRESS/BLOCKED until real ANSA gates pass | ANSA_INTEGRATION.md |
| R-002 | CAD boolean operations fail non-deterministically | High | STEP export/re-import failure rate rises | isolate CAD generation by family; store rejected attempts; add deterministic seed fixtures | DATASET.md |
| R-003 | B-rep entity IDs unstable after STEP import | High | feature matching mismatch | use geometry/topology signatures; never rely on raw entity IDs | CONTRACTS.md |
| R-004 | Label leakage in graph inputs | Critical | target action/size appears in graph schema | add schema tests; keep labels only in labels/ | CONTRACTS.md |
| R-005 | AMG/CDF enum drift | Critical | CDF emits action AMG cannot consume | central contracts; schema validation in both packages | CONTRACTS.md |
| R-006 | ANSA oracle silently modifies labels | High | accepted manifest differs from generated label | oracle must not rewrite labels; reject sample instead | ANSA_INTEGRATION.md |
| R-007 | Synthetic dataset too narrow | Medium | model succeeds on generated but fails on real constant-thickness sheet metal | add holdout splits and scope validation phase | ROADMAP.md |
| R-008 | Growth-rate projection changes feature-critical sizes too much | Medium | hole/bend control satisfaction drops | weighted smoothing; feature controls high priority; report deviations | AMG.md |
| R-009 | Ambiguous entity matching | High | two candidates match same signature | reject sample or OUT_OF_SCOPE; do not auto-select | CONTRACTS.md |
| R-010 | Model implemented before rule-only baseline | Medium | code complexity rises before labels are stable | enforce roadmap order; start with rule-only and dataset loader | MODEL_PLAN.md |
| R-011 | Mock or placeholder artifact is mistaken for real pipeline success | Critical | accepted sample contains mock/unavailable ANSA report, controlled_failure_reason, missing mesh, or placeholder mesh | fail-closed dataset validation; P7 completion requires real ANSA reports, zero hard failures, and non-empty BDF mesh | ANSA_INTEGRATION.md |
| R-012 | One-sample ANSA gate does not scale to pilot dataset | High | T-703 pass rate too low, timeout rate too high, or rejected attempts exceed budget | record rejection reasons and runtime per attempt; improve real ANSA controls only where evidence demands it | CDF.md |

## Risk update rule

When a new risk appears, add:

```text
ID
risk description
level
trigger
mitigation
owner doc or task ID
```

When a risk is resolved, keep the row and append:

```text
status = resolved
resolution date
resolution evidence
```

## Immediate mitigations for first coding phase

```text
1. P0 uses no ANSA and no CAD kernel for acceptance.
2. Dependency boundary tests are mandatory.
3. Graph schema test explicitly rejects target_action_id.
4. JSON schema examples validate before feature work expands.
```
