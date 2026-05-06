# AI CAE Meshing

This repository is being rebuilt around one goal:

```text
clean sheet-metal CAD
  -> B-rep graph
  -> AI part classification
  -> AI face/edge segmentation
  -> AI edge/surface mesh-size prediction
  -> ANSA shell meshing with real quality validation
```

The project is not a rule-only manifest demo, not a baseline mesh generator, and not a
synthetic-data counting exercise. Code is considered useful only when it moves the
system toward AI-driven mesh control that produces real ANSA meshes with measurable
local and global quality.

The design follows the practical lesson from Owen et al. (2026): AI should complement
established CAD kernels and meshing tools. For this project, that means CAD-native
classification, B-rep segmentation, local mesh-quality prediction, constrained size-field
selection, and real ANSA validation.

Start with these documents, in order:

1. `docs/AGENT.md`
2. `docs/STATUS.md`
3. `docs/TASKS.md`
4. `docs/ARCHITECTURE.md`
5. `docs/AMG.md`
6. `docs/CDF.md`
7. `docs/CONTRACTS.md`
8. `docs/ANSA_INTEGRATION.md`
9. `docs/DATASET.md`
10. `docs/TESTING.md`

Obsolete roadmap, model-plan, decision-log, runbook, and risk-register documents were
removed. The remaining documents are the source of truth.
