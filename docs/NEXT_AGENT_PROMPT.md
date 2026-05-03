# NEXT_AGENT_PROMPT.md

This is the rolling handoff prompt for the next coding session. Update it at the end of every completed task together with `docs/STATUS.md` and `docs/TASKS.md`.

```text
You are implementing the AMG/CDF project from the repository documents.

First, read these files in order:
1. AGENT.md
2. STATUS.md
3. TASKS.md
4. CONTRACTS.md
5. ARCHITECTURE.md
6. TESTING.md
7. ANSA_INTEGRATION.md
8. AMG.md
9. CDF.md
10. DATASET.md

Current state:
- P0_BOOTSTRAP_CONTRACTS_AND_RULES is complete.
- T-101 through T-104 are complete.
- T-201 through T-203 are complete.
- T-301 through T-303 are complete.
- T-401 through T-403 are complete.
- T-501 through T-503 are complete.
- T-601 through T-603 are complete, but T-602/T-603 are model skeleton/smoke only.
- T-701_CDF_E2E_DATASET_CLI_FAIL_CLOSED is complete.
- T-702_CDF_REAL_ANSA_API_BINDING is complete for ANSA v25.1.0.
- Latest pure regression: python -m pytest -> 176 passed, 1 skipped.
- Latest real ANSA marker gate:
  $env:ANSA_EXECUTABLE='C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat'; python -m pytest -m requires_ansa
  -> 1 passed.
- Latest real accepted gate:
  python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\e2e_cdf --count 1 --seed 1 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
  -> SUCCESS, accepted_count=1.
  python -m cad_dataset_factory.cdf.cli validate --dataset runs\e2e_cdf --require-ansa
  -> SUCCESS, error_count=0.

Verified ANSA executable:
- C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat

Next task:
- T-703_CDF_ACCEPTED_DATASET_PILOT

Work only on T-703_CDF_ACCEPTED_DATASET_PILOT scope:
- Generate a real CDF pilot dataset with at least 100 accepted samples using the verified ANSA executable.
- Do not count mock, disabled-oracle, controlled-failure, placeholder, dry-run, or synthetic-target samples as accepted.
- Do not mark T-703 DONE from unit tests or smoke tests alone.
- Keep the task IN_PROGRESS or BLOCKED unless strict validation proves the accepted pilot dataset is real.

Closed execution plan:
1. Baseline
   - Confirm the current T-702 changes are committed or intentionally left uncommitted by the user.
   - Run python -m pytest.
   - Run the real ANSA marker gate with ANSA_EXECUTABLE set.

2. Runtime preflight
   - Run cdf ansa-probe against the verified ansa64.bat.
   - Confirm status=OK, import ansa succeeds, and base/batchmesh APIs needed by T-702 are available.
   - If probe fails, stop with BLOCKED and record the exact license/API/runtime failure.

3. Pilot generation
   - Run:
     python -m cad_dataset_factory.cdf.cli generate --config configs\cdf_sm_ansa_v1.default.json --out runs\pilot_cdf_100 --count 100 --seed 1 --require-ansa --ansa-executable C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
   - The requested count means 100 accepted samples, not 100 attempts.
   - Candidate attempts may be rejected, but accepted samples must be promoted only after real ANSA execution and quality parsing.

4. Strict validation
   - Run:
     python -m cad_dataset_factory.cdf.cli validate --dataset runs\pilot_cdf_100 --require-ansa
   - Every accepted sample must contain:
     cad/input.step
     graph/brep_graph.npz
     graph/graph_schema.json
     labels/amg_manifest.json
     reports/ansa_execution_report.json
     reports/ansa_quality_report.json
     meshes/ansa_oracle_mesh.bdf
     reports/sample_acceptance.json
   - Every accepted sample must satisfy:
     accepted_by.ansa_oracle=true
     execution accepted=true
     quality accepted=true
     num_hard_failed_elements=0
     meshes/ansa_oracle_mesh.bdf exists and is non-empty
     no controlled_failure_reason
     ansa_version is neither unavailable nor mock-ansa
     mesh is not placeholder/mock text

5. Pilot evidence report
   - Record requested_count, accepted_count, rejected_count, total attempts, runtime, pass rate, rejection reason counts, and ANSA average runtime.
   - Verify dataset_index.json, dataset_stats.json, rejected_index.json, and split files are deterministic and stable for the fixed seed.
   - Inspect at least the first and last accepted sample reports for relative paths and real mesh artifacts.

Completion criterion for T-703:
- DONE only if at least 100 real ANSA-accepted samples exist and cdf validate --require-ansa passes.
- IN_PROGRESS if generation is running but incomplete.
- BLOCKED if ANSA runtime/license/API/pass-rate prevents completion; record exact failure reason and do not fake acceptance.

Do not implement in T-703:
- AMG real training; that is T-704 after the real accepted pilot dataset exists.
- AMG inference-to-ANSA mesh; that is T-705.
- New graph target_action_id or target numeric control columns.
- Using cad/reference_midsurface.step as a model input.
- Silent fallback that accepts missing ANSA, missing quality report, missing mesh, or failed quality.

Implementation requirements:
- Use Python >= 3.11.
- Keep CDF code independent from AMG imports.
- Keep AMG source independent from CDF package imports; communicate through contract files only.
- Keep ANSA API imports confined to ansa_scripts directories.
- Run python -m pytest before finishing.
- Run the real ANSA gate before marking T-703 DONE.
- Update docs/STATUS.md, docs/TASKS.md, and docs/NEXT_AGENT_PROMPT.md with completed work, tests run, and the next task.

Known risks to check quantitatively:
- T-702 has only proven one flat-panel accepted sample. T-703 must measure scale stability.
- The v1 ANSA binding records manifest controls and uses ANSA Batch Mesh defaults. If quality or feature boundary errors rise, improve real control application instead of adding a fallback.
- The current CDF generator path is mostly flat-panel. If AMG.md/CDF.md require mixed families for T-703, stop and split T-703 into flat pilot and bent-family pilot with explicit acceptance counts.
- Real neural-network training remains unproven until T-704.

Stop and report BLOCKED instead of guessing if AMG.md, CDF.md, CONTRACTS.md, DATASET.md, or ANSA runtime evidence conflict.

At the end, report:
1. completed task IDs
2. changed files
3. test command and result
4. real ANSA command and result
5. pilot dataset counts and validation result
6. next recommended task
7. blockers or risks
```

## Expected next-session output

```text
- T-703 is DONE only if at least 100 real ANSA-accepted samples are generated and strict validation passes.
- Otherwise T-703 remains IN_PROGRESS or BLOCKED with exact ANSA failure reasons and no fake accepted samples.
- python -m pytest passes.
- requires_ansa real gate passes, or exact runtime/license/API blocker is recorded.
- STATUS.md, TASKS.md, and NEXT_AGENT_PROMPT.md remain aligned with the next real-pipeline task.
```
