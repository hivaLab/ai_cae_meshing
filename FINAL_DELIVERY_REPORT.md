# Final Delivery Report

Generated at: 2026-04-30T11:54:25.515332+00:00

## Workflow Commands
- validate_all_repository_schemas
- cad kernel status
- cdf generate --num-samples 1000
- cdf validate-dataset
- cdf build-graphs
- train-brep-assembly-net
- evaluate-brep-assembly-net --split test
- export-amg-model
- amg run-mesh
- amg validate-result
- ansa backend status
- amg run-mesh --backend ANSA_BATCH
- amg validate-result --backend ANSA_BATCH

## Dataset
- CAD kernel: CadQuery/OCP(OpenCascade)
- AP242 B-Rep export available: True
- Dataset ID: LGE_SYNTH_CAE_MESH_V001
- Accepted samples: 1000
- Rejected samples: 0
- Splits: train 800 / val 100 / test 100
- Acceptance rate: 1.0000
- Dataset validation passed: True
- STEP AP242 B-Rep failures: 0
- Graph artifact validation passed: True
- graph.pt files: 1000
- brep_graph.json files: 1000
- assembly_graph.json files: 1000

## Model
- Model type: hetero_brep_assembly_net
- Model path: C:\Users\r0801\Desktop\code\06_ai_cae_meshing\runs\full_delivery\artifacts\models\brep_assembly_net_v001\model.pt
- Exported model path: C:\Users\r0801\Desktop\code\06_ai_cae_meshing\runs\full_delivery\artifacts\models\amg_deployment_model.pt
- Hidden dim: 32
- Message passing layers: 2
- Edge relation types: 16
- Train MAE: 0.701734
- Val MAE: 0.705501
- Test MAE: 0.720296
- Test RMSE: 0.768061
- Size MAE percent: 0.075206
- PartStrategy macro F1: 1.000000
- FaceSemantic mean IoU: 1.000000
- EdgeSemantic macro F1: 1.000000
- Connection recall: 1.000000
- Failure risk recall: 0.941240
- Repair top-1 accuracy: 0.637500

## AMG Result
- Test sample: sample_000900
- Result package validation passed: True
- BDF parse success: True
- Missing properties: 0
- Missing materials: 0
- Shell elements: 6
- Solid elements: 5
- Connectors: 9

## ANSA Backend
- Available: True
- Executable: C:\Users\r0801\AppData\Local\Apps\BETA_CAE_Systems\ansa_v25.1.0\ansa64.bat
- Fallback enabled: False
- Execution probe attempted: True
- Execution probe passed: True
- Batch Meshing Manager invoked: True
- Batch Meshing Manager note: ANSA batchmesh sessions applied AI mesh recipe parameters per part and ran Batch Mesh Manager
- ANSA import counts: {'ANSAPART': 12, 'CBUSH': 0, 'CONM2': 0, 'FACE': 72, 'GRID': 0, 'MAT1': 1, 'PBUSH': 0, 'PSHELL': 12, 'PSOLID': 0, 'RBE2': 0, 'RBE3': 0, 'SHELL': 0, 'SOLID': 0, '__ELEMENTS__': 0}
- ANSA batch counts: {'ANSAPART': 12, 'CBUSH': 8, 'CONM2': 1, 'FACE': 72, 'GRID': 12675, 'MAT1': 4, 'PBUSH': 1, 'PSHELL': 12, 'PSOLID': 5, 'RBE2': 0, 'RBE3': 0, 'SHELL': 12616, 'SOLID': 5, '__ELEMENTS__': 12630}
- AI recipe batch sessions: 11
- Per-part size fields planned: 12
- BMM size-field sessions applied: 11
- Materials written to deck: 4
- PSHELL properties updated: 11
- Solver-deck element fallback enabled: False
- Native CTETRA solids generated: 5
- Native CBUSH connectors generated: 8
- Native CONM2 masses generated: 1
- ANSA quality repair status: passed_no_repair_required
- ANSA QA repair loop records: 3

## ANSA Production Regression
- Command: `python scripts/run_ansa_regression.py --sample-count 10`
- Regression report: `ANSA_REGRESSION_REPORT.md`
- Sample count: 10
- Passed samples: 10
- Failed samples: 0
- Native CTETRA total: 50 / expected 50
- Native CBUSH total: 80 / expected 80
- Native CONM2 total: 10 / expected 10
- Total runtime seconds: 136.662
- Regression acceptance: ACCEPTED

## Known Limitations
- Generated assemblies are deterministic synthetic CAD solids exported through CadQuery/OCP, not OEM production CAD.
- ANSA backend is explicit and does not fall back to local meshing.

## Final Acceptance Status

ACCEPTED
