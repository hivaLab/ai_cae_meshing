# AGENTS.md

## Project instruction

This repository implements the AI-based CAE mesh automation system defined in:

- `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md`

Read `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md` before writing code. Treat that document as the implementation source of truth.

For LG Electronics research-request alignment, also read:

- `docs/lg_research_scope_design_guide.md`

When broad CAE automation ideas conflict with the LG research scope, prioritize
the LG scope: AI-assisted structural shell mesh automation for
constant-thickness sheet-metal parts first, followed by variable-thickness
molded-plastic assemblies. Generic CFD meshing and universal arbitrary solid
meshing are secondary unless explicitly requested.

## Implementation target

Build the complete Python project described in the implementation plan.

The delivered repository must include:

1. Shared schemas and validators
2. CAE Dataset Factory, CDF
3. AI Mesh Generator, AMG
4. CDF synthetic oracle meshing backend
5. ANSA command backend adapter
6. QA and BDF validation modules
7. Graph dataset builder
8. Compact AI model and training pipeline
9. CLI entrypoints
10. Unit, integration, and end-to-end tests
11. Full delivery script
12. Implementation status document
13. Final delivery report

## Dataset target

The accepted dataset target for this implementation is:

```text
1,000 accepted synthetic assembly samples
train / val / test = 800 / 100 / 100
```

The generated dataset must contain:

1. Input package files
2. Synthetic assembly geometry data
3. Part, face, edge, connection, size-field, failure-risk, and repair-action labels
4. Synthetic-oracle mesh data
5. BDF files
6. QA metrics
7. Graph files
8. Dataset index
9. Train, validation, and test split files

## Development workflow

Follow the milestone order in `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md`.

For each milestone:

1. Implement the required modules.
2. Add or update tests.
3. Run the relevant tests.
4. Fix failing tests.
5. Update `IMPLEMENTATION_STATUS.md`.

Use deterministic seeds for:

1. Synthetic assembly generation
2. Mesh generation
3. Graph construction
4. Dataset split generation
5. Model training
6. Model evaluation
7. AMG inference demo

## Engineering standards

Use practical, runnable Python code.

Keep module boundaries clear.

Use typed data models.

Use deterministic tests.

Use explicit CLI commands.

Use ANSA_BATCH as the executable production AMG backend for the full delivery workflow.
The deterministic synthetic oracle is CDF-internal only and must not be used as
evidence that production AMG meshing works.

Implement the ANSA backend as a production adapter with:

1. Command construction
2. Config generation
3. Input artifact staging
4. Result parsing
5. Error handling
6. Backend status reporting

Use optional dependency handling for heavy or proprietary libraries in dataset
building and inspection code. Production AMG meshing must fail explicitly when
ANSA is unavailable; it must not fall back to synthetic or local meshing.

## Required CLI commands

Provide the following commands:

```bash
cdf generate
cdf validate-dataset
cdf build-graphs
train-brep-assembly-net
amg run-mesh
amg validate-result
```

Provide the following final delivery script:

```bash
python scripts/run_full_delivery.py
```

The full delivery script must execute the complete workflow:

1. Validate configs and schemas
2. Generate 1,000 accepted synthetic assembly samples
3. Validate the generated dataset
4. Build graph files
5. Train the compact model
6. Evaluate the trained model
7. Run AMG inference on at least one held-out test sample
8. Generate an AMG mesh result package
9. Validate the AMG result package
10. Write `FINAL_DELIVERY_REPORT.md`

## Status tracking

Maintain `IMPLEMENTATION_STATUS.md`.

Record:

1. Completed milestones
2. Commands executed
3. Test results
4. Generated dataset counts
5. Dataset acceptance statistics
6. Model metrics
7. AMG validation results
8. Known limitations
9. Final acceptance status

## Completion criteria

The implementation is complete when:

1. The repository structure matches `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md`.
2. Shared schemas validate all defined input, output, dataset, label, graph, mesh recipe, and QA objects.
3. CDF generates 1,000 accepted synthetic assembly samples.
4. The dataset contains input packages, labels, graphs, BDF mesh files, QA metrics, and dataset split files.
5. The compact AI model trains on the generated dataset.
6. The trained model is exported as a reusable model artifact.
7. AMG loads the trained model and runs inference on a held-out test sample.
8. AMG generates a mesh result package through ANSA_BATCH.
9. QA validation passes for the generated AMG result package.
10. Unit tests pass.
11. Integration tests pass.
12. End-to-end tests pass.
13. `FINAL_DELIVERY_REPORT.md` summarizes implementation results, dataset statistics, model metrics, AMG validation metrics, and truthful status classes such as `SYNTHETIC_BOOTSTRAP_ACCEPTED`, `ANSA_SMOKE_PASSED`, and `LG_PRODUCTION_NOT_VALIDATED`.

## Truthfulness requirements

No silent omission is allowed. Every CAD product/part must be represented in the
FE output as explicit mesh, connector, mass, approved exclude, or manual
review/failure. Any unrepresented part is a validation failure.

`approved_exclude` requires explicit acceptance metadata. CAD parts must not be
excluded by name pattern or convenience rule.

Physical material constants such as Young's modulus, density, and Poisson ratio
are not required for mesh automation training submissions unless a solver-ready
BDF is explicitly part of the target workflow. Shell thickness and shell quality
criteria are required for shell mesh validation.
