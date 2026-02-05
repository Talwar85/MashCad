# MashCad - AI Agent Reference

> **Version:** 0.3.0-beta | **Last Updated:** February 2026
>
> This file contains essential information for AI coding agents working on the MashCad project.

---

## Project Overview

**MashCad** is an open-source parametric CAD application built with Python. It combines a constraint-based 2D sketcher with 3D modeling capabilities, powered by Build123d (OpenCASCADE kernel).

### Key Characteristics

| Aspect | Details |
|--------|---------|
| **Primary Language** | German (comments, docs), English (code) |
| **GUI Framework** | PySide6 (Qt6) |
| **CAD Kernel** | Build123d + OCP (OpenCASCADE Python bindings) |
| **3D Visualization** | PyVista (VTK-based) |
| **2D Geometry** | Shapely |
| **Status** | Prototype / Early Development |

---

## Technology Stack

### Core Dependencies
```
Python >= 3.11
PySide6 >= 6.5.0          # GUI Framework
build123d >= 0.5.0        # CAD Kernel (OpenCASCADE wrapper)
pyvista >= 0.42.0         # 3D Visualization
pyvistaqt >= 0.11.0       # Qt integration for PyVista
vtk >= 9.2.0              # Visualization Toolkit
ocp-tessellate >= 3.0.0   # CAD kernel → mesh conversion
```

### Scientific & Geometry
```
numpy >= 1.24.0           # Numerical operations
scipy >= 1.10.0           # Constraint solver, optimization
shapely >= 2.0.0          # 2D geometry operations
```

### Export & Import
```
ezdxf >= 1.0.0            # DXF export
lib3mf                    # 3MF export (3D printing)
trimesh >= 4.0.0          # Mesh operations
gmsh >= 4.15.0            # Mesh generation (optional)
```

### Logging
```
loguru >= 0.7.0           # Structured logging
```

---

## Project Structure

```
MashCad/
├── main.py                    # Application entry point
├── MashCAD.spec              # PyInstaller build specification
├── config/                   # Configuration modules
│   ├── version.py            # Centralized version management
│   ├── feature_flags.py      # Feature toggle system
│   └── tolerances.py         # Centralized tolerance constants
├── core/                     # Core utilities
│   └── parameters.py         # Parametric variable system
├── modeling/                 # 3D modeling & CAD operations
│   ├── __init__.py           # Body, Feature, Component classes
│   ├── boolean_engine_v4.py  # Boolean operations (Join/Cut/Intersect)
│   ├── body_transaction.py   # Transaction/rollback system
│   ├── result_types.py       # OperationResult, BooleanResult
│   ├── cad_tessellator.py    # Kernel → mesh conversion
│   ├── feature_dependency.py # Feature dependency graph
│   ├── tnp_tracker.py        # TNP mitigation (legacy)
│   ├── tnp_shape_reference.py # TNP v3.0: Persistent shape references
│   ├── step_io.py            # STEP import/export
│   └── ...                   # Additional modeling modules
├── sketcher/                 # 2D sketcher with constraints
│   ├── geometry.py           # 2D primitives (Point2D, Line2D, etc.)
│   ├── constraints.py        # Constraint definitions
│   ├── solver.py             # Lagrange multiplier constraint solver
│   └── sketch.py             # Sketch class
├── gui/                      # Qt GUI components
│   ├── main_window.py        # Main application window
│   ├── viewport_pyvista.py   # 3D viewport (PyVista-based)
│   ├── sketch_editor.py      # 2D sketch editor
│   ├── browser.py            # Feature tree browser
│   ├── tool_panel_3d.py      # 3D tools panel
│   └── ...                   # Additional GUI modules
├── meshconverter/            # Mesh to CAD conversion (STL/OBJ → BREP)
├── i18n/                     # Internationalization
│   ├── __init__.py           # tr() translation function
│   ├── de.json               # German translations
│   └── en.json               # English translations
├── hooks/                    # PyInstaller hooks
├── docs/                     # Documentation
└── test/                     # Test directory (currently empty)
```

---

## Development Environment Setup

### Prerequisites
- [Miniforge](https://github.com/conda-forge/miniforge) or Miniconda
- Python 3.11+

### Installation

```bash
# Create conda environment
conda create -n cad_env -c conda-forge python=3.11 \
    pyside6 pyvista pyvistaqt build123d ocp vtk \
    numpy scipy shapely ezdxf loguru trimesh \
    matplotlib pillow lib3mf

# Activate environment
conda activate cad_env

# Install additional pip dependencies
pip install ocp-tessellate

# Verify installation
python check_dependencies.py
```

### Running the Application

```bash
conda activate cad_env
python main.py
```

### Running Tests

```bash
# Test sketcher without GUI
python main.py --test

# Run pytest (if tests exist)
pytest
```

---

## Build Process

### Local Build (Development)

**Windows:**
```bash
build_local.bat
```

**macOS/Linux:**
```bash
./build_local.sh
```

### Manual Build

```bash
pip install pyinstaller
pyinstaller MashCAD.spec
```

### Build Outputs

| Platform | Output |
|----------|--------|
| Windows | `dist/MashCAD/MashCAD.exe` |
| macOS | `dist/MashCAD.app` |
| Linux | `dist/MashCAD/MashCAD` |

### CI/CD

GitHub Actions workflow at `.github/workflows/` automatically builds for all platforms on tag push:

```bash
git tag v0.2.1
git push origin v0.2.1
```

---

## Architecture Principles

### 1. CAD Kernel First (Single Source of Truth)

```python
# The CAD kernel (_build123d_solid) is the ONLY truth
class Body:
    def __init__(self):
        self._build123d_solid = None      # ← MASTER
        self._mesh_cache = None           # ← Private, lazy
        self._mesh_cache_valid = False

    @property
    def vtk_mesh(self):
        """Lazy-loaded - regenerates automatically on access"""
        if not self._mesh_cache_valid:
            self._regenerate_mesh()
        return self._mesh_cache
```

**Rules:**
- NEVER manipulate meshes directly - always go through the kernel
- After EVERY kernel change, call `invalidate_mesh()`
- Meshes are regenerated lazily (only when needed for rendering)

### 2. Transaction-Based Safety

Every destructive operation is wrapped in a transaction:

```python
from modeling.body_transaction import BodyTransaction, BooleanOperationError

with BodyTransaction(body, "Boolean Cut") as txn:
    # Operation here
    body._build123d_solid = result
    body.invalidate_mesh()
    txn.commit()  # Must commit to prevent rollback
```

### 3. No Quick Fixes - Build Solid Software

**NEVER implement quick fixes or workarounds.** Always solve the root cause:

```python
# ❌ WRONG: Lower threshold to make failing test pass
if best_score > 0.4:  # Was 0.6, lowered because tests fail
    return match

# ✅ CORRECT: Fix the underlying issue
# Update selectors after geometry changes
self._update_selectors_after_operation(body)
if best_score > 0.6:  # Keep strict threshold
    return match
```

**Rules:**
- Never adjust thresholds, tolerances, or parameters to hide bugs
- Never add special-case handling for symptoms instead of causes  
- If a test fails, fix the underlying architecture, not the test
- Document architectural decisions and their rationale

### 4. Structured Result Types

All operations return structured results:

```python
from modeling.result_types import OperationResult, ResultStatus

result = some_operation()

match result.status:
    case ResultStatus.SUCCESS:
        logger.success(result.message)
    case ResultStatus.ERROR:
        show_error_dialog(result.message)
    case ResultStatus.EMPTY:
        show_info("No results")
    case ResultStatus.WARNING:
        show_warning(result.message)
```

### 4. Feature Flags

New features are implemented behind feature flags:

```python
from config.feature_flags import is_enabled

if is_enabled("my_new_feature"):
    # New feature code
    pass
```

Set flags in `config/feature_flags.py` or at runtime:
```python
from config.feature_flags import set_flag
set_flag("my_new_feature", True)
```

### 5. Centralized Tolerances

All tolerances are defined in `config/tolerances.py`:

```python
from config.tolerances import Tolerances

fuzzy_tolerance = Tolerances.KERNEL_FUZZY  # 1e-4 (0.1mm)
tessellation_quality = Tolerances.TESSELLATION_QUALITY  # 0.01 (10µm)
```

### 6. TNP v3.0 (Topological Naming Problem)

Professional system for persistent shape identification across boolean operations:

```python
# modeling/tnp_shape_reference.py

@dataclass(frozen=True)
class ShapeID:
    """Immutable identifier for shape tracking"""
    feature_id: str      # Feature that created this reference
    local_id: int        # Index within feature
    shape_type: ShapeType

@dataclass
class ShapeReference:
    """Persistent reference with multi-strategy resolution"""
    ref_id: ShapeID
    original_shape: TopoDS_Shape      # OCP shape for history lookup
    geometric_selector: Any            # Fallback: geometric matching
    
    def resolve(self, solid, history=None):
        # Strategy 1: BRepTools_History (if available)
        if history:
            return self._resolve_via_history(history)
        # Strategy 2: Geometric matching (fallback)
        return self._resolve_via_geometry(solid)
```

**Usage in Features:**
```python
@dataclass
class FilletFeature(Feature):
    edge_shape_ids: List[ShapeID] = None        # TNP v3.0 Primary
    geometric_selectors: List = None             # Geometric Fallback
    edge_selectors: List = None                  # Legacy Fallback
```

**Resolution Order:**
1. History-based (BRepTools_History) - most accurate
2. Geometric matching (center, direction, length) - robust fallback
3. Legacy point selectors - last resort

---

## Code Style Guidelines

### Language
- **Code**: English (variable names, functions, classes)
- **Comments**: German
- **Docstrings**: German
- **User-facing strings**: Use `tr()` for i18n

### Example

```python
def calculate_extrusion_volume(sketch: Sketch, height: float) -> float:
    """
    Berechnet das Volumen einer Extrusion.
    
    Args:
        sketch: Der zu extrudierende Sketch
        height: Extrusionshöhe in mm
        
    Returns:
        Volumen in mm³
    """
    # Fläche berechnen
    area = sketch.calculate_area()
    
    # Volumen = Fläche × Höhe
    return area * height
```

### Logging

Use `loguru` with appropriate levels:

```python
from loguru import logger

logger.debug("Detail für Entwickler")
logger.info("Normale Information")
logger.success("Erfolg (grün)")
logger.warning("Warnung")
logger.error("Fehler")
```

### String Translation

```python
from i18n import tr

# In code
label = tr("File")  # → "Datei" in German

# With formatting
msg = tr("Saved: {path}").format(path="/file.txt")
```

---

## Key Patterns

### Boolean Operations

```python
from modeling.boolean_engine_v4 import BooleanEngineV4

result = BooleanEngineV4.execute_boolean(
    body=target_body,
    tool_solid=tool_body._build123d_solid,
    operation="Cut"  # "Join", "Cut", "Intersect"
)

if result.is_error:
    show_error(result.message)
```

### Feature Creation

```python
from modeling import ExtrudeFeature

feature = ExtrudeFeature(
    sketch=my_sketch,
    distance=10.0,
    operation="New Body",  # or "Join", "Cut", "Intersect"
    profile_selector=[(cx, cy)]  # Centroids of selected profiles
)
body.features.append(feature)
```

### Serialization (Save/Load)

All major classes implement `to_dict()` and `from_dict()`:

```python
# Save
body_data = body.to_dict()

# Load
body = Body.from_dict(body_data)
```

---

## Forbidden Patterns (ANTI-PATTERNS)

### ❌ NEVER: Mesh Fallbacks
```python
# FORBIDDEN
try:
    return kernel_boolean(body, tool)
except:
    return mesh_boolean(body, tool)  # NEVER!
```

### ❌ NEVER: Direct Mesh Assignment
```python
# FORBIDDEN
body.vtk_mesh = some_mesh  # vtk_mesh is @property!

# CORRECT
body._build123d_solid = new_solid
body.invalidate_mesh()
```

### ❌ NEVER: Silent Failures
```python
# FORBIDDEN
try:
    do_operation()
except:
    pass  # User learns nothing!

# CORRECT
try:
    do_operation()
except Exception as e:
    return OperationResult.error(f"Operation failed: {e}")
```

### ❌ NEVER: Forget Cache Invalidation
```python
# FORBIDDEN
body._build123d_solid = new_solid
# Mesh is now out of sync!

# CORRECT
body._build123d_solid = new_solid
body.invalidate_mesh()
```

---

## Keyboard Shortcuts Reference

| Key | Action |
|-----|--------|
| `G` | Move gizmo |
| `R` | Rotate gizmo |
| `S` | Scale gizmo |
| `M` | Mirror dialog |
| `H` | Hide/Show toggle |
| `Esc` | Cancel / Deselect |
| `Delete` | Delete selection |
| `Tab` | Numeric input (sketcher) |
| `Space` | 3D peek (sketcher) |

---

## Testing Strategy

### Current State
- Test directory exists but is empty
- `pytest.ini` configured but no test files
- Manual testing via `python main.py --test` (sketcher tests)

### Adding Tests

When adding tests, follow pytest markers:
```ini
[pytest]
markers =
    unit: Unit tests (no GUI, headless)
    integration: Integration tests (requires Qt/display)
    slow: Slow tests (>10s)
```

### Running Tests
```bash
pytest -v                    # All tests
pytest -m unit              # Unit tests only
pytest -m "not slow"        # Exclude slow tests
pytest --tb=short           # Short traceback
```

---

## Common Issues & Solutions

### OpenMP Conflict
Set environment variable before running:
```bash
set KMP_DUPLICATE_LIB_OK=TRUE  # Windows
export KMP_DUPLICATE_LIB_OK=TRUE  # Linux/macOS
```

### lib3mf Not Found
The `hooks/hook-lib3mf.py` patches library discovery for bundled apps.

### VTK/PyVista Rendering Issues
- Update graphics drivers
- Linux: `sudo apt-get install libgl1-mesa-glx libegl1-mesa`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.2.0-beta | Feb 2026 | Current version |
| 0.1.0-alpha | 2025 | Initial prototype |

---

## License

MIT License - See `LICENSE` file

---

## Credits

- [Build123d](https://github.com/gumyr/build123d) - CAD Kernel
- [PyVista](https://github.com/pyvista/pyvista) - 3D Rendering
- [OpenCASCADE](https://www.opencascade.com/) - Geometry kernel
