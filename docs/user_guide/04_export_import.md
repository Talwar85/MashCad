# Export & Import

![Mesh Import](../../img/mesh_import.JPG)

MashCAD supports multiple file formats for exchanging designs with other CAD systems, 3D printers, and visualization tools. This guide covers all export and import workflows.

---

## Table of Contents

1. [Supported Formats](#supported-formats)
2. [Export Workflow](#export-workflow)
3. [Import Workflow](#import-workflow)
4. [Printability Check](#printability-check)
5. [Tips & Best Practices](#tips--best-practices)

---

## Supported Formats

### Export Formats

| Format | Extension | Description | Use Case |
|--------|-----------|-------------|----------|
| **STL** | `.stl` | Standard Tessellation Language | 3D printing, mesh processing |
| **STEP** | `.step`, `.stp` | ISO 10303 (AP214/AP242) | CAD interchange, manufacturing |
| **3MF** | `.3mf` | 3D Manufacturing Format | Modern 3D printing |
| **DXF** | `.dxf` | AutoCAD Drawing Exchange | 2D drawings, laser cutting |
| **OBJ** | `.obj` | Wavefront OBJ | Visualization, rendering |
| **PLY** | `.ply` | Polygon File Format | 3D scanning, point clouds |

### Import Formats

| Format | Extension | Description | Capabilities |
|--------|-----------|-------------|--------------|
| **STEP** | `.step`, `.stp` | ISO 10303 | Full B-Rep, assemblies |
| **STL** | `.stl` | Mesh format | Mesh-to-BREP conversion |
| **3MF** | `.3mf` | 3D Manufacturing | Mesh import |
| **OBJ** | `.obj` | Wavefront OBJ | Mesh import |
| **DXF** | `.dxf` | Drawing Exchange | 2D sketch import |

### Format Comparison

| Feature | STL | STEP | 3MF | OBJ |
|---------|-----|------|-----|-----|
| **Geometry Type** | Mesh | B-Rep | Mesh | Mesh |
| **Accuracy** | Approximate | Exact | Approximate | Approximate |
| **File Size** | Large | Compact | Compressed | Medium |
| **Colors/Materials** | ❌ | ❌ | ✅ | ✅ |
| **Units** | ❌ | ✅ | ✅ | ❌ |
| **CAD Compatible** | ❌ | ✅ | ⚠️ | ❌ |

---

## Export Workflow

### Quick Export

The fastest way to export your design:

1. **Select bodies** to export (or none for all visible)
2. Click **File → Export** or press `Ctrl+Shift+E`
3. Choose format and location
4. Click **Save**

### Export Dialog

```
[Screenshot placeholder: Export dialog]
```

#### Export Options

| Option | Description | Values |
|--------|-------------|--------|
| **Format** | Output file format | STL, STEP, 3MF, OBJ, PLY |
| **Quality** | Tessellation quality | Draft, Standard, Fine, Ultra |
| **Binary** | Binary vs ASCII format | Checkbox (STL only) |
| **Scale** | Unit conversion factor | 1.0 = mm, 0.03937 = inch |
| **Author** | STEP metadata | Text field |
| **Schema** | STEP protocol | AP214, AP242 |

### Quality Settings

| Quality | Linear Deflection | Angular Tolerance | Use Case |
|---------|-------------------|-------------------|----------|
| **Draft** | 0.1 mm | 0.5° | Quick previews |
| **Standard** | 0.05 mm | 0.3° | General use |
| **Fine** | 0.01 mm | 0.2° | 3D printing |
| **Ultra** | 0.005 mm | 0.1° | Precision parts |

### STL Export

STL is the most common format for 3D printing.

**Options:**
- **Binary:** Smaller file size (recommended)
- **ASCII:** Human-readable, larger files
- **Quality:** Higher = more triangles = smoother

**Example - Python Console:**

```python
from modeling.export_kernel import export_stl, ExportOptions, ExportQuality

# Quick export
export_stl([body], "/path/to/part.stl")

# With options
options = ExportOptions(
    quality=ExportQuality.FINE,
    binary=True
)
export_stl([body], "/path/to/part.stl", **options.__dict__)
```

### STEP Export

STEP preserves exact geometry for CAD interchange.

**Options:**
- **Schema:** AP214 (automotive) or AP242 (aerospace)
- **Author/Organization:** Metadata fields
- **Assembly:** Multiple bodies as assembly

**Example - Python Console:**

```python
from modeling.export_kernel import export_step, ExportOptions

options = ExportOptions(
    schema="AP242",
    author="Your Name",
    organization="Company"
)
export_step([body], "/path/to/part.step", **options.__dict__)
```

### 3MF Export

3MF is a modern format for additive manufacturing.

**Advantages over STL:**
- Compressed file size (ZIP-based)
- Unit information preserved
- Color and material support
- Extensible metadata

**Example - Python Console:**

```python
from modeling.export_kernel import export_3mf

export_3mf([body], "/path/to/part.3mf")
```

### Export Validation

Before export, MashCAD can validate your model:

1. **Geometry Check** - Valid solid detection
2. **Manifold Check** - Watertight mesh
3. **Printability Check** - 3D printing readiness

Enable validation in Export dialog: **☑ Validate before export**

---

## Import Workflow

### Quick Import

Import files into your current project:

1. Click **File → Import** or press `Ctrl+I`
2. Select file to import
3. Choose import options
4. Click **Open**

### Import Dialog

```
[Screenshot placeholder: Import dialog]
```

### STEP Import

STEP files import as exact B-Rep solids:

```
[Screenshot placeholder: STEP import options]
```

**Options:**
- **Heal Geometry:** Auto-fix common issues
- **Split Shells:** Separate disconnected solids
- **Units:** Override detected units

**Workflow:**
1. Import STEP file
2. Bodies appear in browser
3. Edit or add features as needed

### Mesh Import (STL/OBJ)

Mesh files require conversion to B-Rep:

![Mesh Converted](../../img/mesh_converted.JPG)

**Mesh-to-BREP Workflow:**

1. **Import mesh file** (STL, OBJ, 3MF)
2. **Analyze mesh** - Detect features
3. **Convert to B-Rep** - Create solid
4. **Refine** - Fix issues if needed

**Conversion Options:**

| Option | Description |
|--------|-------------|
| **Auto-detect Primitives** | Recognize planes, cylinders, spheres |
| **Fit Surfaces** | Create smooth surfaces from mesh |
| **Tolerance** | Mesh simplification level |

**Tips for Mesh Import:**
- High-quality meshes convert better
- Watertight meshes required
- Complex meshes may need manual cleanup

### DXF Import

Import 2D drawings as sketches:

1. **File → Import → DXF**
2. Select file
3. Choose import plane
4. Sketch created from geometry

**Supported DXF entities:**
- Lines
- Arcs
- Circles
- Polylines
- Splines

---

## Printability Check

Before 3D printing, validate your model with the Printability Trust Gate.

### Accessing Printability Check

1. **Select body** to check
2. Click **Tools → Printability Check**
3. Or use **Export dialog** validation

### Printability Report

```
[Screenshot placeholder: Printability report dialog]
```

### Check Categories

| Category | Checks | Weight |
|----------|--------|--------|
| **Manifold** | Watertight, no holes | 30% |
| **Normals** | Consistent orientation | 20% |
| **Wall Thickness** | Minimum printable thickness | 25% |
| **Overhangs** | Unsupported areas | 15% |
| **Geometry** | Valid B-Rep | 10% |

### Status Levels

| Status | Score | Action |
|--------|-------|--------|
| ✅ **PASS** | 80-100 | Export allowed |
| ⚠️ **WARN** | 60-79 | Export with confirmation |
| ❌ **FAIL** | 0-59 | Export blocked |

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **Non-manifold** | Open edges, holes | Fix sketch, add caps |
| **Reversed normals** | Inside-out faces | Recalculate normals |
| **Thin walls** | Below min thickness | Increase wall size |
| **Overhangs** | >45° without support | Add support or redesign |

### Printability Settings

Configure thresholds in **Settings → Printability**:

| Setting | Default | Description |
|---------|---------|-------------|
| Min Overall Score | 60 | Minimum to pass |
| Min Wall Thickness | 0.8 mm | Printable minimum |
| Max Overhang Angle | 45° | Without support |
| Block on Critical | True | Block export on errors |

### Python API

```python
from modeling.printability_gate import check_printability, is_printable

# Quick check
if is_printable(solid):
    print("Model is printable!")
else:
    # Detailed check
    result = check_printability(solid)
    print(f"Score: {result.score.overall_score}")
    for issue in result.blocking_issues:
        print(f"  ❌ {issue.message}")
    for issue in result.warning_issues:
        print(f"  ⚠️ {issue.message}")
```

---

## Tips & Best Practices

### Export Tips

1. **Use STEP for CAD** - Preserves exact geometry
2. **Use 3MF for printing** - Better than STL
3. **Check quality settings** - Balance size vs accuracy
4. **Validate before export** - Catch issues early
5. **Name files clearly** - Include version/revision

### Import Tips

1. **Prefer STEP files** - Best geometry preservation
2. **Clean meshes before import** - Remove errors
3. **Check units** - Verify scale after import
4. **Simplify complex meshes** - Easier conversion
5. **Save after import** - Before making changes

### 3D Printing Workflow

```
1. Design part in MashCAD
2. Run Printability Check
3. Fix any issues
4. Export as 3MF or STL
5. Slice in printer software
6. Print
```

### CAD Collaboration

```
1. Export as STEP (AP242)
2. Include metadata (author, organization)
3. Share file
4. Recipient imports STEP
5. Continues editing
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| Export fails | Check for invalid geometry |
| File too large | Reduce quality setting |
| Mesh won't convert | Clean mesh in external tool |
| Wrong scale | Check unit settings |
| Missing faces | Run geometry validation |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+E` | Export |
| `Ctrl+I` | Import |
| `Ctrl+S` | Save project |
| `Ctrl+Shift+S` | Save As |

---

## Next Steps

Continue exploring MashCAD:

- **[Keyboard Shortcuts](05_keyboard_shortcuts.md)** - Master all shortcuts
- **[3D Operations](03_3d_operations.md)** - Learn modeling features
- **[Getting Started](01_getting_started.md)** - Review basics

---

*Last updated: February 2026 | MashCAD v0.3.0*
