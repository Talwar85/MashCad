# MashCAD V1.0 - 4-Sprint Execution Plan

**Version:** 1.0  
**Created:** 2026-02-20  
**Branch:** feature/v1-roadmap-execution  
**Status:** Active Planning

---

## Executive Summary

This document defines the detailed 4-Sprint execution plan to deliver MashCAD V1.0. Each sprint is2 weeks and targets specific release gates from the quality model.

### Current Progress Status

| Package ID | Title | Status | Sprint |
|------------|-------|--------|--------|
| CI-001 | GitHub CI Gate Repair | ✅ COMPLETED | Pre-Sprint |
| PR-002 | Manifold/Free-Bounds Mandatory Check | ✅ COMPLETED | Pre-Sprint |
| PR-008 | STL/3MF Regression Corpus | ✅ COMPLETED | Pre-Sprint |
| PR-010 | Printability Trust Gate | ✅ COMPLETED | Pre-Sprint |
| PR-001 | Export Path Standardization (3MF) | 🔴 TODO | Sprint 1 |

### Gate Status Overview

| Gate | Target Sprint | Current Status |
|------|---------------|----------------|
| G0 - Baseline & Scope Lock | Pre-Sprint | ✅ PASS |
| G1 - Core Stability Recovery | Sprint 1 | 🟡 IN PROGRESS |
| G2 - Parametric Integrity | Sprint 2 | 🔴 NOT STARTED |
| G3 - Sketcher/UX Reliability | Sprint 2 | 🔴 NOT STARTED |
| G4 - Printability/Export Trust | Sprint 1 | 🟡 IN PROGRESS |
| G5 - Assembly V1 Readiness | Sprint 3 | 🔴 NOT STARTED |
| G6 - RC Burn-in | Sprint 4 | 🔴 NOT STARTED |

---

## Sprint 1: Core Hardening + Export Foundation (W36-37)

**Goal:** Complete G4 Printability Gate, fix remaining P0 items, establish export infrastructure

**Target Gates:** G1 (partial), G4 (complete)

### Week 36 Tasks

#### PR-001: Implement 3MF Export using lib3mf/py3mf
| Field | Value |
|-------|-------|
| **Package ID** | PR-001 |
| **Priority** | P0 |
| **Est. Effort** | 12 hours |
| **Dependencies** | PR-002 (completed) |

**Description:**
Implement standardized 3MF export path that uses the same validation gates as STL export.

**Detailed Tasks:**
- [ ] **PR-001.1:** Research lib3mf/py3mf integration options
  - Evaluate py3mf Python bindings vs direct lib3mf ctypes
  - Check conda-forge availability
  - Document API surface needed
- [ ] **PR-001.2:** Create `modeling/export_3mf.py` module
  - Implement `export_3mf(shape, path, **options)` function
  - Integrate with existing `ExportValidator` class
  - Add unit tests for basic export
- [ ] **PR-001.3:** Integrate 3MF into export service
  - Add 3MF to `ExportKernel` supported formats
  - Update GUI export dialogs
  - Add 3MF-specific options (units, compression)
- [ ] **PR-001.4:** Add 3MF to regression corpus
  - Generate 3MF golden exports for corpus models
  - Add delta comparison tests
- [ ] **PR-001.5:** Update documentation
  - Add 3MF export to user guide
  - Document limitations and workarounds

**Acceptance Criteria:**
- [ ] 3MF export produces valid files
- [ ] Same validation gates as STL (manifold, free-bounds)
- [ ] Slicer import test with PrusaSlicer/Cura
- [ ] Corpus tests include 3MF format

**Files to Modify:**
- `modeling/export_3mf.py` (new)
- `modeling/export_kernel.py`
- `gui/dialogs/stl_export_dialog.py` → rename to `export_dialog.py`
- `test/test_export_3mf.py` (new)

---

#### CH-006: OCP API Compatibility Validation
| Field | Value |
|-------|-------|
| **Package ID** | CH-006 |
| **Priority** | P0 |
| **Est. Effort** | 8 hours |
| **Dependencies** | CI-001 (completed) |

**Description:**
Ensure OCP (OpenCascade Python) API compatibility across supported versions and platforms.

**Detailed Tasks:**
- [ ] **CH-006.1:** Create OCP API compatibility test suite
  - Document all OCP APIs used in codebase
  - Create version-specific test cases
  - Add deprecation warnings detection
- [ ] **CH-006.2:** Implement compatibility layer
  - Create `modeling/ocp_compat.py` module
  - Add version detection and guards
  - Implement fallbacks for deprecated APIs
- [ ] **CH-006.3:** Add CI matrix testing
  - Test against OCP 7.x and 7.8.x
  - Add Windows/Linux compatibility checks
  - Document known incompatibilities
- [ ] **CH-006.4:** Update import patterns
  - Audit all OCP imports
  - Standardize import patterns
  - Add compatibility comments

**Acceptance Criteria:**
- [ ] No import failures on supported OCP versions
- [ ] Compatibility tests in CI matrix
- [ ] Documented API version requirements

**Files to Modify:**
- `modeling/ocp_compat.py` (new)
- `modeling/ocp_helpers.py`
- `test/test_ocp_compat.py` (new)
- `requirements.txt`

---

#### CH-008: Error Diagnostics UI Improvements
| Field | Value |
|-------|-------|
| **Package ID** | CH-008 |
| **Priority** | P1 |
| **Est. Effort** | 10 hours |
| **Dependencies** | CH-003 (error envelope) |

**Description:**
Improve error messages in UI to provide actionable feedback with clear next steps.

**Detailed Tasks:**
- [ ] **CH-008.1:** Audit current error messages
  - Catalog all user-facing error messages
  - Identify messages without clear action
  - Prioritize by frequency and impact
- [ ] **CH-008.2:** Design error message standard
  - Define template: [What happened] + [Why] + [Next step]
  - Create error code mapping
  - Design UI component for rich errors
- [ ] **CH-008.3:** Implement improved error dialogs
  - Update `ErrorDetailsDialog` component
  - Add "Copy to clipboard" and "Get help" buttons
  - Implement error code lookup system
- [ ] **CH-008.4:** Update core error paths
  - Modeling errors (extrude fail, boolean fail)
  - Export errors (invalid geometry, file write)
  - Sketch errors (solver fail, constraint conflict)

**Acceptance Criteria:**
- [ ] 90% of error messages contain concrete action
- [ ] Error code system implemented
- [ ] User tests confirm understandability

**Files to Modify:**
- `gui/dialogs/error_details_dialog.py`
- `modeling/error_diagnostics.py`
- `modeling/result_types.py`
- `i18n/en.json`, `i18n/de.json`

---

### Week 37 Tasks

#### QA-006: Performance Regression Gate
| Field | Value |
|-------|-------|
| **Package ID** | QA-006 |
| **Priority** | P1 |
| **Est. Effort** | 8 hours |
| **Dependencies** | SU-005 (drag performance) |

**Description:**
Implement performance benchmarks in CI to catch performance regressions.

**Detailed Tasks:**
- [ ] **QA-006.1:** Define performance budgets
  - Sketch drag latency: <16ms (60 FPS)
  - Extrude rebuild: <500ms for typical parts
  - Export time: <2s for 100k triangle mesh
  - Document budgets in `config/performance_budgets.py`
- [ ] **QA-006.2:** Create benchmark suite
  - Use pytest-benchmark framework
  - Create representative test models
  - Add timing assertions
- [ ] **QA-006.3:** Integrate with CI
  - Add benchmark step to CI workflow
  - Store historical results
  - Alert on budget violations
- [ ] **QA-006.4:** Create performance dashboard
  - Track trends over time
  - Visualize regression points
  - Document optimization opportunities

**Acceptance Criteria:**
- [ ] Budget violations block merge
- [ ] Historical tracking implemented
- [ ] Dashboard available for team

**Files to Modify:**
- `config/performance_budgets.py` (new)
- `test/benchmarks/` (new directory)
- `scripts/gate_performance.ps1` (new)
- `.github/workflows/gates.yml`

---

#### QA-007: Cross-Platform CI Matrix
| Field | Value |
|-------|-------|
| **Package ID** | QA-007 |
| **Priority** | P1 |
| **Est. Effort** | 6 hours |
| **Dependencies** | CH-006 (OCP compatibility) |

**Description:**
Extend CI to test on both Windows and Linux platforms.

**Detailed Tasks:**
- [ ] **QA-007.1:** Analyze platform-specific code
  - Identify Windows-specific paths
  - Document Linux compatibility gaps
  - Create platform abstraction layer
- [ ] **QA-007.2:** Update GitHub Actions workflow
  - Add matrix strategy for windows-latest, ubuntu-latest
  - Handle platform-specific test exclusions
  - Add platform badges to README
- [ ] **QA-007.3:** Fix platform-specific failures
  - Path handling (Path vs path separators)
  - Process spawning differences
  - Display/OpenGL handling
- [ ] **QA-007.4:** Document platform support matrix
  - Update README with supported platforms
  - Document known limitations per platform
  - Add troubleshooting guide

**Acceptance Criteria:**
- [ ] Core tests pass on Windows and Linux
- [ ] Platform-specific issues documented
- [ ] CI matrix shows both platforms

**Files to Modify:**
- `.github/workflows/gates.yml`
- `scripts/gate_core.ps1` (add Linux equivalent)
- `scripts/gate_core.sh` (new)
- `README.md`

---

#### G4 Gate Validation on Corpus
| Field | Value |
|-------|-------|
| **Package ID** | G4-VAL |
| **Priority** | P0 |
| **Est. Effort** | 4 hours |
| **Dependencies** | PR-001, PR-008, PR-010 |

**Description:**
Run full G4 (Printability/Export Trust) gate validation against the regression corpus.

**Detailed Tasks:**
- [ ] **G4-VAL.1:** Prepare corpus models
  - Verify all 20+ reference models are current
  - Generate golden exports for all formats
  - Document expected metrics per model
- [ ] **G4-VAL.2:** Run export preflight on all models
  - Execute manifold checks
  - Verify free-bounds detection
  - Test normals validation
- [ ] **G4-VAL.3:** Run slicer import tests
  - Import all exports in PrusaSlicer
  - Verify no repair needed
  - Document any warnings
- [ ] **G4-VAL.4:** Generate G4 evidence report
  - Compile all test results
  - Document pass/fail status
  - Create QA evidence JSON

**Acceptance Criteria:**
- [ ] All corpus models pass preflight
- [ ] 0 critical export defects
- [ ] G4 Gate evidence documented

---

### Sprint 1 Exit Criteria

| Criterion | Target | Verification |
|-----------|--------|--------------|
| G4 Gate | PASS | QA evidence generated |
| Export formats | STL, STEP, 3MF working | Manual test + CI |
| CI Matrix | Windows + Linux | GitHub Actions green |
| 3MF Export | Valid files, slicer import | Test suite |
| Performance budgets | Defined and in CI | Benchmark suite |

---

## Sprint 2: UX Refinement + Sketcher (W38-39)

**Goal:** Complete G3 Sketcher/UX Reliability Gate

**Target Gates:** G2 (partial), G3 (complete)

### Week 38 Tasks

#### SU-002: Under/Over-Constrained Diagnostics
| Field | Value |
|-------|-------|
| **Package ID** | SU-002 |
| **Priority** | P1 |
| **Est. Effort** | 10 hours |
| **Dependencies** | SU-001 (solver benchmark) |

**Description:**
Implement clear diagnostics for under-constrained and over-constrained sketch states.

**Detailed Tasks:**
- [ ] **SU-002.1:** Analyze solver output for constraint states
  - Document solver return codes
  - Identify degrees of freedom indicators
  - Map solver errors to diagnostic categories
- [ ] **SU-002.2:** Implement diagnostic detector
  - Create `sketcher/constraint_diagnostics.py` enhancement
  - Add DOF (degrees of freedom) calculation
  - Detect conflicting constraints
- [ ] **SU-002.3:** Create diagnostic UI
  - Design constraint status panel
  - Highlight affected entities
  - Add "Show affected" functionality
- [ ] **SU-002.4:** Add diagnostic tests
  - Create test cases for each state
  - Verify 95% detection accuracy
  - Add to sketch trust gate

**Acceptance Criteria:**
- [ ] Diagnosis correct in 95% of test cases
- [ ] Affected entities clearly highlighted
- [ ] UI shows actionable information

**Files to Modify:**
- `sketcher/constraint_diagnostics.py`
- `sketcher/solver.py`
- `gui/dialogs/constraint_diagnostics_dialog.py`
- `test/test_constraint_diagnostics.py`

---

#### SU-003: Constraint Conflict Explanation
| Field | Value |
|-------|-------|
| **Package ID** | SU-003 |
| **Priority** | P1 |
| **Est. Effort** | 8 hours |
| **Dependencies** | SU-002 |

**Description:**
Provide clear explanations when constraints conflict, helping users understand and fix issues.

**Detailed Tasks:**
- [ ] **SU-003.1:** Design conflict explanation system
  - Define explanation template structure
  - Create conflict type taxonomy
  - Design explanation generation algorithm
- [ ] **SU-003.2:** Implement conflict analyzer
  - Detect constraint pairs that conflict
  - Calculate conflict severity
  - Generate human-readable explanations
- [ ] **SU-003.3:** Create explanation UI
  - Design conflict explanation panel
  - Add "Suggest fix" functionality
  - Implement step-by-step resolution guide
- [ ] **SU-003.4:** Add conflict test cases
  - Create typical conflict scenarios
  - Verify explanation quality
  - User test with beginners

**Acceptance Criteria:**
- [ ] User finds correction step without trial & error
- [ ] Conflict explanations are concrete and actionable
- [ ] Resolution success rate >90%

**Files to Modify:**
- `sketcher/constraint_diagnostics.py`
- `gui/dialogs/constraint_diagnostics_dialog.py`
- `test/test_conflict_explanation.py`

---

#### SU-005: Drag Performance in Sketch
| Field | Value |
|-------|-------|
| **Package ID** | SU-005 |
| **Priority** | P1 |
| **Est. Effort** | 12 hours |
| **Dependencies** | SU-004 (direct manipulation) |

**Description:**
Optimize sketch drag performance to achieve 60 FPS target.

**Detailed Tasks:**
- [ ] **SU-005.1:** Profile current drag performance
  - Measure current FPS during drag
  - Identify bottlenecks (solver, render, event handling)
  - Document performance baseline
- [ ] **SU-005.2:** Implement dirty rectangle optimization
  - Only redraw changed regions
  - Implement incremental update
  - Cache static geometry
- [ ] **SU-005.3:** Add throttling and debouncing
  - Throttle solver calls during drag
  - Debounce final solve on drag end
  - Implement predictive solving
- [ ] **SU-005.4:** Optimize render pipeline
  - Review `gui/sketch_renderer.py`
  - Implement render budget enforcement
  - Add LOD (level of detail) for complex sketches

**Acceptance Criteria:**
- [ ] Drag latency <16ms (60 FPS)
- [ ] No visible stuttering
- [ ] Performance budget enforced

**Files to Modify:**
- `gui/sketch_renderer.py`
- `gui/sketch_controller.py`
- `sketcher/solver.py`
- `config/performance_budgets.py`

---

### Week 39 Tasks

#### UX-001: First-Run Guided Flow
| Field | Value |
|-------|-------|
| **Package ID** | UX-001 |
| **Priority** | P1 |
| **Est. Effort** | 16 hours |
| **Dependencies** | SU-008 (dimensions workflow) |

**Description:**
Create interactive 10-minute guided path for first-time users.

**Detailed Tasks:**
- [ ] **UX-001.1:** Design guided flow content
  - Define 5-7 step journey (sketch → extrude → export)
  - Write step-by-step instructions
  - Create visual guides and hints
- [ ] **UX-001.2:** Implement tutorial overlay system
  - Enhance existing `gui/tutorial_overlay.py`
  - Add step tracking and progress
  - Implement skip/resume functionality
- [ ] **UX-001.3:** Create welcome wizard
  - Design first-run dialog
  - Add "Start tutorial" vs "Skip" options
  - Remember user choice
- [ ] **UX-001.4:** Add contextual hints
  - Detect first-time actions
  - Show just-in-time tooltips
  - Track hint dismissal
- [ ] **UX-001.5:** User test with beginners
  - Recruit 3-5 first-time users
  - Measure completion rate
  - Collect feedback

**Acceptance Criteria:**
- [ ] First-time user reaches printable part without help
- [ ] Tutorial completion rate >70%
- [ ] Average completion time <10 minutes

**Files to Modify:**
- `gui/tutorial_overlay.py`
- `gui/main_window.py`
- `gui/splash_screen.py`
- `config/user_preferences.py`

---

#### UX-003: Error Messages with "Next Step"
| Field | Value |
|-------|-------|
| **Package ID** | UX-003 |
| **Priority** | P1 |
| **Est. Effort** | 8 hours |
| **Dependencies** | CH-008 (error diagnostics) |

**Description:**
Ensure all error messages include a concrete "next step" for the user.

**Detailed Tasks:**
- [ ] **UX-003.1:** Audit error message coverage
  - Review all error paths from CH-008
  - Identify messages missing "next step"
  - Prioritize by frequency
- [ ] **UX-003.2:** Write next-step content
  - Create action templates per error type
  - Add i18n translations
  - Review for clarity
- [ ] **UX-003.3:** Implement in UI components
  - Update error dialogs
  - Add "Take action" buttons where applicable
  - Link to help documentation
- [ ] **UX-003.4:** Verify coverage
  - Target: 90% of errors have next step
  - User test comprehension
  - Document exceptions

**Acceptance Criteria:**
- [ ] 90% of error hints contain concrete action
- [ ] User tests confirm comprehension
- [ ] Help links functional

**Files to Modify:**
- `gui/dialogs/error_details_dialog.py`
- `modeling/error_diagnostics.py`
- `i18n/en.json`, `i18n/de.json`

---

#### PI-006: Rollback Consistency
| Field | Value |
|-------|-------|
| **Package ID** | PI-006 |
| **Priority** | P1 |
| **Est. Effort** | 10 hours |
| **Dependencies** | PI-004 (rebuild idempotency) |

**Description:**
Ensure rollback operations (parameter slider changes, undo/redo) maintain consistent state.

**Detailed Tasks:**
- [ ] **PI-006.1:** Analyze rollback scenarios
  - Document all rollback triggers
  - Identify state inconsistencies
  - Create test matrix
- [ ] **PI-006.2:** Implement rollback contracts
  - Define state invariants
  - Add pre/post condition checks
  - Implement atomic rollback
- [ ] **PI-006.3:** Add rollback tests
  - Create rollback test suite
  - Test parameter slider edge cases
  - Verify undo/redo consistency
- [ ] **PI-006.4:** Fix identified issues
  - Address state leakage
  - Harden geometry cleanup
  - Update TNP references on rollback

**Acceptance Criteria:**
- [ ] No inconsistent state after slider changes
- [ ] Undo/redo maintains geometry integrity
- [ ] All rollback tests pass

**Files to Modify:**
- `modeling/__init__.py` (rollback logic)
- `gui/commands/` (command classes)
- `test/test_rollback_consistency.py` (new)

---

### Sprint 2 Exit Criteria

| Criterion | Target | Verification |
|-----------|--------|--------------|
| G3 Gate | PASS | QA evidence generated |
| Solver convergence | >95% | Benchmark suite |
| UX consistency | Validated | User tests |
| Drag performance | 60 FPS | Performance tests |
| Tutorial completion | >70% | User analytics |

---

## Sprint 3: Assembly + Architecture (W40-41)

**Goal:** Complete G5 Assembly Readiness, start architecture refactoring

**Target Gates:** G5 (complete), AR (partial)

### Week 40 Tasks

#### AS-001: Component-Core Stabilization
| Field | Value |
|-------|-------|
| **Package ID** | AS-001 |
| **Priority** | P1 |
| **Est. Effort** | 12 hours |
| **Dependencies** | CH-004 (rebuild failsafe) |

**Description:**
Stabilize component operations to support multi-body assemblies.

**Detailed Tasks:**
- [ ] **AS-001.1:** Audit component operations
  - Document all component-related code
  - Identify race conditions and state issues
  - Create operation flow diagrams
- [ ] **AS-001.2:** Fix active component state issues
  - Implement proper state machine
  - Add state validation
  - Fix component switching bugs
- [ ] **AS-001.3:** Harden component operations
  - Add atomic create/delete/activate
  - Implement proper error recovery
  - Add operation logging
- [ ] **AS-001.4:** Create component test suite
  - Test all component operations
  - Test edge cases (empty, nested, etc.)
  - Add to assembly trust gate

**Acceptance Criteria:**
- [ ] No inconsistent active component states
- [ ] All component operations atomic
- [ ] Component tests pass

**Files to Modify:**
- `modeling/__init__.py` (component logic)
- `gui/commands/component_commands.py`
- `test/test_component_operations.py` (new)

---

#### AS-002: Mate-System V1 Scope Definition
| Field | Value |
|-------|-------|
| **Package ID** | AS-002 |
| **Priority** | P1 |
| **Est. Effort** | 6 hours |
| **Dependencies** | AS-001 |

**Description:**
Define the exact scope of mate types for V1 release.

**Detailed Tasks:**
- [ ] **AS-002.1:** Research mate type requirements
  - Survey common CAD mate types
  - Identify minimum viable set for V1
  - Document non-goals
- [ ] **AS-002.2:** Define V1 mate scope
  - Coincident (plane-plane, plane-axis)
  - Parallel (plane-plane)
  - Concentric (cylinder-cylinder)
  - Distance (plane-plane, point-plane)
  - Document each with examples
- [ ] **AS-002.3:** Create mate specification document
  - Define mate data structures
  - Specify solver requirements
  - Document UI requirements
- [ ] **AS-002.4:** Review and approve scope
  - Team review meeting
  - Stakeholder sign-off
  - Freeze scope for V1

**Acceptance Criteria:**
- [ ] Scope freeze document created
- [ ] Clear non-goals defined
- [ ] Team approval documented

**Files to Modify:**
- `roadmap_ctp/MATE_SYSTEM_V1_SPEC.md` (new)
- `roadmap_ctp/V1_SCOPE_FREEZE.md` (new)

---

#### AR-002: modeling/__init__.py Phase 1 Split
| Field | Value |
|-------|-------|
| **Package ID** | AR-002 |
| **Priority** | P0 |
| **Est. Effort** | 16 hours |
| **Dependencies** | AR-001 (architecture blueprint) |

**Description:**
Extract modules from the 9720-line `modeling/__init__.py` file - Phase 1.

**Detailed Tasks:**
- [ ] **AR-002.1:** Analyze current structure
  - Map all classes and functions
  - Identify cohesive groups
  - Document dependencies
- [ ] **AR-002.2:** Create extraction plan
  - Phase 1: Document, Body, Rebuild, Persistence
  - Define new module boundaries
  - Plan import updates
- [ ] **AR-002.3:** Extract Document module
  - Create `modeling/document.py`
  - Move Document class and related
  - Update imports throughout codebase
- [ ] **AR-002.4:** Extract Body module
  - Create `modeling/body.py`
  - Move Body class and related
  - Update imports
- [ ] **AR-002.5:** Extract Rebuild module
  - Create `modeling/rebuild.py`
  - Move rebuild logic
  - Update imports
- [ ] **AR-002.6:** Run full test suite
  - Verify no behavioral changes
  - Fix any import issues
  - Update test imports

**Acceptance Criteria:**
- [ ] No behavioral changes
- [ ] All tests pass
- [ ] File size reduced by ~50%

**Files to Modify:**
- `modeling/__init__.py` (reduce)
- `modeling/document.py` (new)
- `modeling/body.py` (new)
- `modeling/rebuild.py` (new)
- All files importing from modeling

---

### Week 41 Tasks

#### AS-003: Mate-Solver Base Kernel
| Field | Value |
|-------|-------|
| **Package ID** | AS-003 |
| **Priority** | P1 |
| **Est. Effort** | 20 hours |
| **Dependencies** | AS-002 |

**Description:**
Implement the base solver for V1 mate types.

**Detailed Tasks:**
- [ ] **AS-003.1:** Design solver architecture
  - Define constraint representation
  - Design solver algorithm (iterative/optimization)
  - Plan integration with existing geometry
- [ ] **AS-003.2:** Implement mate data structures
  - Create `assembly/mate.py`
  - Define Mate, MateType, MateReference classes
  - Add serialization support
- [ ] **AS-003.3:** Implement solver core
  - Create `assembly/mate_solver.py`
  - Implement constraint Jacobian
  - Add iterative solver
  - Handle over-constrained detection
- [ ] **AS-003.4:** Implement V1 mate types
  - Coincident solver
  - Parallel solver
  - Concentric solver
  - Distance solver
- [ ] **AS-003.5:** Add solver tests
  - Unit tests for each mate type
  - Integration tests for combinations
  - Performance benchmarks

**Acceptance Criteria:**
- [ ] Core mate scenarios solvable
- [ ] Reproducible results
- [ ] Solver tests pass

**Files to Modify:**
- `assembly/__init__.py` (new directory)
- `assembly/mate.py` (new)
- `assembly/mate_solver.py` (new)
- `test/test_mate_solver.py` (new)

---

#### AR-004: gui/main_window.py Phase 1 Split
| Field | Value |
|-------|-------|
| **Package ID** | AR-004 |
| **Priority** | P0 |
| **Est. Effort** | 16 hours |
| **Dependencies** | AR-001 |

**Description:**
Extract modules from the 10261-line `gui/main_window.py` file - Phase 1.

**Detailed Tasks:**
- [ ] **AR-004.1:** Analyze current structure
  - Map all methods and responsibilities
  - Identify cohesive groups
  - Document signal connections
- [ ] **AR-004.2:** Create extraction plan
  - Phase 1: ModeController, ExportController, SketchController
  - Define clear interfaces
  - Plan signal routing
- [ ] **AR-004.3:** Extract ModeController
  - Create `gui/controllers/mode_controller.py`
  - Move mode switching logic
  - Maintain signal connections
- [ ] **AR-004.4:** Extract ExportController
  - Create `gui/controllers/export_controller.py`
  - Move export workflow logic
  - Update dialog connections
- [ ] **AR-004.5:** Extract SketchController
  - Create `gui/controllers/sketch_controller.py`
  - Move sketch mode logic
  - Update sketch handler connections
- [ ] **AR-004.6:** Run full test suite
  - Verify UI functionality
  - Test all extracted controllers
  - Fix any regressions

**Acceptance Criteria:**
- [ ] MainWindow significantly reduced
- [ ] All UI functionality preserved
- [ ] Tests pass

**Files to Modify:**
- `gui/main_window.py` (reduce)
- `gui/controllers/__init__.py` (new)
- `gui/controllers/mode_controller.py` (new)
- `gui/controllers/export_controller.py` (new)
- `gui/controllers/sketch_controller.py` (new)

---

#### PI-008: Geometry Drift Early Detection
| Field | Value |
|-------|-------|
| **Package ID** | PI-008 |
| **Priority** | P1 |
| **Est. Effort** | 10 hours |
| **Dependencies** | PI-002 (deterministic resolution) |

**Description:**
Implement early detection of geometry drift to catch issues before they cause crashes.

**Detailed Tasks:**
- [ ] **PI-008.1:** Define drift metrics
  - Bounding box deviation
  - Face area changes
  - Edge length changes
  - Volume changes
- [ ] **PI-008.2:** Implement drift detectors
  - Create `modeling/drift_detector.py`
  - Add baseline capture
  - Implement comparison logic
- [ ] **PI-008.3:** Add warning/block strategy
  - Define thresholds
  - Implement user warnings
  - Add block option for critical drift
- [ ] **PI-008.4:** Integrate with rebuild
  - Check drift after each rebuild
  - Log drift events
  - Add to diagnostics

**Acceptance Criteria:**
- [ ] Drift actively displayed
- [ ] Testable detection
- [ ] Warning system functional

**Files to Modify:**
- `modeling/drift_detector.py` (new)
- `modeling/__init__.py` (rebuild integration)
- `gui/main_window.py` (warning display)

---

### Sprint 3 Exit Criteria

| Criterion | Target | Verification |
|-----------|--------|--------------|
| G5 Gate | Basic PASS | Assembly workflow test |
| God files | Reduced by 20% | Line count comparison |
| Mate solver | Core types working | Solver tests |
| Component ops | Stable | Component tests |
| Drift detection | Implemented | Detector tests |

---

## Sprint 4: Gate Completion + RC Preparation (W42-43)

**Goal:** Complete all gates, prepare Release Candidate

**Target Gates:** All G0-G5 complete, G6 preparation

### Week 42 Tasks

#### QA-010: Release Candidate Burn-in
| Field | Value |
|-------|-------|
| **Package ID** | QA-010 |
| **Priority** | P0 |
| **Est. Effort** | 8 hours (setup) + 7-14 days monitoring |
| **Dependencies** | QA-008 (pre-merge gate) |

**Description:**
Establish the RC burn-in process with fixed backlog and monitoring.

**Detailed Tasks:**
- [ ] **QA-010.1:** Define burn-in criteria
  - Duration: 7-14 days
  - Required test suites: All gates green
  - Monitoring: Defect tracking, flaky test rate
- [ ] **QA-010.2:** Create burn-in checklist
  - Daily test runs
  - Defect triage process
  - Go/No-Go criteria
- [ ] **QA-010.3:** Set up monitoring dashboard
  - Test pass rates over time
  - Defect discovery rate
  - Flaky test incidents
- [ ] **QA-010.4:** Start burn-in period
  - Tag RC candidate
  - Begin daily monitoring
  - Track metrics

**Acceptance Criteria:**
- [ ] Burn-in process documented
- [ ] Monitoring active
- [ ] 0 new P0/P1 defects during burn-in

**Files to Modify:**
- `roadmap_ctp/RC_BURN_IN_CHECKLIST.md` (new)
- `scripts/rc_monitoring.ps1` (new)
- `config/release_config.py` (new)

---

#### AR-003: modeling/__init__.py Phase 2 Split
| Field | Value |
|-------|-------|
| **Package ID** | AR-003 |
| **Priority** | P1 |
| **Est. Effort** | 16 hours |
| **Dependencies** | AR-002 |

**Description:**
Continue extracting modules from `modeling/__init__.py` - Phase 2.

**Detailed Tasks:**
- [ ] **AR-003.1:** Analyze remaining content
  - Review what remains after Phase 1
  - Identify feature-compute services
  - Plan further extraction
- [ ] **AR-003.2:** Extract feature services
  - Create `modeling/features/` directory
  - Move feature-specific logic
  - Update imports
- [ ] **AR-003.3:** Reduce cyclic dependencies
  - Identify circular imports
  - Refactor to eliminate
  - Add interface modules where needed
- [ ] **AR-003.4:** Verify and test
  - Run full test suite
  - Check import times
  - Verify no regressions

**Acceptance Criteria:**
- [ ] Cyclic dependencies reduced
- [ ] File under 3000 lines
- [ ] All tests pass

**Files to Modify:**
- `modeling/__init__.py` (further reduce)
- `modeling/features/__init__.py` (new)
- `modeling/features/*.py` (new files)

---

#### AR-005: gui/main_window.py Phase 2 Split
| Field | Value |
|-------|-------|
| **Package ID** | AR-005 |
| **Priority** | P1 |
| **Est. Effort** | 16 hours |
| **Dependencies** | AR-004 |

**Description:**
Continue extracting modules from `gui/main_window.py` - Phase 2.

**Detailed Tasks:**
- [ ] **AR-005.1:** Analyze remaining content
  - Review what remains after Phase 1
  - Identify command orchestration logic
  - Plan further extraction
- [ ] **AR-005.2:** Extract command orchestration
  - Create `gui/commands/command_orchestrator.py`
  - Move command coordination logic
  - Update signal routing
- [ ] **AR-005.3:** Reduce MainWindow to integration shell
  - MainWindow becomes thin integration layer
  - All logic in controllers/commands
  - Clean signal/slot connections
- [ ] **AR-005.4:** Verify and test
  - Run UI tests
  - Check all workflows
  - Verify no regressions

**Acceptance Criteria:**
- [ ] MainWindow is integration shell only
- [ ] File under 2000 lines
- [ ] All UI tests pass

**Files to Modify:**
- `gui/main_window.py` (reduce to shell)
- `gui/commands/command_orchestrator.py` (new)
- `gui/controllers/*.py` (enhance)

---

### Week 43 Tasks

#### PD-001: V1 User Guide Core Flows
| Field | Value |
|-------|-------|
| **Package ID** | PD-001 |
| **Priority** | P1 |
| **Est. Effort** | 12 hours |
| **Dependencies** | UX-001 |

**Description:**
Create step-by-step user guide for 8 core journeys.

**Detailed Tasks:**
- [ ] **PD-001.1:** Define core journeys
  - Journey A: Create and export a simple cube
  - Journey B: Sketch, extrude, and modify a bracket
  - Journey C: Create a parametric part
  - Journey D: Import reference and design around it
  - Journey E: Add fillets and chamfers
  - Journey F: Create and edit holes
  - Journey G: Use patterns for repeated features
  - Journey H: Prepare part for 3D printing
- [ ] **PD-001.2:** Write guide content
  - Create `docs/user_guide/` directory
  - Write markdown for each journey
  - Add screenshots and diagrams
- [ ] **PD-001.3:** Create quick reference card
  - One-page keyboard shortcuts
  - Common operations reference
  - Troubleshooting quick tips
- [ ] **PD-001.4:** Review and test
  - Have new users follow guides
  - Fix unclear steps
  - Add missing information

**Acceptance Criteria:**
- [ ] New users complete journeys A-D without external help
- [ ] All screenshots current
- [ ] Guide reviewed by team

**Files to Modify:**
- `docs/user_guide/` (new directory)
- `docs/user_guide/*.md` (new files)
- `docs/quick_reference.md` (new)

---

#### PD-002: Troubleshooting Playbooks
| Field | Value |
|-------|-------|
| **Package ID** | PD-002 |
| **Priority** | P1 |
| **Est. Effort** | 8 hours |
| **Dependencies** | CH-008 |

**Description:**
Create error-code-to-solution playbooks for top 20 errors.

**Detailed Tasks:**
- [ ] **PD-002.1:** Compile error catalog
  - Extract all error codes from codebase
  - Rank by frequency and impact
  - Select top 20 for playbooks
- [ ] **PD-002.2:** Write playbook entries
  - Error code and description
  - Common causes
  - Step-by-step resolution
  - Prevention tips
- [ ] **PD-002.3:** Create searchable format
  - Design playbook structure
  - Add index by error code
  - Add index by symptom
- [ ] **PD-002.4:** Integrate with in-app help
  - Link errors to playbook entries
  - Add "Get help" button to error dialogs
  - Track help access

**Acceptance Criteria:**
- [ ] Top 20 errors documented
- [ ] Playbooks accessible from app
- [ ] Resolution success tracked

**Files to Modify:**
- `docs/troubleshooting/` (new directory)
- `docs/troubleshooting/playbook.md` (new)
- `gui/dialogs/error_details_dialog.py` (add help link)

---

#### PD-003: Known-Limitations Transparency
| Field | Value |
|-------|-------|
| **Package ID** | PD-003 |
| **Priority** | P1 |
| **Est. Effort** | 4 hours |
| **Dependencies** | QA-010 |

**Description:**
Document all known limitations and workarounds transparently.

**Detailed Tasks:**
- [ ] **PD-003.1:** Compile known limitations
  - Survey team for known issues
  - Review test skips for limitations
  - Document feature gaps
- [ ] **PD-003.2:** Write limitations document
  - Categorize by area (modeling, sketch, export, etc.)
  - Include workarounds where available
  - Add severity indicators
- [ ] **PD-003.3:** Add to application
  - Create "Known Limitations" help page
  - Link from about dialog
  - Version-specific limitations
- [ ] **PD-003.4:** Review for completeness
  - Team review
  - Ensure no hidden limitations
  - Update for RC

**Acceptance Criteria:**
- [ ] No hidden limitations for users
- [ ] Workarounds documented
- [ ] Accessible from application

**Files to Modify:**
- `docs/known_limitations.md` (new)
- `gui/dialogs/about_dialog.py` (add link)

---

#### Final Gate Runs and Documentation
| Field | Value |
|-------|-------|
| **Package ID** | FINAL-GATES |
| **Priority** | P0 |
| **Est. Effort** | 8 hours |
| **Dependencies** | All sprint tasks |

**Description:**
Run all gates and compile final evidence for RC.

**Detailed Tasks:**
- [ ] **FINAL-1:** Run all gate scripts
  - `gate_core.ps1`
  - `gate_ui.ps1`
  - `gate_fast_feedback.ps1`
  - `gate_all.ps1`
  - Document results
- [ ] **FINAL-2:** Generate gate evidence reports
  - Create QA evidence JSON
  - Generate summary markdown
  - Archive in `roadmap_ctp/archive/`
- [ ] **FINAL-3:** Create RC release notes draft
  - Compile all changes
  - Document breaking changes
  - List known issues
- [ ] **FINAL-4:** Tag RC candidate
  - Create git tag
  - Build release artifacts
  - Upload to release location

**Acceptance Criteria:**
- [ ] All gates G0-G5 PASS
- [ ] Evidence documented
- [ ] RC tagged and available

---

### Sprint 4 Exit Criteria

| Criterion | Target | Verification |
|-----------|--------|--------------|
| All Gates G0-G5 | PASS | Gate scripts |
| RC Tagged | v1.0-rc1 | Git tag exists |
| Documentation | Complete | User guide, playbooks, limitations |
| God files | Reduced by 40% | Line count comparison |
| Burn-in | Started | Monitoring active |

---

## Risk Mitigation

### Risk Register

| ID | Risk | Probability | Impact | Mitigation | Owner |
|----|------|-------------|--------|------------|-------|
| R1 | 3MF export complexity underestimated | MEDIUM | HIGH | Early spike in Week 36, fallback to STL-only if blocked | Sprint 1 |
| R2 | OCP API changes break compatibility | LOW | CRITICAL | Compatibility layer in CH-006, version pinning | Sprint 1 |
| R3 | Solver convergence issues persist | MEDIUM | HIGH | SU-001 benchmark first, escalate if <95% | Sprint 2 |
| R4 | Architecture refactoring causes regressions | MEDIUM | CRITICAL | Incremental extraction, full test suite after each phase | Sprint 3 |
| R5 | Mate solver scope creep | HIGH | MEDIUM | Strict scope freeze in AS-002, defer to V2 | Sprint 3 |
| R6 | RC burn-in reveals critical defects | MEDIUM | CRITICAL | Dedicated fix time in burn-in, rollback plan | Sprint 4 |
| R7 | Documentation incomplete for GA | LOW | MEDIUM | Parallel documentation work, templates ready | Sprint 4 |

### Rollback Plans

#### Sprint 1 Rollback
- **3MF Export:** If blocked, ship with STL/STEP only, defer 3MF to V1.1
- **CI Matrix:** If Linux fails, ship Windows-only for V1

#### Sprint 2 Rollback
- **Solver:** If convergence <95%, document as known limitation
- **Tutorial:** If incomplete, ship with basic hints only

#### Sprint 3 Rollback
- **Architecture:** If regressions found, revert to pre-split state
- **Assembly:** If mate solver unstable, disable for V1, document as preview

#### Sprint 4 Rollback
- **RC:** If critical defects found, extend burn-in, fix and re-tag

### Daily Standup Protocol
- **Time:** Daily 9:00 AM
- **Duration:** 15 minutes max
- **Focus:** Blocking items only
- **Escalation:** Same-day resolution for P0 blockers

---

## Success Metrics

### Per-Sprint Metrics

| Sprint | Metric | Target |
|--------|--------|--------|
| Sprint 1 | G4 Gate | PASS |
| Sprint 1 | Export formats | 3 (STL, STEP, 3MF) |
| Sprint 1 | CI platforms | 2 (Win, Linux) |
| Sprint 2 | Solver convergence | >95% |
| Sprint 2 | Tutorial completion | >70% |
| Sprint 2 | Drag FPS | 60 |
| Sprint 3 | God file reduction | 20% |
| Sprint 3 | Mate types working | 4 |
| Sprint 4 | All gates | PASS |
| Sprint 4 | God file reduction | 40% |

### V1 Release Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| P0 defects | 0 | Issue tracker |
| P1 defects | 0 | Issue tracker |
| Test pass rate | ≥95% | pytest output |
| Gate status | All green | Gate scripts |
| Documentation | Complete | Review checklist |
| Burn-in duration | 7-14 days | Calendar |
| Burn-in defects | 0 P0/P1 | Issue tracker |

---

## Appendix A: File Change Summary

### New Files (Planned)

```
modeling/
├── export_3mf.py           # Sprint 1
├── ocp_compat.py           # Sprint 1
├── drift_detector.py       # Sprint 3
├── document.py             # Sprint 3
├── body.py                 # Sprint 3
├── rebuild.py              # Sprint 3
└── features/
    └── __init__.py         # Sprint 4

assembly/
├── __init__.py             # Sprint 3
├── mate.py                 # Sprint 3
└── mate_solver.py          # Sprint 3

gui/
├── controllers/
│   ├── __init__.py         # Sprint 3
│   ├── mode_controller.py  # Sprint 3
│   ├── export_controller.py # Sprint 3
│   └── sketch_controller.py # Sprint 3
└── commands/
    └── command_orchestrator.py # Sprint 4

config/
├── performance_budgets.py  # Sprint 1
└── release_config.py       # Sprint 4

docs/
├── user_guide/
│   └── *.md                # Sprint 4
├── troubleshooting/
│   └── playbook.md         # Sprint 4
├── known_limitations.md    # Sprint 4
└── quick_reference.md      # Sprint 4

test/
├── test_export_3mf.py      # Sprint 1
├── test_ocp_compat.py      # Sprint 1
├── test_constraint_diagnostics.py # Sprint 2
├── test_rollback_consistency.py # Sprint 2
├── test_component_operations.py # Sprint 3
├── test_mate_solver.py     # Sprint 3
└── benchmarks/             # Sprint 1

scripts/
├── gate_performance.ps1    # Sprint 1
├── gate_core.sh            # Sprint 1
└── rc_monitoring.ps1       # Sprint 4

roadmap_ctp/
├── MATE_SYSTEM_V1_SPEC.md  # Sprint 3
├── V1_SCOPE_FREEZE.md      # Sprint 3
└── RC_BURN_IN_CHECKLIST.md # Sprint 4
```

### Modified Files (Significant)

| File | Sprint | Change |
|------|--------|--------|
| `modeling/__init__.py` | 3, 4 | Split into multiple modules |
| `gui/main_window.py` | 3, 4 | Extract controllers |
| `modeling/export_kernel.py` | 1 | Add 3MF support |
| `sketcher/constraint_diagnostics.py` | 2 | Enhance diagnostics |
| `gui/tutorial_overlay.py` | 2 | Enhance tutorial system |
| `sketcher/solver.py` | 2 | Performance optimization |
| `gui/sketch_renderer.py` | 2 | Performance optimization |

---

## Appendix B: Quick Reference Commands

### Sprint 1 Commands
```powershell
# Run export tests
pytest test/test_export*.py -v

# Run OCP compatibility tests
pytest test/test_ocp_compat.py -v

# Run performance benchmarks
pytest test/benchmarks/ --benchmark-only
```

### Sprint 2 Commands
```powershell
# Run sketch tests
pytest test/test_sketch*.py -v

# Run constraint diagnostics tests
pytest test/test_constraint_diagnostics.py -v

# Run rollback tests
pytest test/test_rollback_consistency.py -v
```

### Sprint 3 Commands
```powershell
# Run assembly tests
pytest test/test_assembly*.py -v

# Run component tests
pytest test/test_component_operations.py -v

# Run mate solver tests
pytest test/test_mate_solver.py -v
```

### Sprint 4 Commands
```powershell
# Run all gates
.\scripts\gate_all.ps1

# Generate evidence
.\scripts\generate_qa_evidence.ps1

# Tag RC
git tag -a v1.0-rc1 -m "Release Candidate 1"
```

---

**Document End**
