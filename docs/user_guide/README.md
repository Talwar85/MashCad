# MashCAD User Guide

![MashCAD](../../img/viewport3d.jpg)

Welcome to the MashCAD User Guide. This comprehensive documentation covers all aspects of using MashCAD for parametric 3D CAD design.

---

## Table of Contents

### 1. [Getting Started](01_getting_started.md)
- Installation requirements
- First launch experience
- UI overview (viewport, browser, tool panels)
- Basic navigation (orbit, pan, zoom)

### 2. [Sketch Workflow](02_sketch_workflow.md)
- Creating a new sketch
- Selecting sketch planes
- Drawing tools (line, circle, arc, rectangle)
- Adding constraints
- Finishing and editing sketches

### 3. [3D Operations](03_3d_operations.md)
- Extrude dialog and options
- Fillet and chamfer
- Boolean operations (union, difference, intersection)
- Shell and sweep
- Loft operations

### 4. [Export & Import](04_export_import.md)
- Supported formats (STEP, STL, 3MF, glTF)
- Export workflow
- Import workflow
- Printability check

### 5. [Keyboard Shortcuts](05_keyboard_shortcuts.md)
- Navigation shortcuts
- Tool shortcuts
- Action shortcuts
- Customization

---

## Quick Start

### Installation

```bash
# Using conda (recommended)
conda create -n cad_env -c conda-forge python=3.11 \
    pyside6 pyvista pyvistaqt build123d ocp vtk \
    numpy scipy shapely ezdxf loguru trimesh

conda activate cad_env
pip install ocp-tessellate
python main.py
```

### First Steps

1. **Create a sketch** - Click New Sketch, select a plane
2. **Draw geometry** - Use line, rectangle, circle tools
3. **Add constraints** - Make sketch fully defined
4. **Extrude to 3D** - Select sketch, click Extrude
5. **Export** - Save as STEP or STL for 3D printing

---

## Feature Overview

### 2D Sketch Editor

| Category | Features |
|----------|----------|
| **Drawing** | Line, Rectangle, Circle (3 modes), Arc, Polygon, Slot, Spline |
| **Editing** | Move, Copy, Rotate, Mirror, Scale, Linear/Circular Pattern |
| **Modify** | Trim, Extend, Offset, Fillet, Chamfer |
| **Constraints** | Horizontal, Vertical, Parallel, Perpendicular, Equal, Concentric, Tangent |
| **Generators** | Involute Gear, Star, Hex Nut |

### 3D Modeling

| Category | Features |
|----------|----------|
| **Create** | Extrude, Revolve, Loft, Sweep |
| **Modify** | Fillet, Chamfer, Shell, Draft, Hole, Thread |
| **Boolean** | Join (Union), Cut (Difference), Intersect |
| **Transform** | Move, Rotate, Scale with 3D Gizmo |

### Export Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| **STEP** | .step, .stp | CAD interchange |
| **STL** | .stl | 3D printing |
| **3MF** | .3mf | Modern 3D printing |
| **DXF** | .dxf | 2D drawings |
| **OBJ** | .obj | Visualization |

---

## Keyboard Shortcuts

### Most Essential

| Shortcut | Action |
|----------|--------|
| `Middle Drag` | Orbit view |
| `Scroll` | Zoom |
| `G` | Move |
| `R` | Rotate |
| `S` | Scale |
| `E` | Extrude |
| `Ctrl + S` | Save |
| `Ctrl + Z` | Undo |

### Sketch Mode

| Shortcut | Tool |
|----------|------|
| `L` | Line |
| `R` | Rectangle |
| `C` | Circle |
| `A` | Arc |
| `D` | Dimension |
| `Tab` | Numeric input |

See [Keyboard Shortcuts](05_keyboard_shortcuts.md) for complete reference.

---

## Getting Help

- **Documentation:** This user guide
- **Issues:** [GitHub Issues](../../issues)
- **Discussions:** [GitHub Discussions](../../discussions)

---

## Version Information

- **Current Version:** v0.3.0-alpha
- **Last Updated:** February 2026
- **License:** MIT

---

## Contributing

Contributions are welcome! Please see the main [README.md](../../README.md) for contribution guidelines.

---

*© 2024-2026 MashCAD Contributors*
