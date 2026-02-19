# G4 Export Infrastructure Analysis

**Goal**: Analyze current export functionality for Printability and Export Trust (G4) implementation.

**Date**: 2026-02-19
**Branch**: feature/v1-roadmap-execution

---

## 1. Current Export Architecture

### 1.1 Architecture Diagram (Text-Based)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXPORT ARCHITECTURE                                │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   MainWindow     │────▶│ExportController  │────▶│  ExportKernel    │
│  (GUI Entry)     │     │ (UI Orchestration)│     │ (Unified API)    │
└──────────────────┘     └──────────────────┘     └────────┬─────────┘
                                  │                        │
                                  ▼                        ▼
                         ┌──────────────────┐     ┌──────────────────┐
                         │ STLExportDialog  │     │ CADTessellator   │
                         │ (Quality Config) │     │ (Mesh Generation)│
                         └──────────────────┘     └────────┬─────────┘
                                                          │
                                  ▼                        ▼
                         ┌──────────────────┐     ┌──────────────────┐
                         │ExportPreflightDlg│     │ ExportValidator  │
                         │ (Issue Display)  │     │ (Pre-flight Chk) │
                         └──────────────────┘     └────────┬─────────┘
                                                          │
                                                          ▼
                                                 ┌──────────────────┐
                                                 │GeometryValidator │
                                                 │ (Kernel-Level)   │
                                                 └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         SUPPORTED FORMATS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Format   │ Status      │ Export │ Import │ Notes                           │
├───────────┼─────────────┼────────┼────────┼─────────────────────────────────┤
│  STL      │ ✅ Full     │   ✅   │   ✅    │ Binary + ASCII, Quality config  │
│  STEP     │ ✅ Full     │   ✅   │   ✅    │ AP214/AP242, Metadata support   │
│  OBJ      │ ✅ Via meshio│   ✅  │   ✅    │ Requires meshio dependency      │
│  PLY      │ ✅ Via meshio│   ✅  │   ✅    │ Requires meshio dependency      │
│  3MF      │ ❌ Placeholder│  ⚠️  │   ✅    │ Export NOT IMPLEMENTED          │
│  SVG      │ ✅ Sketch    │   ✅   │   ✅    │ Sketch export only              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow Diagram

```
USER ACTION                    PROCESSING PIPELINE                     OUTPUT
─────────────                  ─────────────────────────               ──────

File ▶ Export STL
        │
        ▼
┌───────────────────┐
│ Get Visible Bodies│
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌─────────────────────────────────────┐
│ Preflight Check   │────▶│ ExportValidator.validate_for_export │
└─────────┬─────────┘     │  - Manifold check                   │
          │               │  - Free bounds check                │
          │               │  - Degenerate faces check           │
          │               │  - Normals check (optional)         │
          │               └─────────────────────────────────────┘
          ▼
┌───────────────────┐
│ Show Dialog if    │
│ Issues Found      │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌─────────────────────────────────────┐
│ Configure Export  │────▶│ STLExportDialog                     │
└─────────┬─────────┘     │  - Quality: Draft/Standard/Fine/Ultra│
          │               │  - Format: Binary/ASCII              │
          │               │  - Units: mm/inch                    │
          │               └─────────────────────────────────────┘
          ▼
┌───────────────────┐     ┌─────────────────────────────────────┐
│ Tessellate        │────▶│ CADTessellator.tessellate_for_export│
└─────────┬─────────┘     │  - Adaptive deflection              │
          │               │  - Export cache (feature flag)      │
          │               │  - Thread-safe                      │
          │               └─────────────────────────────────────┘
          ▼
┌───────────────────┐
│ Write File        │────▶  part.stl (Binary/ASCII)
└───────────────────┘
```

---

## 2. Key Components Analysis

### 2.1 ExportController (`gui/export_controller.py`)

**Purpose**: UI orchestration for export/import workflows

**Strengths**:
- ✅ Clean separation from MainWindow
- ✅ Async STL export via `STLExportWorker`
- ✅ Signal-based UI updates (`export_started`, `export_finished`)
- ✅ Pre-flight validation integration

**Weaknesses**:
- ⚠️ Missing 3MF export implementation
- ⚠️ No batch export support
- ⚠️ Limited error recovery options

### 2.2 ExportKernel (`modeling/export_kernel.py`)

**Purpose**: Unified export API for all formats

**Strengths**:
- ✅ Format-agnostic `ExportOptions` dataclass
- ✅ Quality presets (DRAFT, STANDARD, FINE, ULTRA)
- ✅ `export_with_validation()` method
- ✅ Extensible exporter registry

**Weaknesses**:
- ❌ 3MF export returns `NOT_IMPLEMENTED`
- ⚠️ No export progress callback
- ⚠️ No parallel export for multiple bodies

### 2.3 ExportValidator (`modeling/export_validator.py`)

**Purpose**: Pre-flight validation for 3D export quality

**Strengths**:
- ✅ Manifold check via `BRepCheck_Analyzer`
- ✅ Free bounds detection (edge reference counting)
- ✅ Degenerate faces detection (area threshold)
- ✅ Non-manifold edges detection
- ✅ Configurable via `ValidationOptions`
- ✅ Quick helper methods: `is_printable()`, `is_valid_for_export()`

**Weaknesses**:
- ⚠️ Self-intersection check is optional (performance)
- ⚠️ Normals check incomplete
- ⚠️ No automated healing suggestions
- ⚠️ No printability scoring system

### 2.4 CADTessellator (`modeling/cad_tessellator.py`)

**Purpose**: B-Rep to mesh conversion with caching

**Strengths**:
- ✅ Adaptive deflection based on model size
- ✅ Export-specific cache (feature flag: `export_cache`)
- ✅ Thread-safe for async tessellation
- ✅ B-Rep edge extraction (not tessellation edges)
- ✅ Face-ID tracking for TNP

**Weaknesses**:
- ⚠️ No mesh quality validation post-tessellation
- ⚠️ No triangle count estimation accuracy tracking

### 2.5 GeometryValidator (`modeling/geometry_validator.py`)

**Purpose**: Kernel-level geometry validation

**Strengths**:
- ✅ Three validation levels (QUICK, NORMAL, FULL)
- ✅ Pre-boolean validation
- ✅ Euler-Poincaré check
- ✅ Volume/topology sanity checks

**Weaknesses**:
- ⚠️ Not integrated into export pipeline
- ⚠️ No printability-specific checks

---

## 3. Feature Flags Analysis

### 3.1 Export-Related Feature Flags

| Flag | Default | Purpose | G4 Relevance |
|------|---------|---------|--------------|
| `export_free_bounds_check` | `True` | Enable free bounds check before export | ✅ PR-002 |
| `export_cache` | `True` | Tessellation cache for export | ✅ Performance |
| `adaptive_tessellation` | `True` | Deflection proportional to model size | ✅ Quality |
| `boolean_post_validation` | `True` | Post-boolean shape validation | ✅ Quality |
| `self_heal_strict` | `True` | Atomic rollback on invalid geometry | ✅ Robustness |

### 3.2 Missing Feature Flags for G4

| Proposed Flag | Purpose |
|---------------|---------|
| `printability_trust_gate` | Block export if not printable |
| `export_regression_corpus` | Enable corpus-based validation |
| `3mf_export` | Enable 3MF export (when implemented) |

---

## 4. Gap Analysis for G4 Packages

### 4.1 PR-001: Export Path Standardization

**Status**: ⚠️ Partially Complete

**What Exists**:
- ✅ `ExportKernel` provides unified API
- ✅ `ExportController` orchestrates UI
- ✅ `ExportOptions` dataclass standardizes configuration
- ✅ Format auto-detection from file extension

**What's Missing**:
- ❌ 3MF export implementation (placeholder only)
- ❌ Export path validation tests
- ❌ Export configuration persistence
- ❌ Batch export API

**Files to Modify**:
- `modeling/export_kernel.py` - Implement `_export_3mf()`
- `gui/export_controller.py` - Add `export_3mf()` method
- `config/feature_flags.py` - Add `3mf_export` flag

### 4.2 PR-002: Manifold/Free-Bounds Check

**Status**: ✅ Mostly Complete

**What Exists**:
- ✅ `ExportValidator` with manifold check
- ✅ Free bounds detection via edge counting
- ✅ Degenerate faces detection
- ✅ Feature flag `export_free_bounds_check`
- ✅ `ExportPreflightDialog` for issue display

**What's Missing**:
- ⚠️ Self-intersection check is optional (performance concern)
- ⚠️ No automated healing suggestions
- ⚠️ No repair integration (link to `geometry_healer.py`)
- ⚠️ Normals check incomplete

**Files to Modify**:
- `modeling/export_validator.py` - Complete normals check
- `gui/dialogs/export_preflight_dialog.py` - Add "Auto-Repair" button
- `modeling/geometry_healer.py` - Integrate with validator

### 4.3 PR-008: STL/3MF Regression Corpus

**Status**: ❌ Not Started

**What Exists**:
- ⚠️ Test files exist (`stl/V1.stl`, `stl/TensionMeter.stl`)
- ✅ `test_export_kernel.py` - Unit tests for export
- ✅ `test_export_validator.py` - Unit tests for validation

**What's Missing**:
- ❌ No regression corpus directory structure
- ❌ No golden file comparison system
- ❌ No round-trip test framework (export → import → compare)
- ❌ No mesh fidelity metrics
- ❌ No automated corpus runner

**Files to Create**:
- `test/corpus/` - Regression corpus directory
- `test/corpus/stl/` - STL test files with expected results
- `test/corpus/3mf/` - 3MF test files (future)
- `test/test_export_corpus.py` - Corpus runner
- `scripts/run_export_corpus.ps1` - CI integration

### 4.4 PR-010: Printability Trust Gate

**Status**: ⚠️ Partially Complete

**What Exists**:
- ✅ `ExportValidator.is_printable()` method
- ✅ `ValidationResult.is_printable` property
- ✅ Pre-flight dialog shows printability issues
- ✅ User can choose to export anyway

**What's Missing**:
- ❌ No automated trust gate enforcement
- ❌ No printability scoring system (0-100)
- ❌ No minimum score threshold configuration
- ❌ No printability report generation
- ❌ No integration with slicing software validation

**Files to Modify**:
- `modeling/export_validator.py` - Add `PrintabilityScore` class
- `gui/export_controller.py` - Add trust gate enforcement
- `config/feature_flags.py` - Add `printability_trust_gate` flag
- `gui/dialogs/export_preflight_dialog.py` - Show score

---

## 5. Implementation Recommendations

### 5.1 Recommended Implementation Order

```
Phase 1: Foundation (PR-001 + PR-002 completion)
├── 1.1 Complete normals check in ExportValidator
├── 1.2 Add auto-repair integration
├── 1.3 Implement 3MF export (use lib3mf or py3mf)
└── 1.4 Add export configuration persistence

Phase 2: Regression Corpus (PR-008)
├── 2.1 Create corpus directory structure
├── 2.2 Define golden file format (STL + metadata JSON)
├── 2.3 Implement mesh comparison utilities
├── 2.4 Create round-trip test framework
└── 2.5 Integrate with CI pipeline

Phase 3: Trust Gate (PR-010)
├── 3.1 Design printability scoring system
├── 3.2 Implement PrintabilityScore class
├── 3.3 Add trust gate enforcement option
├── 3.4 Create printability report generator
└── 3.5 Add user configuration for thresholds
```

### 5.2 Priority Matrix

| Package | Effort | Impact | Risk | Priority |
|---------|--------|--------|------|----------|
| PR-001 (3MF) | Medium | High | Low | **P1** |
| PR-002 (Complete) | Low | Medium | Low | **P2** |
| PR-008 (Corpus) | High | High | Medium | **P3** |
| PR-010 (Trust Gate) | Medium | High | Low | **P4** |

### 5.3 Dependencies

```
PR-001 (3MF Export)
    └── Requires: lib3mf Python bindings or py3mf package

PR-002 (Validation Complete)
    └── Requires: geometry_healer.py integration

PR-008 (Regression Corpus)
    └── Requires: PR-001, PR-002 for meaningful tests

PR-010 (Trust Gate)
    └── Requires: PR-002 for scoring basis
```

---

## 6. Test Coverage Analysis

### 6.1 Existing Tests

| Test File | Coverage | Notes |
|-----------|----------|-------|
| `test_export_kernel.py` | ExportKernel API | Mock-based unit tests |
| `test_export_validator.py` | ExportValidator | Mock-based unit tests |
| `test_export_controller.py` | ExportController | Signal/flow tests |
| `test_integration_export_diagnostics.py` | Integration | Error diagnostics |
| `test_mesh_quality_checker.py` | Mesh Quality | V1.stl tests |

### 6.2 Missing Tests

- ❌ 3MF export round-trip tests
- ❌ Large file export stress tests
- ❌ Multi-body export tests
- ❌ Printability score validation tests
- ❌ Corpus-based regression tests

---

## 7. Files Summary

### 7.1 Files to Modify

| File | Changes Required |
|------|------------------|
| `modeling/export_kernel.py` | Implement `_export_3mf()` |
| `modeling/export_validator.py` | Complete normals check, add scoring |
| `gui/export_controller.py` | Add 3MF export, trust gate |
| `gui/dialogs/export_preflight_dialog.py` | Add repair button, score display |
| `config/feature_flags.py` | Add new flags |

### 7.2 Files to Create

| File | Purpose |
|------|---------|
| `test/corpus/README.md` | Corpus documentation |
| `test/corpus/stl/*.json` | Golden file metadata |
| `test/test_export_corpus.py` | Corpus runner |
| `modeling/printability_score.py` | Scoring system |
| `scripts/run_export_corpus.ps1` | CI integration |

---

## 8. Next Steps

1. **Review this analysis** with the team
2. **Prioritize packages** based on current roadmap
3. **Create detailed implementation plans** for each PR package
4. **Set up corpus infrastructure** (PR-008 foundation)
5. **Implement 3MF export** (PR-001 completion)

---

## Appendix A: Export Quality Presets

```python
QUALITY_PRESETS = [
    (0.1,   0.5,  "Draft"),       # ~11° angular, coarse
    (0.05,  0.3,  "Standard"),    # ~17° angular
    (0.01,  0.2,  "Fine"),        # ~11.5° angular, current default
    (0.005, 0.1,  "Ultra"),       # ~5.7° angular, very fine
]
```

## Appendix B: Validation Check Types

```python
class ValidationCheckType(Enum):
    MANIFOLD = "manifold"               # Geschlossenes Volumen
    FREE_BOUNDS = "free_bounds"         # Offene Kanten
    DEGENERATE_FACES = "degenerate"     # Degenerierte Faces
    NORMALS = "normals"                 # Normalen-Konsistenz
    SELF_INTERSECTION = "self_intersection"  # Selbstüberschneidungen
    SMALL_FEATURES = "small_features"   # Sehr kleine Features
    NON_MANIFOLD_EDGES = "non_manifold_edges"  # Nicht-Manifold Kanten
```

## Appendix C: Current Test Files

- `stl/V1.stl` - Primary test mesh
- `stl/TensionMeter.stl` - Complex test mesh
