# MashCAD V1 Known Limitations

## Overview

This document provides transparent information about known limitations in MashCAD V1. We believe in setting honest expectations - this helps you understand what V1 can and cannot do, and plan your workflows accordingly.

**Last Updated:** February 2026  
**Version:** V1.0

---

## Feature Limitations

### Assembly System

**Limitation:** Basic mates only - no complex constraint system

V1 supports fundamental assembly mates:
- Coincident (face-to-face, edge-to-edge)
- Distance (fixed offset between faces)
- Angle (fixed angle between faces)

Not supported:
- Gear/rack mates
- Cam followers
- Path constraints
- Limit mates (min/max ranges)
- Motion studies

**Workaround:** For complex mechanisms, use multiple simple mates to approximate the constraint. Export sub-assemblies as STEP and re-import as static geometry if needed.

**Planned for V2:** Yes - full constraint solver with motion studies is a V2 priority.

---

### Sketcher

**Limitation:** Limited spline constraint solving

V1 supports two types of splines:
- **Bézier Splines** (`BezierSpline`): Interactive splines with control points and tangent handles (Fusion360-style)
- **B-Splines** (`Spline2D`): Native NURBS curves imported from DXF files

However, the py-slvs constraint solver does not support spline geometry. This means:
- Spline control points cannot be fully constrained
- Spline-to-geometry constraints (tangent to spline, point on spline) are limited
- Complex sketches with splines may not solve correctly

**Workaround:**
- Use the scipy fallback solver for sketches containing splines
- Manually position spline control points before adding other constraints
- Import complex spline profiles from DXF rather than creating interactively

**Planned for V2:** Yes - full spline constraint support with py-slvs integration.

---

**Limitation:** Limited constraint types

Available constraints:
- Distance
- Angle
- Horizontal/Vertical
- Perpendicular
- Parallel
- Coincident
- Concentric (circles/arcs)
- Equal (length/radius)

Not available:
- Symmetry constraint
- Pattern constraint
- Fix/Ground constraint (partial - works differently than expected)
- Tangent to curve (arc-line tangent works)

**Workaround:** Use construction geometry and equal constraints to achieve symmetry. Ground elements by fully constraining their position with dimension constraints.

**Planned for V2:** Yes - symmetry and additional constraint types planned.

---

### 3D Operations

**Limitation:** No multi-body loft

Loft operations require a single profile per plane. You cannot loft between multiple separate profiles in one operation.

**Workaround:** Create separate loft features for each profile set, then use Boolean union to combine.

**Planned for V2:** Yes - multi-profile loft with guide curves.

---

**Limitation:** Limited sweep paths

Sweep operations support:
- Single continuous path curves
- Circular profiles
- Rectangular profiles

Limitations:
- No guide curves
- No twist control
- No scaling along path
- No multiple profiles (loft-like sweep)

**Workaround:** For variable cross-sections, use multiple sweeps with different profiles and blend with lofts or fillets.

**Planned for V2:** Partial - guide curves and twist control planned.

---

**Limitation:** No surface modeling

V1 is a solid-only modeler. Surface operations available:
- None (surfaces only exist as faces of solids)

You cannot:
- Create standalone surfaces
- Trim/extend surfaces
- Thicken surfaces to solids
- Unroll/flatten surfaces

**Workaround:** Model thin solids directly. For sheet metal workflows, use constant-thickness extrusions.

**Planned for V2:** Yes - basic surface modeling planned.

---

### Import

**Limitation:** No direct SolidWorks/Inventor/Fusion import

V1 cannot open native CAD files from:
- SolidWorks (.sldprt, .sldasm)
- Autodesk Inventor (.ipt, .iam)
- Fusion 360 (.f3d)
- CATIA (.CATPart, .CATProduct)
- NX (.prt)
- Creo/Pro-E (.prt, .asm)

**Workaround:** Export from source CAD as STEP or IGES, then import into MashCAD. Most CAD systems support STEP AP214 which preserves assembly structure and colors.

**Supported Import Formats:**
- STEP (.step, .stp) - AP203, AP214
- IGES (.iges, .igs)
- STL (.stl) - as mesh (limited editing)
- BREP (.brep) - native OCCT format
- DXF (.dxf) - 2D sketches only

**Planned for V2:** No - native format reverse-engineering is not planned. Focus on STEP interoperability.

---

### Export

**Limitation:** No Parasolid export

V1 cannot export to Parasolid (.x_t, .x_b) format, which is used by:
- SolidWorks
- Siemens NX
- Fusion 360

**Workaround:** Use STEP export, which is universally supported. For mesh workflows, use STL or 3MF.

**Supported Export Formats:**
- STEP (.step, .stp) - AP203, AP214
- STL (.stl) - ASCII and binary
- 3MF (.3mf) - for 3D printing
- glTF (.gltf, .glb) - for visualization
- OBJ (.obj) - mesh format
- BREP (.brep) - native OCCT format

**Planned for V2:** No - Parasolid is a proprietary format. STEP remains the recommended exchange format.

---

## Performance Limitations

### Body Count

**Limitation:** Recommended maximum ~50 bodies for smooth interaction

Performance characteristics:
- 1-20 bodies: Fully responsive
- 20-50 bodies: Minor delays on complex operations
- 50-100 bodies: Noticeable delays, especially in assembly mode
- 100+ bodies: Significant delays, consider simplification

**Workaround:** 
- Use components to organize bodies hierarchically
- Hide bodies not currently being edited
- Use "display as bounding box" for reference geometry
- Split large assemblies into sub-assemblies

**Planned for V2:** Yes - performance improvements targeting 200+ bodies.

---

### Sketch Complexity

**Limitation:** ~100 elements before performance degrades

A "sketch element" is:
- Line, arc, or circle segment
- Each constraint counts as processing overhead

Symptoms of overloaded sketches:
- Delayed constraint solving (>100ms)
- Laggy cursor during sketching
- Slow selection response

**Workaround:**
- Split complex profiles into multiple sketches
- Use construction geometry sparingly
- Delete unused constraints
- Fully constrain sketches early (easier to solve)

**Planned for V2:** Yes - optimized solver targeting 500+ elements.

---

### File Size

**Limitation:** Files >100MB may cause memory issues

Large file symptoms:
- Slow file open/save
- Increased memory usage (>4GB RAM)
- Potential crashes on low-memory systems

Common causes of large files:
- High-resolution meshes imported from STL
- Complex assemblies with many instances
- Large numbers of fillet/chamfer features

**Workaround:**
- Simplify imported meshes before import
- Use component instancing for repeated geometry
- Periodically use "compact" or "rebuild" to clean up internal data

**Planned for V2:** Partial - streaming/paging for large files is under consideration.

---

## Platform Limitations

### Operating System

| OS | Support Level | Notes |
|----|---------------|-------|
| Windows 10/11 | **Primary** | Fully tested, recommended |
| Linux (Ubuntu 22.04+) | **Supported** | Build pipeline available |
| macOS | **Supported** | Build pipeline available |

**Linux Known Issues:**
- Some display managers cause flickering
- Wayland not fully supported (use X11)
- Font rendering may differ
- File dialogs may have quirks

**macOS Known Issues:**
- Apple Silicon (M1/M2/M3) may require Rosetta for some dependencies
- Xcode command line tools required for compilation

**Workaround (Linux):** Use X11 session, report issues with system details.

**Workaround (macOS):** Use conda-forge for ARM64 packages, or Rosetta for x86_64 compatibility.

**Planned for V2:** Platform support will continue to be improved across all platforms.

---

### GPU Requirements

**Minimum:** OpenGL 3.3 compatible GPU

**Limitation:** No software fallback

If your GPU doesn't support OpenGL 3.3:
- Application will not start
- No software rendering fallback

**Tested GPUs:**
- NVIDIA: GTX 700 series and newer
- AMD: RX 400 series and newer
- Intel: HD 4000 and newer (integrated)

**Workaround:** None - a compatible GPU is required. Check your GPU drivers are up to date.

**Planned for V2:** No - OpenGL 3.3 is a hard requirement for the rendering pipeline.

---

### Python Version

**Supported:** Python 3.10, 3.11, 3.12

**Not Supported:**
- Python 3.9 and earlier
- Python 3.13+ (not yet tested)

**Workaround:** Use pyenv or conda to install a supported Python version.

**Planned for V2:** Python 3.13 support will be added after upstream dependency validation.

---

## Known Bugs

### Sketch Plane Y-Direction Bug

**Issue:** `plane_y_dir` becomes (0, 0, 0)

When creating sketches on certain planes, the Y-direction vector may be incorrectly calculated as zero, causing:
- Incorrect sketch orientation
- Geometry appearing in wrong location
- Transform errors

**Status:** Workaround implemented

**Workaround:** The system automatically detects and corrects this condition. If you encounter sketch orientation issues:
1. Check the sketch plane definition
2. Manually specify X and Y directions if needed
3. Report the specific steps that triggered the issue

**Related Code:** 
- [`modeling/__init__.py`](../modeling/__init__.py) - lines 1526-1527
- [`sketcher/sketch.py`](../sketcher/sketch.py)
- [`gui/main_window.py`](../gui/main_window.py) - lines 2684-2708

**Planned Fix:** V1.1 - Root cause investigation ongoing.

---

### TNP Failures on Complex Topology

**Issue:** Topology Naming Protocol (TNP) may fail on complex changes

TNP tracks faces/edges through modeling operations. It may fail when:
- Multiple Boolean operations on same body
- Complex fillet patterns
- Dramatic geometry changes (e.g., shell after many features)

Symptoms:
- Face references become invalid
- Features fail to regenerate
- "Face not found" errors

**Workaround:**
- Avoid deep feature trees on single body
- Use "recompute" to rebuild from scratch
- Reference stable features (base planes, axes) when possible

**Planned Fix:** V2 - TNP system redesign planned.

---

### Boolean Edge Cases with Coplanar Faces

**Issue:** Boolean operations may fail with coplanar faces

When performing Boolean operations (union, subtract, intersect) on bodies with coplanar faces:
- Operation may fail silently
- Result may have invalid geometry
- Tessellation artifacts may appear

**Workaround:**
- Offset faces slightly (0.001mm) to avoid exact coplanarity
- Use "heal geometry" after Boolean if issues occur
- Check result with geometry validation

**Feature Flags (Debug):**
```python
"boolean_self_intersection_check": True
"boolean_post_validation": True
"boolean_argument_analyzer": True
```

**Planned Fix:** V1.1 - Improved coplanar face handling in progress.

---

### Intermittent Selection Issues

**Issue:** Occasional failure to select faces/edges in complex models

In models with many overlapping faces or edges:
- Click may not register
- Wrong element selected
- Selection highlight delayed

**Workaround:**
- Rotate view to reduce overlap
- Use "select by type" filter
- Zoom in for precision selection
- Hide interfering bodies

**Planned Fix:** V1.1 - Selection algorithm improvements.

---

## Not Planned for V1

The following features are explicitly out of scope for V1:

### Cloud Collaboration
- No cloud storage integration
- No real-time collaboration
- No shared workspaces
- No cloud-based rendering

**V2 Status:** Under evaluation - depends on infrastructure decisions.

---

### Plugin/Extension System
- No third-party plugin support
- No scripting API beyond Python console
- No custom toolbar/panel extensions

**V2 Status:** Planned - plugin architecture is a V2 priority.

---

### Mobile/Tablet Support
- No iOS app
- No Android app
- No touch-optimized interface
- No mobile file sync

**V2 Status:** Not planned - desktop focus continues.

---

### Real-time Collaboration
- No simultaneous multi-user editing
- No presence indicators
- No change tracking
- No conflict resolution

**V2 Status:** Not planned - requires significant infrastructure.

---

### Version Control Integration
- No Git integration
- No built-in diff viewer
- No version history UI
- No branching/merging

**Workaround:** Use external Git for .mashcad files (they are JSON-based and version-control friendly).

**V2 Status:** Under consideration - basic Git integration possible.

---

### Rendering & Visualization
- No photorealistic rendering
- No ray tracing
- No environment/hdr lighting
- No material library beyond basics

**V2 Status:** Basic rendering improvements planned; photorealism not in scope.

---

### Simulation & Analysis
- No FEA (finite element analysis)
- No CFD (computational fluid dynamics)
- No motion simulation
- No thermal analysis

**V2 Status:** Not planned - focus remains on CAD modeling.

---

## Troubleshooting Resources

For issues not covered here:

1. **Check Feature Flags:** [`config/feature_flags.py`](../config/feature_flags.py)
2. **Run Diagnostics:** `scripts/gate_core.ps1` for core validation
3. **Performance Issues:** `scripts/gate_performance.ps1` for benchmarking
4. **Report Bugs:** Include system info, steps to reproduce, and sample files

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 2026 | Initial limitations document |

---

## Feedback

Found an inaccuracy or have a suggestion for this document? Please open an issue with the label `documentation` and reference this file.
