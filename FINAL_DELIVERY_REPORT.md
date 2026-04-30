# Final Delivery Report

Generated at: 2026-04-30T07:17:24.389675+00:00

## Workflow Commands
- python -m pytest
- python scripts/run_full_delivery.py
- validate_all_repository_schemas
- cdf generate --num-samples 1000
- cdf validate-dataset
- cdf build-graphs
- train-brep-assembly-net
- evaluate-brep-assembly-net --split test
- amg run-mesh
- amg validate-result

## Test Results
- Unit tests: 13 passed
- Unit + integration tests: 15 passed
- E2E tests: 2 passed
- Full test suite: 17 passed

## Dataset
- Dataset ID: LGE_SYNTH_CAE_MESH_V001
- Accepted samples: 1000
- Rejected samples: 0
- Splits: train 800 / val 100 / test 100
- Acceptance rate: 1.0000
- Dataset validation passed: True

## Model
- Train MAE: 0.029639
- Val MAE: 0.029139
- Test MAE: 0.029281
- Test RMSE: 0.038217

## AMG Result
- Test sample: sample_000900
- Result package validation passed: True
- BDF parse success: True
- Missing properties: 0
- Missing materials: 0
- Shell elements: 6
- Solid elements: 5
- Connectors: 9

## Known Limitations
- Full delivery uses deterministic procedural geometry instead of a heavy CAD kernel.
- ANSA backend is a production command adapter and is not used as the executable delivery backend.

## Final Acceptance Status

ACCEPTED
