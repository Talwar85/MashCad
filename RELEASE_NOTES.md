# MashCAD V1.0.0 Release Notes

**Release Date:** February 2026  
**Codename:** "Foundation"  
**Status:** Production Ready

---

## 🎯 Highlights

MashCAD V1 delivers a complete parametric CAD experience powered by an OCP-First architecture. Here are the top features:

### 1. OCP-First CAD Kernel
Direct OpenCASCADE (OCP) integration for robust 3D modeling operations. All core operations bypass abstraction layers and use OCP primitives directly, ensuring maximum reliability and performance.

### 2. Parametric Modeling with TNP
Full parametric modeling with Topology Naming Protocol (TNP) for persistent face/edge tracking through modeling operations. Edit any feature in the history tree and watch downstream features update correctly.

### 3. Multi-format Export
Professional-grade export capabilities:
- **STEP** (AP203/AP214) - For CAD interoperability
- **STL** (ASCII/Binary) - For 3D printing
- **3MF** - For additive manufacturing workflows
- **glTF** - For web visualization and AR/VR
- **OBJ** - For rendering pipelines
- **DXF** - For 2D drawings

### 4. Integrated Sketcher with Constraint Solver
Full-featured 2D sketcher with:
- Geometric constraints (horizontal, vertical, parallel, perpendicular, tangent, coincident, concentric)
- Dimensional constraints (distance, angle, radius)
- Multiple solver backends (py-slvs for SolveSpace integration, scipy fallback)
- Real-time constraint diagnostics with actionable guidance

### 5. Printability Trust Gate
Built-in validation for 3D printing workflows:
- Mesh analysis for non-manifold geometry
- Wall thickness validation
- Export validation before slicing

---

## ✨ New Features

### Modeling

| Feature | Description |
|---------|-------------|
| **Extrude** | Convert 2D sketches to 3D solids with symmetric/to-next/tapered options |
| **Fillet** | Round edges with variable radius support |
| **Chamfer** | Bevel edges with equal/distance-angle modes |
| **Shell** | Hollow solids with specified wall thickness |
| **Sweep** | Create solids by sweeping profiles along paths |
| **Loft** | Blend between multiple profiles |
| **Revolve** | Create solids by revolving profiles around axes |
| **Boolean Operations** | Union, Subtract, Intersect with robust edge case handling |
| **Push/Pull** | Direct face manipulation for intuitive editing |
| **Draft** | Apply taper to faces for mold design |
| **Hole** | Create standardized holes (simple, counterbore, countersink) |
| **Thread** | Add cosmetic or real threads to cylindrical faces |
| **Pattern** - Linear/Circular | Repeat features in patterns |
| **Mirror** | Mirror features across planes |

### Sketcher

| Feature | Description |
|---------|-------------|
| **Drawing Tools** | Line, Rectangle, Circle (3 modes), Arc, Polygon, Slot, Spline, Bézier |
| **Editing Tools** | Move, Copy, Rotate, Mirror, Scale, Offset |
| **Modify Tools** | Trim, Extend, Fillet, Chamfer |
| **Constraints** | Horizontal, Vertical, Parallel, Perpendicular, Equal, Concentric, Tangent, Coincident |
| **Dimensions** | Distance, Angle, Radius with live preview |
| **Generators** | Involute Gear, Star, Hex Nut |
| **Precision Input** | Tab for numeric entry with smart snapping |

### Import

| Format | Capability |
|--------|------------|
| **STEP** (.step, .stp) | Full BREP import with assembly structure |
| **IGES** (.iges, .igs) | Surface and wireframe import |
| **STL** (.stl) | Mesh-to-BREP conversion for editing |
| **DXF** (.dxf) | 2D sketch import with constraint preservation |
| **BREP** (.brep) | Native OCCT format for lossless transfer |

### Export

| Format | Options |
|--------|---------|
| **STEP** | AP203, AP214 with color and metadata |
| **STL** | ASCII and Binary with quality settings |
| **3MF** | With units and material properties |
| **glTF** | GLB binary and GLTF+bin for web |
| **OBJ** | With MTL material library |
| **DXF** | 2D projections and flat patterns |
| **BREP** | Native OCCT for round-trip editing |

### Assembly

- Basic component system with hierarchical organization
- Mate types: Coincident, Distance, Angle
- Component instancing for repeated geometry
- Assembly tree visualization

### User Experience

| Feature | Description |
|---------|-------------|
| **First-Run Tutorial** | Guided introduction to core workflows |
| **Error Explanations** | Clear error messages with "Next Steps" guidance |
| **Discoverability Hints** | Contextual tips for learning shortcuts |
| **Transform Gizmo** | Visual G/R/S manipulation in 3D (G=Move, R=Rotate, S=Scale) |
| **Viewport Modes** | Shaded, Wireframe, Hidden Line removal |
| **Multi-viewport** | Orthographic and perspective views |

---

## 🚀 Improvements

### Performance Optimizations
- **Actor Pooling**: Reusable VTK actors reduce memory allocation during editing
- **Async Tessellation**: Background mesh generation keeps UI responsive
- **Picker Pooling**: Efficient selection handling for complex assemblies
- **BBOX Early Rejection**: Fast culling during picking operations
- **Export Caching**: Incremental export for repeated operations
- **Feature Dependency Tracking**: Minimal rebuilds on feature edits

### Error Diagnostics
- Constraint diagnostics with degrees-of-freedom analysis
- Boolean operation failure analysis with suggestions
- Geometry validation with repair recommendations
- Actionable "Next Steps" in all error dialogs

### Cross-Platform CI
- Windows and Linux CI pipelines
- Automated quality gates (Core-Gate, UI-Gate, Hygiene-Gate)
- Regression corpus for stability testing
- Visual acceptance testing framework

### Developer Experience
- Comprehensive API documentation ([`docs/api/`](docs/api/))
- Architecture documentation ([`docs/architecture.md`](docs/architecture.md))
- Feature flags for experimental features ([`config/feature_flags.py`](config/feature_flags.py))

---

## ⚠️ Known Limitations

V1 has documented limitations to set honest expectations. See the complete list at [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

### Key Limitations Summary

| Area | Limitation |
|------|------------|
| **Assembly** | Basic mates only - no motion studies or complex constraints |
| **Sketcher** | Limited spline constraint solving |
| **Modeling** | No surface modeling, no multi-body loft |
| **Import** | No direct SolidWorks/Fusion/Inventor files (use STEP) |
| **Performance** | Recommended max ~50 bodies for smooth interaction |
| **Platform** | macOS supported via build pipeline; Linux supported |

---

## 💥 Breaking Changes

### Requirements Changes
- **Python 3.10+ required** (Python 3.9 and earlier no longer supported)
- **OCP dependency required** (OpenCASCADE Python wrapper - no fallback)

### API Changes
- All modeling operations now use OCP-First helpers
- `BooleanEngineV4` replaces legacy boolean implementations
- Feature commands require `Body` objects (not raw geometry)

### File Format
- `.mashcad` files are JSON-based and backward compatible
- BREP cache format updated (old caches will be regenerated)

---

## 📋 Requirements

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **Python** | 3.10 | 3.11 or 3.12 |
| **RAM** | 8 GB | 16 GB |
| **GPU** | OpenGL 3.3 | OpenGL 4.5+ |
| **Storage** | 500 MB | 2 GB (with dependencies) |

### Supported Platforms

| Platform | Support Level | Notes |
|----------|---------------|-------|
| **Windows 10/11** | ✅ Primary | Fully tested, recommended |
| **Linux (Ubuntu 22.04+)** | ✅ Supported | Build pipeline available |
| **macOS 12+** | ✅ Supported | Build pipeline available |

### Dependencies

Core dependencies (installed via conda):
- `pyside6` - Qt GUI framework
- `pyvista` / `pyvistaqt` - 3D visualization
- `build123d` - Parametric CAD kernel
- `ocp` - OpenCASCADE Python wrapper
- `vtk` - Visualization Toolkit
- `numpy` / `scipy` - Numerical computing
- `shapely` - 2D geometry
- `ezdxf` - DXF file support
- `loguru` - Logging
- `trimesh` - Mesh processing
- `lib3mf` - 3MF file support
- `matplotlib` / `pillow` - Visualization utilities

Additional pip packages:
- `ocp-tessellate` - OCP mesh generation

---

## 👥 Contributors

### Core Team
MashCAD V1 was made possible by the dedication of contributors who believe in open-source CAD.

### Acknowledgments
- **[Build123d](https://github.com/gumyr/build123d)** - The foundation of our CAD kernel
- **[PyVista](https://github.com/pyvista/pyvista)** - 3D visualization made accessible
- **[OpenCASCADE](https://www.opencascade.com/)** - Industrial-grade geometry kernel
- **[SolveSpace](https://solvespace.com/)** - Constraint solver inspiration

---

## 🔮 Roadmap Preview (V2)

V2 will build on the solid foundation of V1 with these planned features:

### Advanced Assembly
- Full constraint solver with motion studies
- Gear/rack mates, cam followers, path constraints
- Limit mates with min/max ranges
- Interference detection

### Plugin System
- Third-party plugin architecture
- Scripting API for automation
- Custom toolbar/panel extensions
- Material and appearance libraries

### Cloud Collaboration
- Cloud storage integration
- Real-time co-viewing (not editing)
- Shared workspaces for teams
- Version history and commenting

### Enhanced Modeling
- Surface modeling (trim, extend, thicken)
- Multi-profile loft with guide curves
- Sheet metal workflows
- Improved TNP for complex topology

### Platform Expansion
- Improved Linux support
- Enhanced macOS support (Apple Silicon native)

---

## 📦 Installation

### From Release (Recommended)
Download pre-built executables from [Releases](../../releases):
- Windows x64
- Linux x86_64

### From Source
```bash
# Create conda environment
conda create -n mashcad -c conda-forge python=3.11 \
    pyside6 pyvista pyvistaqt build123d ocp vtk \
    numpy scipy shapely ezdxf loguru trimesh \
    matplotlib pillow lib3mf

conda activate mashcad
pip install ocp-tessellate

# Clone and run
git clone https://github.com/your-repo/MashCAD.git
cd MashCAD
python main.py
```

---

## 📝 Changelog

For a detailed list of all changes, see the commit history on the `feature/v1-roadmap-execution` branch.

### Sprint 4 Completion Summary
- ✅ CI Pipeline Green
- ✅ TNP Stability (16 tests passing)
- ✅ Feature Edit Robustness with undo/redo
- ✅ Test Coverage: 252+ new tests added
- ✅ API Documentation complete
- ✅ Release Notes (this document)

---

## 🐛 Reporting Issues

Found a bug? Have a suggestion?

1. Check [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) first
2. Search existing issues
3. Open a new issue with:
   - System information (OS, Python version, GPU)
   - Steps to reproduce
   - Expected vs actual behavior
   - Sample files if applicable

---

**Thank you for choosing MashCAD!** 🎉

*Built with ❤️ for the open-source CAD community.*
