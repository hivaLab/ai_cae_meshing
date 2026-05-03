# MODEL_PLAN.md

## 1. Scope

AMG model development starts only after the dataset file contract and rule-only manifest path exist. The model predicts raw mesh-control parameters that are projected into `AMG_MANIFEST_SM_V1`. The model does not predict mesh connectivity.

## 2. Implementation stages

```text
M0_RULE_ONLY_BASELINE
  Deterministic rules produce manifest without ML.

M1_DATASET_LOADER
  Load CDF dataset graph and labels without CDF runtime dependency.

M2_BASELINE_MODEL
  Simple feature-level baseline, masked action head, numeric heads.

M3_HETEROGENEOUS_GNN
  B-rep node/edge relation message passing.

M4_RULE_PROJECTED_INFERENCE
  Raw model output passes through rule projector and schema validation.

M5_ANSA_VALIDATED_EVALUATION
  Evaluate model manifests through ANSA adapter/oracle where available.
```

## 3. Inputs

Allowed model inputs:

```text
part tensor
face tensor
edge tensor
coedge topology
feature candidate tensor
expected_action_mask
amg_config mesh policy
```

Not allowed as inputs:

```text
target action
target element size
target divisions
ANSA oracle pass/fail label as direct feature
reference_midsurface.step
solver deck connectivity
```

## 4. Output heads

```text
part_class_head
feature_type_head
feature_action_head
log_h_head
division_head
quality_risk_head
```

`feature_action_head` uses mask from `expected_action_mask`.

## 5. Losses

```text
part class       : cross entropy
feature type     : cross entropy
feature action   : masked cross entropy
log h            : Huber(log h_pred - log h_target)
divisions        : ordinal CE or Huber
quality risk     : BCE
rule penalty     : bounds and growth-rate penalty
```

## 6. Rule projector

Model output is not serialized directly. The rule projector enforces:

```text
h_min/h_max
growth_rate_max
role/action mask
unknown feature suppress mask
washer clearance
bend row bounds
flange minimum elements
schema validity
```

## 7. Metrics

Training metrics:

```text
feature_type_accuracy
feature_action_accuracy
log_h_median_relative_error
n_theta_within_2_accuracy
bend_rows_within_1_accuracy
rule_violation_count
```

Execution metrics:

```text
manifest_schema_pass_rate
ANSA first_pass_mesh_success_rate
ANSA after_retry_mesh_success_rate
hard_quality_violation_count
feature_control_satisfaction_rate
```

## 8. Checkpoint policy

Checkpoint should store:

```text
model_state_dict
config
schema versions
feature column schema hash
training dataset index hash
metrics
```

A checkpoint is invalid if graph schema or manifest enum set changes without explicit migration.

## 9. Baseline before GNN

Before implementing a full heterogeneous GNN, implement a rule-only predictor and a simple feature MLP baseline. This provides loader, loss, masking, projection, and evaluation infrastructure with minimal risk.
