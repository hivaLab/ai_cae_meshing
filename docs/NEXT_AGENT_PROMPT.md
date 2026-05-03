# NEXT_AGENT_PROMPT.md

아래 프롬프트를 첫 번째 코딩 에이전트 세션에 그대로 사용할 수 있다.

```text
You are implementing the AMG/CDF project from the repository documents.

First, read these files in order:
1. AGENT.md
2. STATUS.md
3. TASKS.md
4. CONTRACTS.md
5. ARCHITECTURE.md
6. TESTING.md
7. AMG.md
8. CDF.md

Work only on P0_BOOTSTRAP_CONTRACTS_AND_RULES. Do not implement CadQuery CAD generation, real ANSA execution, or AMG model training in this session.

Complete these tasks if possible:
- T-001_REPOSITORY_SKELETON
- T-002_CONTRACT_SCHEMA_SKELETON
- T-003_CONFIG_SCHEMA_AND_DEFAULTS
- T-004_MATH_UTILITIES
- T-005_LABEL_RULES_PURE
- T-006_DEPENDENCY_BOUNDARY_TESTS

Implementation requirements:
- Use Python >= 3.11.
- Create importable package skeletons for ai_mesh_generator and cad_dataset_factory.
- Create contracts/*.schema.json files with canonical enums from CONTRACTS.md.
- Implement pure formula utilities and deterministic label rule functions with unit tests.
- CDF code must not import AMG code.
- ANSA API imports must not appear outside ansa_scripts directories.
- Graph schema must not contain target_action_id or target numeric control columns.
- Run pytest before finishing.
- Update STATUS.md and TASKS.md with completed work, tests run, and the next task.

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, and CONTRACTS.md conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. next recommended task
5. any blockers or risks
```

## Expected first-session output

```text
- repository skeleton exists
- schema skeleton files validate as JSON
- pure formula tests pass
- label rule tests pass
- dependency boundary tests pass
- STATUS.md and TASKS.md updated
```
