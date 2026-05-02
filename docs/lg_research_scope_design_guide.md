# LG AI Mesh Automation Scope And Design Guide

This document narrows the repository scope to the LG Electronics research request
shown by the user-provided project brief. It should be used as the practical
design guide when implementation choices conflict with broader, general-purpose
CAE meshing ideas.

## 1. Problem Definition

The target problem is AI-based automation of CAE shell mesh generation for 3D
CAE full-assembly structural analysis workflows.

The core bottleneck is not generic CFD meshing or arbitrary multiphysics mesh
generation. The bottleneck is that full assembly analysis takes weeks, and mesh
work consumes a large share of the schedule and engineering effort. Repeated CAD
changes make manual mesh rework a neck point for future analysis automation.

The requested tool should:

1. Preprocess paired CAD and mesh data.
2. Select and train an appropriate AI model.
3. Learn CAD-to-mesh patterns from existing CAD/Mesh examples.
4. Generate a mesh automatically when a CAD file is provided.
5. Reduce manual mesh work while preserving acceptable CAE mesh quality.

The research brief defines the mesh completion KPI as:

- Baseline: 100% manual mesh completion.
- Target: 70% automatic mesh completion.

This means the near-term system is not required to replace every manual meshing
decision. The intended target is an AI-assisted automation tool that completes a
large portion of repetitive mesh work and exposes the remaining manual-review
regions clearly.

## 2. Product Roadmap Scope

### 2026 Target: Constant-Thickness Sheet-Metal Parts

Primary target:

- Single parts or simple assemblies made of constant-thickness sheet-metal-like
  components.
- Shell mesh generation.
- Uniform thickness assignment per part or per simple region.
- ANSA Batch Mesh Manager recipe automation.

Examples:

- Control box style parts.
- Brackets, covers, panels, simple housings.

Required model behavior:

- Detect shell-mesh-suitable parts.
- Preserve important boundaries and holes.
- Predict mesh size field.
- Assign shell property and thickness.
- Generate BDF shell mesh with valid material/property references.
- Report regions that need manual cleanup or review.

### 2027 Target: Variable-Thickness Injection-Molded Assemblies

Second-stage target:

- Assemblies containing variable-thickness molded plastic parts.
- Shell mesh generation with multiple thickness regions.
- Thickness/color/region-aware property assignment.
- Assembly-level connection handling.

Examples:

- Base indoor assemblies.
- Plastic bases, covers, ribs, bosses, mounts, and mixed-thickness regions.

Required model behavior:

- Segment thickness regions.
- Assign separate PSHELL/PID regions for different thickness values.
- Preserve ribs, bosses, screw mounts, boundary conditions, and load paths.
- Generate connector candidates where structural connections are needed.
- Report uncertain regions instead of hiding failures.

## 3. Explicitly Out Of Scope For This Research Direction

The following are not primary goals unless explicitly requested later:

- General CFD volume mesh generation.
- Air-flow domain extraction.
- Boundary-layer prism mesh generation for fluid analysis.
- Universal arbitrary solid tetra meshing for every CAD part.
- Fully automatic semantic interpretation of all engineering intent from CAD
  geometry alone.
- Cosmetic-detail-perfect meshing of logos, tiny fillets, labels, and screw
  threads.

CAD parts must not be silently omitted. If a part is present in CAD, it must be
represented as explicit mesh, connector, mass, approved-exclude, or
manual-review/failure. The default is explicit mesh. Fasteners are not excluded
by default; connector or mass representations require explicit engineering
intent or acceptance metadata.

The current code may contain solid tetra and connector capabilities because they
are useful for validation and broader CAE integration, but the LG request should
steer future development toward structural shell meshing automation for
sheet-metal and molded-plastic parts.

## 4. Input CAD Requirements

Preferred CAD input:

- STEP AP242 B-Rep assembly.
- Units in millimeters.
- Product tree and part names preserved.
- One engineering part per CAD product/body where possible.
- Valid solid or sheet body topology that ANSA/OpenCascade can import.
- No descriptor-only, tessellated-only, or mesh-only geometry.

Helpful optional metadata:

- Nominal thickness by part.
- Thickness region information for variable-thickness plastic parts.
- Existing manual mesh for supervised training.
- Named sets for loads, constraints, contact, preserved holes, and critical
  boundaries.
- Part classification such as sheet metal, molded plastic, fastener, mass-only,
  approved-exclude, or manual review.

The minimum real training submission is:

```text
cad/raw.step
ansa/final.ansa
metadata/acceptance.csv
metadata/quality_criteria.yaml
```

`solver/final.bdf` and `reports/ansa_quality_report.*` are useful but optional
because the pipeline can export them from ANSA when the license and batch
environment are available.

## 5. CAD Cleanup Expectations

Clean CAD is strongly preferred. Automatic cleanup should be treated as a
limited robustness layer, not as a replacement for engineering CAD preparation.

The automation can reasonably attempt to handle:

- Small cracks or tolerable sewing gaps.
- Duplicate or tiny sliver faces that ANSA can heal.
- Collapsed or needle faces that do not encode important design intent.
- Minor overlaps that can be repaired without changing analysis meaning.

The automation should not silently hide:

- Large open shells where a shell/solid interpretation is ambiguous.
- Non-manifold topology.
- Self-intersections.
- Missing or broken product structure.
- Severe part overlap.
- Thin features whose purpose cannot be inferred.
- Gaps that may be intentional clearance or sealing features.
- Areas where a human must decide whether to defeature, preserve, or connect.

When cleanup is uncertain, the correct behavior is to emit a failed or
manual-review region, not to force a fake pass.

## 6. AI Model Scope

The AI model should be trained and evaluated on CAD/Mesh pairs that match the LG
target classes.

The model should predict:

- Mesh representation: shell, mass-only, connector, approved-exclude, manual review.
- Mesh size field.
- Feature preservation or defeature decisions.
- Thickness assignment or thickness region class.
- Boundary preservation flags.
- Connection candidates.
- Failure risk and repair action candidates.

For 2026, model quality should be measured primarily on constant-thickness shell
mesh automation. For 2027, model quality should expand to variable-thickness
region segmentation and assembly connection automation.

Synthetic data is useful for bootstrapping, but production claims require
validation on real LG CAD/Mesh examples.

Young's modulus, density, and Poisson ratio are not required inputs for the mesh
automation training dataset unless solver-ready BDF export is explicitly in
scope. Shell thickness and shell quality criteria are required because they
define whether a shell mesh is a valid structural FE representation.

## 7. Mesh Output Requirements

Primary output:

- Nastran BDF shell mesh.
- GRID, CQUAD4/CTRIA3 shell elements.
- PSHELL properties with correct thickness.
- MAT1 material references.
- Connector elements only where structurally meaningful.
- CAD-to-mesh mapping.
- QA metrics and failed/manual-review region reports.

Quality reports should include:

- Missing property/material/node counts.
- Element quality statistics.
- Free edges and unmeshed regions.
- Thickness assignment coverage.
- Boundary preservation coverage.
- Manual review list.

For this LG scope, shell mesh quality and thickness/property correctness are
more important than maximizing native solid tetra count.

If the workflow only targets mesh automation, physical material constants can be
left for downstream analysis setup. The mesh workflow should still preserve
property and thickness traceability.

## 8. Human-In-The-Loop Target

The near-term system should minimize human work, not pretend to remove all human
judgment.

Recommended workflow:

1. Import STEP AP242 assembly.
2. Extract B-Rep topology and part metadata.
3. Predict mesh recipe with AI.
4. Run ANSA Batch Mesh Manager.
5. Validate BDF and QA metrics.
6. Report pass/fail/manual-review regions.
7. Allow a human engineer to approve or correct only the uncertain regions.

This aligns with the research KPI of 70% automatic mesh completion and reduces
manual work without hiding quality or geometry problems.

## 9. Current Repository Status Relative To This Scope

Implemented:

- STEP AP242 B-Rep import and topology extraction through CadQuery/OCP.
- Heterogeneous graph construction from part, face, edge, contact candidate, and
  connection nodes.
- PyTorch heterogeneous graph neural network.
- ANSA Batch Mesh Manager backend adapter.
- BDF validation.
- BDF material/property/source-part traceability validation.
- Regression scripts and reports.

Still needing LG-specific production development:

- Training on real LG CAD/Mesh pairs.
- Constant-thickness sheet-metal specific labels and metrics.
- Variable-thickness plastic region segmentation.
- Shell mesh quality metrics focused on LG CAE standards.
- Thickness-region-aware PSHELL/PID generation.
- Robust manual-review visualization for failed or uncertain regions.
- Pilot validation on real air-conditioner assemblies.

The current synthetic 1,000-sample dataset is a bootstrap/dev dataset, not proof
that a real LG air-conditioner CAD can be meshed with production quality.

## 10. Implementation Priority From This Point

Future implementation should prioritize:

1. Real LG STEP and existing manual mesh ingestion.
2. Shell mesh dataset schema for constant-thickness sheet-metal parts.
3. AI label generation from manual mesh examples.
4. Shell mesh recipe prediction and ANSA shell recipe application.
5. Thickness/property traceability and QA.
6. Manual-review region packaging.
7. Variable-thickness plastic assembly support.

Solid tetra and generic CAE features should remain secondary unless they support
the shell mesh automation objective above.
