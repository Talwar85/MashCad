# Print Optimization Plan

## Status

- Date: 2026-03-02
- Version: 2.0
- Scope: MashCAD V1-aligned implementation plan
- Supersedes: prior draft "Vollstaendiger Implementierungsplan"

---

## Executive Feedback

The previous plan was not suitable as a V1 execution plan.

Main issues:

1. It was too research-heavy for a production-readiness phase.
2. It introduced too many new subsystems before proving value with existing code.
3. It was weakly connected to the current MashCAD codebase.
4. It mixed "interesting future work" with "must ship for V1".
5. It lacked hard acceptance criteria and release gates.
6. It proposed dependencies and parallel execution paths without proving they are necessary or safe.

Conclusion:

- Keep print optimization, but reduce V1 scope to deterministic geometric analysis and orientation recommendation.
- Move thermal simulation, dynamic print simulation, fin synthesis, and full Pareto research to post-V1 backlog.

---

## Alignment With Canonical V1 Plan

This plan is subordinate to:

- [plans/PRODUCTION_READINESS_PLAN.md](plans/PRODUCTION_READINESS_PLAN.md)

Primary V1 target:

- Gate G4: Printability and Export Trust

Supporting constraints:

1. OCP-first only.
2. No silent fallbacks.
3. No UI-blocking long-running work on the main interaction path.
4. No new physics claims without validation corpus.
5. No ProcessPool or background OCP kernel execution.

---

## V1 Goal

Deliver a print-optimization workflow that can:

1. evaluate printability-relevant geometric risks for a body,
2. recommend a better print orientation,
3. explain the recommendation in concrete metrics,
4. integrate into export trust and viewport feedback,
5. remain deterministic, testable, and fast enough for normal part sizes.

This is a V1 engineering goal, not a research simulator.

---

## Non-Goals For V1

These are explicitly out of scope for the first production version:

1. Full thermo-mechanical warping simulation
2. Layer-by-layer dynamic stability simulation
3. Auto-generated stabilization fins
4. Full Pareto-front optimization UI
5. ML-based ranking
6. ProcessPool-based geometric evaluation
7. Multi-material or printer-farm specific optimization

If later needed, they belong in a separate post-V1 roadmap.

---

## Current Codebase Reality

The plan must build on what already exists:

Existing relevant modules:

- [modeling/printability_gate.py](modeling/printability_gate.py)
- [modeling/printability_score.py](modeling/printability_score.py)
- [modeling/export_validator.py](modeling/export_validator.py)
- [modeling/wall_thickness_analyzer.py](modeling/wall_thickness_analyzer.py)
- [gui/export_controller.py](gui/export_controller.py)

What already exists today:

1. printability trust gate
2. scoring model for manifold, normals, wall thickness, overhang
3. export preflight integration
4. OCP geometry access

What is missing:

1. orientation candidate generation
2. support-volume estimation
3. bridge-aware overhang classification
4. orientation recommendation UX
5. viewport overlay for print-quality diagnostics
6. regression corpus for print optimization decisions

Therefore the right plan is extension and hardening, not subsystem explosion.

---

## V1 Architecture

### Module Strategy

Prefer extending existing printability modules and add only the minimum new packages:

```text
modeling/
  printability_score.py          # extend scoring inputs
  printability_gate.py           # keep as enforcement layer
  print_orientation.py           # new: candidate generation and ranking
  print_support_estimator.py     # new: deterministic support heuristics
  print_bridge_analysis.py       # new: bridge-aware face classification

gui/
  dialogs/print_optimize_dialog.py
  viewport/print_quality_overlay.py
```

Do not create thermal/, stability/, fins/, optimization/ package trees for V1.

### Data Flow

1. Body/shape enters analysis
2. Base printability metrics are computed
3. Orientation candidates are generated
4. Each candidate is scored with deterministic heuristics
5. Best candidates are ranked and explained
6. UI shows recommendation and optional overlay
7. Export preflight can reuse the same analysis results

---

## V1 Work Packages

## Phase 0: Scope Lock And Baseline

### Deliverables

1. lock V1 scope to deterministic geometric analysis only
2. define reference corpus of parts
3. define performance budget and response budget
4. define explanation schema for user-facing results

### Acceptance Criteria

1. no thermal or dynamic simulation code added
2. no new dependency introduced without direct implementation need
3. reference corpus committed
4. metric schema documented

### Suggested corpus

1. cube
2. flat plate
3. bridge sample
4. arch
5. tall narrow tower
6. L-bracket
7. hole-rich mechanical part
8. fillet-heavy organic-ish part

---

## Phase 1: Deterministic Geometry Analysis

### AP 1.1: Extend Printability Metrics

Target file:

- [modeling/printability_score.py](modeling/printability_score.py)

Add or tighten:

1. overhang area ratio
2. unsupported span estimate
3. support contact area estimate
4. base contact area / stability heuristic
5. build height penalty

Output must remain explicit and serializable.

### AP 1.2: Bridge-Aware Classification

New file:

- [modeling/print_bridge_analysis.py](modeling/print_bridge_analysis.py)

Purpose:

1. distinguish simple bridge cases from generic overhang
2. reduce false-positive support penalties
3. produce explanation objects, not only a boolean

Hard rule:

- this is geometric classification, not simulation

### AP 1.3: Support Estimation

New file:

- [modeling/print_support_estimator.py](modeling/print_support_estimator.py)

Purpose:

1. estimate support-requiring area
2. estimate support volume proxy
3. estimate support difficulty score

For V1 use deterministic heuristics from face angle, exposed underside area, and projected support height.

### Acceptance Criteria

1. all metrics are deterministic across repeated runs
2. corpus parts produce stable score outputs
3. bridge samples are not treated like generic overhang failures
4. performance stays within agreed budget on corpus parts

---

## Phase 2: Orientation Recommendation

### AP 2.1: Candidate Generation

New file:

- [modeling/print_orientation.py](modeling/print_orientation.py)

Generate a bounded candidate set:

1. major planar-face-down orientations
2. axis-aligned rotations
3. optional 45-degree derived candidates where geometrically justified

Do not brute-force the rotation space.

### AP 2.2: Candidate Ranking

Each candidate gets a score from:

1. overhang penalty
2. bridge adjustment
3. support estimate
4. build height
5. contact stability

Ranking model for V1:

- explicit weighted heuristic
- user-visible explanation
- no hidden ML

### AP 2.3: Recommendation Output

Return:

1. best candidate
2. top-N alternatives
3. metric breakdown
4. human-readable explanation strings

Example explanations:

1. "reduces support estimate by 34%"
2. "improves base contact area"
3. "increases build height by 12 mm"

### Acceptance Criteria

1. recommendations are reproducible
2. explanation matches computed metrics
3. corpus ranking is sensible and manually reviewable
4. no candidate evaluation requires unsafe threaded OCP work

---

## Phase 3: UI Integration

### AP 3.1: Print Optimize Dialog

New file:

- [gui/dialogs/print_optimize_dialog.py](gui/dialogs/print_optimize_dialog.py)

V1 dialog scope:

1. select body
2. choose material profile from a small preset list
3. run analysis
4. show top recommendations
5. preview chosen orientation
6. apply orientation

Do not build a dense research dashboard for V1.

### AP 3.2: Viewport Overlay

New file:

- [gui/viewport/print_quality_overlay.py](gui/viewport/print_quality_overlay.py)

Overlay scope:

1. highlight likely support-heavy regions
2. optionally show bridge regions
3. remain responsive
4. fully clear on cancel/close

### Acceptance Criteria

1. dialog does not block the app for normal corpus parts
2. overlay cleanup is correct on cancel and mode exit
3. recommendation apply path is undo/redo safe
4. export flow can consume the same analysis result without recomputing everything unnecessarily

---

## Phase 4: Export Trust Integration

### AP 4.1: Reuse In Export Controller

Existing file:

- [gui/export_controller.py](gui/export_controller.py)

Add:

1. richer explanation when printability gate warns or fails
2. optional recommendation handoff into print-optimization dialog
3. caching of recent analysis for same body/state

### Acceptance Criteria

1. export preflight and optimize dialog do not disagree on the same body state
2. warnings include actionable next steps
3. no duplicate analysis stack diverges

---

## Phase 5: Validation And Regression Protection

### Required Test Areas

1. metric correctness on corpus parts
2. bridge vs overhang classification
3. support estimate monotonicity
4. orientation ranking determinism
5. dialog workflow
6. overlay cleanup
7. export preflight consistency

### Suggested test files

```text
test/test_print_bridge_analysis.py
test/test_print_support_estimator.py
test/test_print_orientation.py
test/test_print_optimize_dialog.py
test/test_print_quality_overlay.py
test/test_export_print_optimization_integration.py
```

### Acceptance Criteria

1. no skips added for core print optimization paths
2. deterministic outputs in CI
3. corpus-based regression tests cover ranking and explanation

---

## Performance Budget

V1 needs bounded, believable targets.

Suggested budgets for normal single-body parts:

1. base printability analysis: under 500 ms
2. orientation recommendation on bounded candidate set: under 2 s
3. overlay refresh: debounced and non-blocking

If these are not met, reduce scope before adding more analysis complexity.

Do not add heavy dependencies to hide algorithmic inefficiency.

---

## Dependency Policy

Default stance: do not add new dependencies unless the implementation is already blocked without them.

For V1, prefer:

1. OCP
2. existing MashCAD math/geometry utilities
3. stdlib
4. existing PyVista integration

Not approved by default for V1:

1. numba
2. scikit-learn
3. trimesh
4. pyvistaqt

`scipy` may be used only if a concrete implementation step proves it is required and already aligned with existing environment constraints.

---

## Risks And Mitigations

### Risk 1: Plan grows back into a research project

Mitigation:

- keep non-goals explicit
- reject thermal/dynamic simulation in V1

### Risk 2: UI becomes slow or inconsistent

Mitigation:

- bounded candidate set
- cached results by body state
- overlay cleanup tests

### Risk 3: Print optimization disagrees with export trust gate

Mitigation:

- single analysis source of truth
- shared score objects

### Risk 4: False confidence from weak heuristics

Mitigation:

- show recommendation as heuristic guidance
- expose metric breakdown
- validate against corpus and selected real parts

---

## Implementation Order

1. scope lock and corpus
2. extend printability metrics
3. bridge-aware classification
4. support estimation
5. orientation candidate generation
6. orientation ranking
7. dialog
8. overlay
9. export integration
10. regression suite and budgets

This order matters. Do not start with UI chrome or post-V1 simulation modules.

---

## Definition Of Done

The print optimization plan is complete for V1 only when:

1. the system recommends improved orientations on the reference corpus,
2. explanations are concrete and reproducible,
3. export preflight and optimize dialog are consistent,
4. UI interaction remains stable and cancellable,
5. tests prove determinism and prevent regression,
6. no post-V1 research modules were quietly introduced into the critical path.

---

## Post-V1 Backlog

These items may be revisited later:

1. thermal warping estimator
2. dynamic stability over build time
3. support fin generation
4. Pareto-front UI
5. printer-profile-specific scoring
6. material database expansion

They should be separate design documents, not hidden inside the V1 plan.
