# Getting Started with MashCAD

![MashCAD Logo](../../img/viewport3d.jpg)

Welcome to MashCAD, an open-source parametric CAD application built with Python. This guide will help you get started with the core features and workflows.

---

## Table of Contents

1. [Installation Requirements](#installation-requirements)
2. [First Launch Experience](#first-launch-experience)
3. [UI Overview](#ui-overview)
4. [Basic Navigation](#basic-navigation)
5. [Tips & Best Practices](#tips--best-practices)

---

## Installation Requirements

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Windows 10, Ubuntu 20.04, macOS 10.15 | Windows 11, Ubuntu 22.04, macOS 12+ |
| **RAM** | 8 GB | 16 GB |
| **GPU** | OpenGL 3.2 compatible | Dedicated GPU with OpenGL 4.5+ |
| **Storage** | 2 GB | 5 GB (with cache) |

### Pre-built Binaries

Download the latest release for your platform from the [Releases page](../../releases):

- **Windows:** `MashCAD_x64.exe`
- **Linux:** `MashCAD_x86_64.AppImage`
- **macOS:** `MashCAD.dmg` (Intel x64, works on M1/M2 via Rosetta 2)

### Development Setup

For developers or users who prefer running from source:

#### Prerequisites

- [Miniforge](https://github.com/conda-forge/miniforge) or Miniconda
- Python 3.11

#### Installation Steps

```bash
# 1. Create conda environment
conda create -n cad_env -c conda-forge python=3.11 \
    pyside6 pyvista pyvistaqt build123d ocp vtk \
    numpy scipy shapely ezdxf loguru trimesh \
    matplotlib pillow lib3mf

# 2. Activate environment
conda activate cad_env

# 3. Install ocp-tessellate (pip only)
pip install ocp-tessellate

# 4. Clone and run
git clone https://github.com/your-repo/MashCAD.git
cd MashCAD
python main.py
```

### Dependency Overview

MashCAD relies on these core libraries:

| Library | Purpose |
|---------|---------|
| **PySide6** | Qt-based user interface |
| **build123d** | Parametric CAD kernel (OpenCASCADE) |
| **PyVista** | 3D visualization and rendering |
| **VTK** | Low-level 3D graphics |
| **Shapely** | 2D geometry operations |
| **SciPy** | Constraint solver backend |
| **NumPy** | Numerical computations |

---

## First Launch Experience

### Initial Setup

When you first launch MashCAD:

1. **Language Selection** - Choose between English and German
2. **First Run Wizard** - Quick introduction to key features
3. **Default Workspace** - Opens with an empty project

### Creating Your First Project

```
[Screenshot placeholder: New Project dialog]
```

1. Click **File → New Project** or press `Ctrl+N`
2. Choose a project name and location
3. Select default units (mm, cm, inch)
4. Click **Create**

### Opening an Existing File

MashCAD supports opening these formats:

| Format | Import | Export |
|--------|--------|--------|
| **STEP** (.step, .stp) | ✅ | ✅ |
| **STL** (.stl) | ✅ | ✅ |
| **3MF** (.3mf) | ✅ | ✅ |
| **DXF** (.dxf) | ✅ | ✅ |
| **glTF** (.gltf, .glb) | ✅ | ✅ |

---

## UI Overview

MashCAD's interface is designed for efficient CAD workflows with three main areas:

```
[Screenshot placeholder: Full UI with labeled regions]
```

### 1. Viewport (3D View)

The central area displays your 3D model with real-time rendering.

| Element | Description |
|---------|-------------|
| **Grid** | Reference plane at Z=0 |
| **Axis Triad** | Orientation indicator (X=Red, Y=Green, Z=Blue) |
| **View Cube** | Click faces to orient view |
| **Status Bar** | Coordinates, selection info, messages |

### 2. Browser Panel (Left)

Hierarchical view of your design:

```
[Screenshot placeholder: Browser panel]
```

| Section | Content |
|---------|---------|
| **Bodies** | 3D solid objects |
| **Sketches** | 2D sketch definitions |
| **Features** | Operations history |
| **Constraints** | Sketch constraints list |

**Browser Actions:**
- **Click** - Select item
- **Double-click** - Edit/rename
- **Right-click** - Context menu
- **Drag** - Reorder items

### 3. Tool Panels (Right)

Context-sensitive tool panels:

```
[Screenshot placeholder: Tool panels]
```

| Panel | Available Tools |
|-------|-----------------|
| **Sketch Tools** | Line, Rectangle, Circle, Arc, Polygon, Slot, Spline |
| **Modify Tools** | Trim, Extend, Offset, Fillet, Chamfer |
| **Pattern Tools** | Linear Pattern, Circular Pattern, Mirror |
| **3D Tools** | Extrude, Fillet, Chamfer, Shell, Hole, Thread |
| **Transform** | Move, Rotate, Scale (G/R/S shortcuts) |

### 4. Property Panel (Bottom)

Displays and edits properties of selected items:

- **Transform** - Position, rotation, scale
- **Dimensions** - Size parameters
- **Material** - Color, appearance
- **Constraints** - Constraint values

---

## Basic Navigation

### Mouse Controls

| Action | Mouse | Result |
|--------|-------|--------|
| **Orbit** | Middle button + drag | Rotate view around model |
| **Pan** | Middle button + Shift + drag | Move view horizontally |
| **Zoom** | Scroll wheel | Zoom in/out |
| **Select** | Left click | Select object/face/edge |
| **Multi-select** | Left click + Ctrl | Add to selection |
| **Box select** | Left drag (empty space) | Select multiple items |

### View Presets

Access standard views from the toolbar or keyboard:

| View | Shortcut | Description |
|------|----------|-------------|
| **Front** | `1` (Numpad) | View from +Y direction |
| **Back** | `Ctrl+1` | View from -Y direction |
| **Top** | `7` (Numpad) | View from +Z direction |
| **Bottom** | `Ctrl+7` | View from -Z direction |
| **Left** | `3` (Numpad) | View from -X direction |
| **Right** | `Ctrl+3` | View from +X direction |
| **Isometric** | `5` (Numpad) | 3D isometric view |
| **Home** | `Home` | Reset to default view |
| **Fit All** | `F` | Fit entire model in view |

### Navigation Bar

```
[Screenshot placeholder: Navigation toolbar]
```

The navigation bar at the bottom provides:

- **Zoom slider** - Quick zoom control
- **View presets** - One-click view orientation
- **Projection toggle** - Switch perspective/orthographic
- **Show/hide grid** - Toggle grid visibility
- **Show/hide axes** - Toggle coordinate axes

---

## Tips & Best Practices

### Performance Tips

1. **Use orthographic mode** for precise modeling
2. **Hide unused bodies** to reduce rendering load
3. **Simplify sketches** - fewer constraints solve faster
4. **Use STEP format** for interoperability (preserves geometry)

### Workflow Tips

1. **Start with sketches** - Define 2D profiles before 3D operations
2. **Name your features** - Helps with complex designs
3. **Save frequently** - Use `Ctrl+S` often
4. **Use the browser** - Organize and track your design hierarchy

### Common Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New project |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save project |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Delete` | Delete selected |
| `H` | Hide/Show selected |
| `G` | Move (Grab) |
| `R` | Rotate |
| `S` | Scale |
| `Tab` | Numeric input mode (in sketch) |
| `Space` | 3D peek (in sketch) |
| `Escape` | Cancel current operation |

### Troubleshooting

#### Application Won't Start

```bash
# Check Python version (requires 3.11)
python --version

# Verify dependencies
pip list | grep -E "PySide6|pyvista|build123d"

# Try clean reinstall
conda env remove -n cad_env
conda create -n cad_env -c conda-forge python=3.11 pyside6 pyvista pyvistaqt build123d ocp vtk numpy scipy shapely ezdxf loguru trimesh matplotlib pillow lib3mf
```

#### 3D View Not Rendering

1. Update GPU drivers
2. Check OpenGL version: `glxinfo | grep "OpenGL version"`
3. Try software rendering: Set environment variable `MESA_GL_VERSION_OVERRIDE=3.3`

#### Boolean Operations Failing

- Ensure meshes are manifold (no holes)
- Check for self-intersections
- Try slightly overlapping volumes (avoid coplanar faces)

---

## Next Steps

Now that you're familiar with the basics, continue with:

- **[Sketch Workflow](02_sketch_workflow.md)** - Learn to create 2D profiles
- **[3D Operations](03_3d_operations.md)** - Transform sketches into 3D models
- **[Export & Import](04_export_import.md)** - Work with external files
- **[Keyboard Shortcuts](05_keyboard_shortcuts.md)** - Master efficiency shortcuts

---

## Getting Help

- **Documentation:** This user guide
- **Issues:** [GitHub Issues](../../issues)
- **Discussions:** [GitHub Discussions](../../discussions)
- **License:** MIT - Free to use and modify

---

*Last updated: February 2026 | MashCAD v0.3.0*
