# Print Optimization Plan

## Status

- Date: 2026-03-02
- Version: 2.1
- Scope: MashCAD V1-aligned implementation plan
- Supersedes: prior draft "Vollstaendiger Implementierungsplan"
- Status: Ready for Execution

---

## Executive Summary

V1 Goal: Deliver a working print-orientation recommendation system that:
- evaluates geometric printability risks
- recommends better orientations with explanations
- can generate removable support fins for critical regions
- integrates into export workflow
- stays within performance budgets
- builds on existing code only

**Time estimate:** 12-15 working days

---

## What Changed (V2.0 → V2.1)

1. Added concrete time estimates for each AP
2. Defined corpus test files explicitly
3. Tightened performance budgets with examples
4. Added detailed deliverable definitions
5. Specified exact API boundaries

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
4. generate deterministic support fins for selected critical regions,
5. integrate into export trust and viewport feedback,
6. remain deterministic, testable, and fast enough for normal part sizes.

This is a V1 engineering goal, not a research simulator.

---

## Non-Goals For V1

These are explicitly out of scope for the first production version:

1. Full thermo-mechanical warping simulation
2. Layer-by-layer dynamic stability simulation
3. physics-optimized or fully automatic fin synthesis without user confirmation
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
4. deterministic support fin generation
5. orientation recommendation UX
6. viewport overlay for print-quality diagnostics
7. regression corpus for print optimization decisions

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
  print_fin_generator.py         # new: deterministic support fin synthesis

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
6. Critical unsupported regions can be converted into support fin proposals
7. UI shows recommendation, fin preview, and optional overlay
8. Export preflight can reuse the same analysis results

---

## V1 Work Packages

## Phase 0: Scope Lock And Baseline

**Time: 0.5 day**

### Deliverables

1. Scope document (this plan, approved)
2. Reference corpus test files
3. Performance budget definition
4. Explanation schema definition

### Tasks

| Task | Owner | Estimate |
|------|-------|----------|
| Create corpus test directory | TBD | 1h |
| Generate 8 reference CAD files | TBD | 2h |
| Define performance budget | TBD | 1h |
| Document explanation schema | TBD | 1h |

### Reference Corpus Files

All files to be created in `test/corpus/print_orientation/`:

```python
# corpus_parts.py
"""
Reference test parts for print orientation validation.
Each part is a simple Build123d construction.
"""

def get_corpus_parts() -> dict:
    return {
        'cube': make_cube(20),                    # 20mm cube
        'flat_plate': make_plate(100, 100, 5),     # 100x100x5mm
        'bridge': make_bridge_sample(60, 10, 20),   # Span, width, height
        'arch': make_arch(50, 25, 5),               # Width, height, thickness
        'tall_tower': make_cylinder(8, 60),         # 8mm diameter, 60mm height
        'l_bracket': make_l_bracket(40, 30, 5),     # Simple L-bracket
        'mech_part': make_holey_part(30),           # Part with holes
        'fillet_part': make_fillet_cube(15)          # Cube with rounded edges
    }
```

**Each part must:**
- Be constructible in <1 second
- Be exportable to STL without errors
- Have known "good" and "bad" orientations

### Performance Budget

For a typical part (5000 faces, 20mm bounding box):

| Operation | Budget | Notes |
|-----------|--------|-------|
| Base printability analysis | <300ms | Existing modules |
| Bridge classification | <100ms | New, simple heuristics |
| Support estimation | <200ms | Face iteration only |
| Candidate generation | <50ms | Max ~20 candidates |
| Candidate scoring | <1s | All candidates serial |
| **Total recommendation** | **<2s** | **Hard limit** |

Budget enforcement:
- Add timing decorators to all analysis functions
- Fail with clear error if budget exceeded
- Log actual timings for corpus monitoring

---

## Phase 1: Deterministic Geometry Analysis

**Time: 2-3 days**

### AP 1.1: Extend Printability Metrics

**File:** [modeling/printability_score.py](modeling/printability_score.py) (extend)

**Time:** 4 hours

**Add to `PrintabilityScore` class:**

```python
@dataclass
class OrientationMetrics:
    """Metrics that depend on orientation."""
    overhang_area_mm2: float = 0.0
    overhang_ratio: float = 0.0          # overhang / total surface
    unsupported_span_mm: float = 0.0      # max unsupported distance
    support_contact_area_mm2: float = 0.0
    base_contact_area_mm2: float = 0.0
    base_contact_ratio: float = 0.0       # convex hull footprint ratio
    build_height_mm: float = 0.0

    def to_dict(self) -> dict:
        """Serializable for caching/UI."""
        return asdict(self)
```

**Changes to existing score computation:**
- Extract raw overhang area (not just 0-100 score)
- Compute bounding box height
- Compute base footprint (projection on XY plane)

**Deliverable:** Extended `PrintabilityScore` with raw metrics

---

### AP 1.2: Bridge-Aware Classification

**File:** [modeling/print_bridge_analysis.py](modeling/print_bridge_analysis.py) (new)

**Time:** 6 hours

**Simple bridge detection algorithm:**

```python
def classify_bridge_faces(mesh, critical_angle=45) -> dict:
    """
    Returns dict mapping face_index -> BridgeClassification

    Bridge criteria (conservative):
    - Face normal is within 15° of horizontal
    - Face has at least 2 supporting edges
    - Supporting edges connect to vertical geometry below
    - Span < 50mm (configurable per material)
    """
    result = {}

    for face_idx, face in enumerate(mesh.faces):
        normal = face.normal
        angle_to_vertical = angle_between(normal, [0, 0, 1])

        if angle_to_vertical < 15:  # Nearly horizontal
            supports = count_vertical_supports_below(face, mesh)
            if supports >= 2:
                span = compute_face_span(face)
                if span < get_max_bridge_span(material):
                    result[face_idx] = BridgeClassification(
                        is_bridge=True,
                        span=span,
                        support_count=supports
                    )

    return result
```

**Deliverable:** `BridgeClassifier` class with `classify()` method

---

### AP 1.3: Support Estimation

**File:** [modeling/print_support_estimator.py](modeling/print_support_estimator.py) (new)

**Time:** 6 hours

**Deterministic heuristic (no simulation):**

```python
def estimate_support(body: Body, orientation: Rotation) -> SupportEstimate:
    """
    Estimate support requirements without simulation.

    For each face with downward-facing component:
    - If angle > critical_angle: needs support
    - Support volume = face_area × (face_height_above_bed)
    - Support difficulty = based on height and accessibility
    """
    total_support_volume = 0.0
    support_faces = []

    for face in body.faces:
        angle = face_angle_to_vertical(face)
        if angle < critical_angle:  # Faces facing down
            # Check if supported from below
            if not has_support_below(face, body):
                support_faces.append(face)
                height = get_face_z_height(face)
                volume = face.area * height
                total_support_volume += volume

    # Difficulty: higher support = more difficult
    difficulty = compute_support_difficulty(support_faces)

    return SupportEstimate(
        volume_mm3=total_support_volume,
        face_count=len(support_faces),
        difficulty=difficulty  # 0-1 scale
    )
```

**Deliverable:** `SupportEstimator` class

---

### AP 1.4: Support Fin Generation

**File:** [modeling/print_fin_generator.py](modeling/print_fin_generator.py) (new)

**Time:** 8 hours

**V1 scope:**

- deterministic fin generation only
- collision-safe against the source body
- driven by unsupported regions from support estimation
- explicit user preview and confirmation before apply

**Fin rules:**

1. fin root must land on build plane
2. fin must touch or closely support the target region
3. fin must not intersect the source body except at intended contact zone
4. fin geometry must be removable and low-complexity
5. fin count must be bounded

**Suggested output model:**

```python
@dataclass
class FinProposal:
    base_segment: tuple
    target_region_id: str
    height_mm: float
    thickness_mm: float
    clearance_mm: float
    estimated_support_gain: float

@dataclass
class FinGenerationResult:
    fins: list[FinProposal]
    skipped_regions: list[str]
    notes: list[str]
```

**Deliverable:** `SupportFinGenerator` class with previewable fin proposals

---

### Phase 1 Acceptance Criteria

- [ ] `OrientationMetrics` can be computed for all corpus parts
- [ ] Bridge classification correctly identifies simple bridges
- [ ] Support estimate is deterministic (±0.1% variance)
- [ ] Fin proposals are generated for eligible unsupported corpus regions
- [ ] Fin proposals are collision-checked and bounded
- [ ] All analyses complete within 600ms per part
- [ ] No new dependencies added

---

## Phase 2: Orientation Recommendation

**Time: 3-4 days**

### AP 2.1: Candidate Generation

**File:** [modeling/print_orientation.py](modeling/print_orientation.py) (new)

**Time:** 8 hours

**Bounded candidate set (NOT brute force):**

```python
def generate_candidates(body: Body) -> List[OrientationCandidate]:
    """
    Generate ~10-20 orientation candidates, not thousands.
    """
    candidates = []

    # 1. Try each face pointing down (6 candidates)
    for face in body.faces:
        if face.area > 100:  # Only significant faces
            candidates.append(face_down_orientation(face))

    # 2. Try axis-aligned rotations (3 candidates)
    for axis in [[1,0,0], [0,1,0], [0,0,1]]:
        candidates.append(axis_aligned_orientation(axis))

    # 3. Try 45° rotations for best candidates only
    top_3 = sorted(candidates, key=score)[:3]
    for base in top_3:
        candidates.append(rotation_45(base))

    return deduplicate(candidates)
```

**Candidate count target: 10-20**

---

### AP 2.2: Candidate Ranking

**Time:** 8 hours

**Scoring function (explicit, not ML):**

```python
def score_candidate(candidate: OrientationCandidate,
                   metrics: OrientationMetrics) -> float:
    """
    Weighted heuristic - all weights visible and user-editable.
    """
    # Default weights (can be overridden)
    W_OVERHANG = 0.35
    W_SUPPORT = 0.30
    W_HEIGHT = 0.15
    W_STABILITY = 0.15
    W_BRIDGE = 0.05

    # Normalize metrics (0-1 scale)
    overhang_penalty = metrics.overhang_ratio
    support_penalty = normalize(metrics.support_volume, 0, 50000)
    height_penalty = normalize(metrics.build_height_mm, 0, 200)
    stability_bonus = metrics.base_contact_ratio
    bridge_bonus = bridge_friendliness_score(metrics)

    score = (
        W_OVERHANG * overhang_penalty +
        W_SUPPORT * support_penalty +
        W_HEIGHT * height_penalty +
        W_STABILITY * (1.0 - stability_bonus) +
        W_BRIDGE * (1.0 - bridge_bonus)
    )

    return score
```

**Deliverable:** `OrientationRanker` class

---

### AP 2.3: Recommendation Output

**Time:** 4 hours

**Result structure:**

```python
@dataclass
class OrientationRecommendation:
    """Result of orientation optimization."""
    best: OrientationCandidate
    alternatives: List[OrientationCandidate]  # Top 3

    # Explanation of WHY best is best
    metrics_before: OrientationMetrics
    metrics_after: OrientationMetrics
    improvements: List[str]  # Human-readable

    # For UI display
    comparison_table: dict  # metric_name -> (before, after)
```

**Improvement strings template:**

```python
# Generated from metric deltas:
- f"Reduces support volume by {delta:.0f}%"
- f"Larger base contact ({before.area} → {after.area} mm²)"
- f"Taller by {delta_height} mm (affects print time)"
```

**Deliverable:** `OrientationRecommendation` dataclass

---

### AP 2.4: Fin Recommendation Integration

**Time:** 4 hours

Combine orientation ranking and fin generation into one recommendation result:

```python
@dataclass
class PrintOptimizationRecommendation:
    orientation: OrientationRecommendation
    fin_result: FinGenerationResult | None
    rationale: list[str]
```

Rules:

1. prefer orientation improvement before adding fins
2. propose fins only where orientation alone does not sufficiently mitigate risk
3. explain why fins are proposed

**Deliverable:** unified recommendation object for UI and export handoff

---

### Phase 2 Acceptance Criteria

- [ ] Candidate generation produces 10-20 orientations
- [ ] Ranking is deterministic (same input = same order)
- [ ] All corpus parts get reasonable recommendations
- [ ] Explanation text accurately reflects computed metrics
- [ ] Fin proposals are attached only when justified by remaining unsupported risk
- [ ] Total analysis time < 2s per part

---

## Phase 3: UI Integration

**Time: 2-3 days**

### AP 3.1: Print Optimize Dialog

**File:** [gui/dialogs/print_optimize_dialog.py](gui/dialogs/print_optimize_dialog.py) (new)

**Time:** 10 hours

**Minimal V1 dialog:**

```
┌─────────────────────────────────────┐
│  Optimize for 3D Printing            │
├─────────────────────────────────────┤
│  Body: [Current_Body ▼]             │
│  Material: [PLA ▼]                   │
│                                      │
│  [Analyze]                           │
│                                      │
│  ── Results ──────────────────────  │
│  Recommended: Face-3 Down            │
│                                      │
│  Before → After:                     │
│  Supports: 8500 mm³ → 1200 mm³       │
│  Overhang: 23% → 8%                  │
│  Height: 45mm → 67mm                  │
│                                      │
│  [Preview] [Apply Orientation]        │
│  [Generate Fins] [Apply Fins] [Cancel]│
└─────────────────────────────────────┘
```

**Minimal features:**
- Body selector (default: current active body)
- Material preset (PLA, ABS, PETG) - affects bridge span only
- Single "Analyze" button
- Results table (before/after comparison)
- Preview orientation in viewport
- Apply orientation → adds TransformFeature
- Generate fins → previews fin solids/overlays
- Apply fins → creates actual support-fin feature(s) on user confirmation

**Deliverable:** Working dialog

---

### AP 3.2: Viewport Overlay

**File:** [gui/viewport/print_quality_overlay.py](gui/viewport/print_quality_overlay.py) (new)

**Time:** 6 hours

**Simple color-coded overlay:**

```python
def show_printability_overlay(viewport, body):
    """
    Adds scalar bar showing overhang risk.
    """
    mesh = body.vtk_mesh

    # Compute overhang angle per face
    overhang_angles = compute_overhang_angles(mesh)

    # Add to mesh as cell data
    mesh.cell_data['Overhang'] = overhang_angles

    # Color map: Green (OK) → Yellow → Red (Bad)
    viewport.plotter.add_mesh(
        mesh,
        scalars='Overhang',
        cmap='RdYlGn_r',
        clim=[0, 45]  # 0° = green, 45° = red
        show_edges=False
    )

    # Scalar bar
    viewport.plotter.add_scalar_bar(
        title="Overhang Angle",
        n_labels=5
    )
```

**Deliverable:** Toggleable overlay mode

---

### Phase 3 Acceptance Criteria

- [ ] Dialog opens and closes cleanly
- [ ] Analysis runs on background thread
- [ ] Results are shown (no empty state)
- [ ] Apply orientation creates undo-able TransformFeature
- [ ] Apply fins creates undo-able fin feature(s)
- [ ] Cancel removes fin previews and temporary overlays
- [ ] Overlay can be toggled on/off
- [ ] Overlay cleanup is 100% reliable

---

## Phase 4: Export Trust Integration

**Time: 1 day**

### AP 4.1: Reuse In Export Controller

**File:** [gui/export_controller.py](gui/export_controller.py) (extend)

**Time:** 4 hours

**Changes:**

```python
# In ExportController.export_stl()
if not printability_gate.check(body):
    # NEW: Show rich explanation
    show_printability_warning(
        body,
        suggestion="Try 'Optimize for 3D Printing' for orientation tips"
    )
```

**Cache reuse:**

```python
# Store last analysis result
_last_analysis_cache: dict = {}

def get_or_analyze(body) -> PrintabilityScore:
    body_key = (body.id, body._solid_generation)
    if body_key in _last_analysis_cache:
        return _last_analysis_cache[body_key]
    # ... compute and cache
```

**Deliverable:** Warning dialog with "Optimize" button

---

### Phase 4 Acceptance Criteria

- [ ] Export warnings mention print optimization
- [ ] "Optimize" button opens the dialog
- [ ] Export warnings can reference fin generation where relevant
- [ ] Same analysis is reused, not recomputed

---

## Phase 5: Validation And Regression Protection

**Time: 2-3 days**

### Test Files to Create

| File | Tests | Time |
|------|-------|------|
| `test/test_print_bridge_analysis.py` | Bridge detection, span computation | 3h |
| `test/test_print_support_estimator.py` | Volume estimation, determinism | 2h |
| `test/test_print_fin_generator.py` | Fin generation, collision checks | 3h |
| `test/test_print_orientation.py` | Candidate generation, ranking | 4h |
| `test/test_print_optimize_dialog.py` | UI workflow, fin apply flow | 3h |
| `test/test_print_quality_overlay.py` | Overlay toggle, cleanup | 2h |
| `test/test_export_print_optimization_integration.py` | End-to-end | 3h |

### Corpus Tests

For each corpus part, define expected results:

```python
# test/corpus/test_corpus_recommendations.py

CORPUS_EXPECTATIONS = {
    'cube': [
        'all orientations are equivalent',
        'no support needed',
    ],
    'flat_plate': [
        'flat_down is recommended',
        'edge_down is worst (tipping risk)',
    ],
    'bridge': [
        'bridge is recognized (not overhang)',
        'orientation that puts bridge on top is preferred',
    ],
    'tall_tower': [
        'lying_down is recommended (stability)',
        'standing_up has lowest stability score',
    ],
}
```

---

### Phase 5 Acceptance Criteria

- [ ] All 7 test files exist and pass
- [ ] Corpus tests produce documented results
- [ ] Running full test suite takes < 30s
- [ ] No test skip decorators in print optimization paths
- [ ] Determinism test proves same input = same ranking

---

## Implementation Timeline

| Phase | Tasks | Time |
|-------|-------|------|
| Phase 0 | Corpus, budgets, schema | 0.5 day |
| Phase 1 | Metrics, bridge, support, fin generation | 3.5 days |
| Phase 2 | Candidates, ranking, output | 3.5 days |
| Phase 3 | Dialog, overlay, fin apply flow | 2.5 days |
| Phase 4 | Export integration | 1 day |
| Phase 5 | Tests, validation | 2.5 days |
| **Buffer** | Unexpected issues, fixes | 1-2 days |
| **Total** | | **14-15 days** |

**Milestone definition:**
- Day 3: Phase 0-1 complete (core analysis working)
- Day 7: Phase 2 complete (recommendations + fin proposals working)
- Day 10: Phase 3 complete (UI functional)
- Day 15: All tests passing

---

## Performance Budget

V1 needs bounded, believable targets.

Suggested budgets for normal single-body parts:

1. base printability analysis: under 500 ms
2. orientation recommendation on bounded candidate set: under 2 s
3. fin proposal generation: under 500 ms
4. overlay refresh: debounced and non-blocking

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

### Risk 5: Fin generation creates bad or colliding geometry

Mitigation:

- strict collision checks against body
- bounded fin templates only
- preview-before-apply
- regression tests on corpus parts

---

## Implementation Order

1. scope lock and corpus
2. extend printability metrics
3. bridge-aware classification
4. support estimation
5. fin generation
6. orientation candidate generation
7. orientation ranking
8. dialog
9. overlay
10. export integration
11. regression suite and budgets

This order matters. Do not start with UI chrome or post-V1 simulation modules.

---

## Definition Of Done

The print optimization feature is complete for V1 when:

### Functional Requirements
- [ ] System recommends orientations for all corpus parts
- [ ] Recommendations are verifiable (can see why it chose that orientation)
- [ ] Bridge samples are NOT penalized like overhangs
- [ ] System can generate support fins for eligible unsupported regions
- [ ] Export warnings link to optimization dialog

### Quality Requirements
- [ ] All 7 test files exist and pass
- [ ] Determinism test proves reproducibility
- [ ] Performance budgets met on all corpus parts
- [ ] UI is responsive (no freeze > 2s on corpus parts)

### Integration Requirements
- [ ] Adds TransformFeature when "Apply" clicked
- [ ] Adds fin feature(s) when "Apply Fins" clicked
- [ ] Undo/redo works for orientation changes
- [ ] Undo/redo works for fin application
- [ ] Overlay cleanup is 100% reliable
- [ ] Export preflight uses same analysis

### Negative Definition Of Done
The following are NOT required for V1:

- Perfection (recommendations just need to be "better", not optimal)
- Coverage of all edge cases (corpus coverage is sufficient)
- Advanced features (thermal sim, Pareto UI, physics-based fin optimization) → post-V1

---

## Risk Register

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| Performance budgets exceeded | High | Reduce candidate count before adding more analysis | Open |
| Bridge detection fails on real parts | Medium | Conservative detection (false negatives OK) | Open |
| Orientation recommendations are "obviously wrong" | Medium | User feedback, manual corpus review | Open |
| Fin generation collides or produces unusable geometry | High | Collision checks, bounded templates, preview-before-apply | Open |
| Overlay doesn't clean up | High | Strict test, never exit without cleanup | Open |
| Export dialog conflicts with optimize dialog | Low | Single source of truth (shared cache) | Open |

---

## Handoff Checklist

Before starting implementation:

- [ ] Plan approved by stakeholder
- [ ] Time allocation confirmed (12-14 days)
- [ ] Existing printability modules reviewed
- [ ] Test infrastructure verified

Before declaring V1 complete:

- [ ] All acceptance criteria met
- [ ] Performance budgets validated on corpus
- [ ] User tested on at least 3 real parts
- [ ] Documentation updated

---

## Post-V1 Backlog

These items may be revisited later:

1. thermal warping estimator
2. dynamic stability over build time
3. Pareto-front UI
4. printer-profile-specific scoring
5. material database expansion

They should be separate design documents, not hidden inside the V1 plan.
