# Agent Guide

## Mission

Build an AI-based sheet-metal meshing tool that works with real ANSA execution.

The intended runtime path is:

```text
STEP clean CAD
  -> exact B-rep graph
  -> part classification model
  -> face/edge segmentation model
  -> direct segmentation-aware edge/surface size-field GNN
  -> size-field projection with user global growth rate
  -> ANSA local mesh controls
  -> real mesh and quality report
```

The old feature-manifest, quality-ranker, baseline recommendation, and surrogate
optimizer paths are not primary architecture.

## Non-Negotiable Rules

1. Do not claim success from synthetic messages, mock ANSA, placeholder meshes, or
   baseline/reference selection.
2. Do not hide model weakness with a baseline guard or deterministic rule fallback.
3. Defeaturing is out of scope for the next architecture. Assume clean CAD and preserve
   geometric boundaries.
4. The primary ANSA payload is a mesh sizing field: global size policy, user-adjustable
   global growth rate, per-edge target size, and optional per-face target size.
5. Graph inputs must not contain target mesh-size labels, target actions, quality
   labels, or reference midsurface artifacts.
6. AMG code must not import CDF code. CDF and AMG communicate through versioned files.
7. ANSA API imports may appear only inside ANSA script directories.
8. A task is complete only when its acceptance evidence is real, measurable, and
   recorded.

## Current Source Of Truth

Read these files before work:

```text
docs/STATUS.md
docs/TASKS.md
docs/ARCHITECTURE.md
docs/AMG.md
docs/CDF.md
docs/CONTRACTS.md
docs/ANSA_INTEGRATION.md
docs/DATASET.md
docs/TESTING.md
```

`docs/NEXT_AGENT_PROMPT.md` is the rolling handoff for the next task.

## Work Style

- Prefer deleting obsolete design language over preserving compatibility with an
  abandoned direction.
- Keep code paths fail-closed. If a metric cannot be measured, record `BLOCKED` or
  `metric_unavailable`; do not fabricate a zero error.
- Use real ANSA evidence for meshing claims.
- Keep iteration fast: small, diverse datasets first; scale only after the learning
  signal is proven.
- When a user choice is needed, present concrete options with consequences.

## Done Report Template

End each coding task with:

```text
completed task IDs
changed files
test commands and results
real gate commands and results, if any
next task
blockers or risks
```
