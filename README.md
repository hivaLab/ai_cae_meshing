# CAE Mesh Automation

This repository implements the executable AI-based CAE mesh automation project
defined by `CAE_MESH_AUTOMATION_IMPLEMENTATION_PLAN.md`.

The project contains two runnable systems:

- `cdf`: CAE Dataset Factory for deterministic synthetic assembly dataset generation.
- `amg`: AI Mesh Generator for model-backed mesh recipe inference and procedural meshing.

The full reproducible delivery workflow is:

```bash
python scripts/run_full_delivery.py
```

The local procedural meshing backend is the default executable backend. The ANSA
backend is implemented as a production adapter with command construction,
staging, config generation, result parsing, status reporting, and error handling.
