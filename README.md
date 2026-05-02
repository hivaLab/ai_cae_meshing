# CAE Mesh Automation

This repository implements the executable AI-based CAE mesh automation project
defined by `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md`.

For the LG Electronics research-request scope, use
`docs/lg_research_scope_design_guide.md` as the practical design guide. That
scope focuses on structural CAE shell mesh automation for constant-thickness
sheet-metal parts first, then variable-thickness molded-plastic assemblies.

The project contains two runnable systems:

- `cdf`: CAE Dataset Factory for deterministic synthetic bootstrap dataset generation.
- `amg`: AI Mesh Generator for model-backed mesh recipe inference and ANSA_BATCH production meshing.

The full reproducible delivery workflow is:

```bash
python scripts/run_full_delivery.py
```

ANSA_BATCH is the only production AMG backend. The deterministic synthetic
oracle is used only inside CDF to bootstrap labels and test artifacts; it is not
reported as production mesh automation capability. If ANSA is unavailable,
production AMG meshing fails explicitly.

Real supervised training submissions should use this minimum structure:

```text
sample_id/
  cad/raw.step
  ansa/final.ansa
  metadata/acceptance.csv
  metadata/quality_criteria.yaml
  solver/final.bdf                  # optional; exportable from ANSA
  reports/ansa_quality_report.*      # optional; exportable from ANSA
```

`acceptance.csv` must contain:

```text
sample_id,acceptance_status,reviewer,review_date,use_for_training,reject_reason,notes
```

Material constants such as Young's modulus, density, and Poisson ratio are not
required for mesh automation training unless solver-ready BDF export is part of
the requested workflow.
