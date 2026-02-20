# MashCAD Troubleshooting Guide

Welcome to the MashCAD troubleshooting documentation. This guide helps you diagnose and fix common issues quickly.

## Quick Diagnosis

### By Symptom

| Symptom | Likely Cause | Guide | Section |
|---------|--------------|-------|---------|
| 🔴 Sketch won't solve | Over/under-constrained | [Sketch Issues](sketch_issues.md) | Sketch Won't Solve |
| 🔴 Profile not detected | Open contour or gaps | [Sketch Issues](sketch_issues.md) | Profile Not Detected |
| 🔴 Extrude fails | Invalid profile or parameters | [3D Operations](3d_operations.md) | Extrude Failures |
| 🔴 Fillet fails | Radius too large | [3D Operations](3d_operations.md) | Fillet/Chamfer Errors |
| 🔴 Boolean fails | Invalid geometry | [3D Operations](3d_operations.md) | Boolean Operation Failures |
| 🟡 Export fails | Invalid geometry for format | [Export/Import](export_import.md) | Export Failures |
| 🟡 STL has holes | Non-manifold mesh | [Export/Import](export_import.md) | STL Mesh Quality Issues |
| 🟡 STEP incompatible | Version mismatch | [Export/Import](export_import.md) | STEP File Compatibility |
| 🟠 Slow viewport | Too many triangles | [Performance](performance.md) | Slow Viewport Rendering |
| 🟠 High memory | Cache or leak issue | [Performance](performance.md) | High Memory Usage |
| 🟠 App freezes | Long operation on main thread | [Performance](performance.md) | Application Freezes |
| 🔵 Won't start | Missing dependencies | [Installation](installation.md) | Environment Setup |
| 🔵 Import errors | Package not installed | [Installation](installation.md) | Dependency Conflicts |
| 🔵 Black viewport | GPU/driver issue | [Installation](installation.md) | GPU/Driver Problems |

### By Error Type

| Error Pattern | Category | Guide |
|---------------|----------|-------|
| `Over-constrained` / `Under-constrained` | Sketch | [Sketch Issues](sketch_issues.md) |
| `Profile not closed` / `No valid profile` | Sketch | [Sketch Issues](sketch_issues.md) |
| `Extrude failed` / `Invalid extrusion` | 3D Operations | [3D Operations](3d_operations.md) |
| `Fillet failed` / `Radius exceeds` | 3D Operations | [3D Operations](3d_operations.md) |
| `Boolean failed` / `Invalid solid` | 3D Operations | [3D Operations](3d_operations.md) |
| `Export failed` / `Tessellation failed` | Export/Import | [Export/Import](export_import.md) |
| `Non-manifold` / `Mesh has holes` | Export/Import | [Export/Import](export_import.md) |
| `Out of memory` / `High memory` | Performance | [Performance](performance.md) |
| `ModuleNotFoundError` / `ImportError` | Installation | [Installation](installation.md) |
| `OpenGL` / `GPU` / `Driver` | Installation | [Installation](installation.md) |

---

## Documentation Index

### 1. [Sketch Issues](sketch_issues.md)
Problems with2D sketch creation and constraint solving.

**Topics Covered:**
- Sketch won't solve (over/under-constrained)
- Constraints not working as expected
- Profile not detected
- Sketch plane issues (including `plane_y_dir` bug)
- Performance problems with complex sketches

**Key Files:**
- `sketcher/sketch.py`
- `sketcher/solver.py`
- `sketcher/constraint_diagnostics.py`

### 2. [3D Operations](3d_operations.md)
Problems with3D modeling operations.

**Topics Covered:**
- Extrude failures
- Fillet/chamfer errors
- Boolean operation failures
- Shell/sweep/loft issues
- Geometry drift after edits (TNP failures)

**Key Files:**
- `modeling/__init__.py`
- `modeling/boolean_engine_v4.py`
- `modeling/edge_operations.py`
- `modeling/geometry_drift_detector.py`

### 3. [Export/Import](export_import.md)
Problems with file export and import.

**Topics Covered:**
- Export failures
- STL mesh quality issues
- STEP file compatibility
- Import failures
- Printability check failures

**Key Files:**
- `modeling/export_kernel.py`
- `modeling/export_validator.py`
- `modeling/cad_tessellator.py`
- `modeling/mesh_repair.py`

### 4. [Performance](performance.md)
Performance and responsiveness issues.

**Topics Covered:**
- Slow viewport rendering
- High memory usage
- Application freezes
- Startup problems
- Optimization tips

**Key Files:**
- `config/feature_flags.py`
- `modeling/brep_cache.py`
- `gui/viewport/`

### 5. [Installation](installation.md)
Installation and environment setup issues.

**Topics Covered:**
- OCP/OCCT installation issues
- Dependency conflicts
- GPU/driver problems
- Cross-platform issues (Windows, Linux, macOS)
- Environment setup

**Key Files:**
- `requirements.txt`
- `main.py`

---

## Known Issues

### Sketch Plane Bug: `plane_y_dir` becomes (0, 0, 0)

**Status:** Workaround implemented

**Description:** When creating a sketch plane from certain face selections, the Y-direction vector can become zero.

**Workaround Location:** [`modeling/__init__.py`](../../modeling/__init__.py) lines 1526-1527

```python
if y_dir.X == 0 and y_dir.Y == 0 and y_dir.Z == 0:
    y_dir = z_dir.cross(x_dir)  # Fallback calculation
```

**See Also:** [Sketch Issues - Sketch Plane Issues](sketch_issues.md#sketch-plane-issues)

### TNP (Topology Naming Protocol) Failures

**Status:** Active development

**Description:** After model edits, face/edge references may be lost, causing features to fail or drift.

**Debug Mode:**
```python
from config.feature_flags import set_flag
set_flag("tnp_debug_logging", True)
```

**See Also:** [3D Operations - Geometry Drift](3d_operations.md#geometry-drift-after-edits)

### Boolean Operation Edge Cases

**Status:** Mitigations implemented

**Description:** Certain geometric configurations can cause boolean operations to fail or produce invalid results.

**Mitigations:**
```python
from config.feature_flags import set_flag
set_flag("boolean_self_intersection_check", True)
set_flag("boolean_post_validation", True)
set_flag("boolean_argument_analyzer", True)
```

**See Also:** [3D Operations - Boolean Failures](3d_operations.md#boolean-operation-failures)

---

## Debug Mode

### Enable All Debug Flags

```python
from config.feature_flags import set_flag

# Sketch debugging
set_flag("sketch_debug", True)
set_flag("sketch_input_logging", True)

# 3D operation debugging
set_flag("extrude_debug", True)
set_flag("tnp_debug_logging", True)

# Performance debugging
set_flag("performance_monitoring", True)
set_flag("operation_timing", True)

# Startup debugging
set_flag("startup_debug", True)
```

### Collect Diagnostics

```python
# Generate diagnostic report
from core.diagnostics import generate_report
report = generate_report()
report.save("mashcad_diagnostics.txt")

# Print summary
print(report.summary())
```

---

## Feature Flags Reference

### Performance Flags (Recommended: All True)

| Flag | Purpose |
|------|---------|
| `optimized_actor_pooling` | Reuse viewport actors |
| `reuse_hover_markers` | Reuse selection markers |
| `picker_pooling` | Pool picking objects |
| `bbox_early_rejection` | Skip invisible objects |
| `export_cache` | Cache export results |
| `feature_dependency_tracking` | Track feature dependencies |
| `async_tessellation` | Async mesh generation |

### Robustness Flags (Recommended: All True)

| Flag | Purpose |
|------|---------|
| `boolean_self_intersection_check` | Check for self-intersection |
| `boolean_post_validation` | Validate boolean results |
| `boolean_argument_analyzer` | Analyze boolean arguments |
| `ocp_glue_auto_detect` | Auto-detect glued faces |
| `batch_fillets` | Optimize multiple fillets |

### Debug Flags (Default: False)

| Flag | Purpose |
|------|---------|
| `sketch_debug` | Sketch operation logging |
| `sketch_input_logging` | Log sketch inputs |
| `extrude_debug` | Extrude operation logging |
| `tnp_debug_logging` | TNP tracking logging |
| `viewport_debug` | Viewport rendering logging |
| `performance_monitoring` | Performance metrics |

---

## Getting Help

### Before Reporting

1. Check the relevant troubleshooting guide
2. Enable debug logging and collect diagnostics
3. Try to reproduce with minimal steps
4. Check if issue is in Known Issues above

### Information to Include

- MashCAD version
- Operating system and version
- Python version
- Steps to reproduce
- Error messages (exact text)
- Diagnostic report (if available)

### Related Resources

- [AGENTS.md](../../AGENTS.md) - Project status and conventions
- [V1_EXECUTION_PLAN.md](../../V1_EXECUTION_PLAN.md) - Development roadmap
- [config/feature_flags.py](../../config/feature_flags.py) - All feature flags

---

## Quick Commands

### Verify Installation
```bash
python -c "from core.diagnostics import verify_installation; verify_installation()"
```

### Run Tests
```bash
pytest test/
```

### Check Dependencies
```bash
pip check
pip list | grep -E "ocp|vtk|PySide6|numpy|scipy"
```

### Clear Caches
```python
from modeling.brep_cache import BrepCache
BrepCache.clear_all()

from meshconverter.mesh_converter import clear_mesh_cache
clear_mesh_cache()

import gc
gc.collect()
```

### Reset Configuration
```python
from config.settings import reset_to_defaults
reset_to_defaults()
```
