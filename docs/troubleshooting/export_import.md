# Export/Import Troubleshooting Guide

This guide covers common file export and import issues in MashCAD, including STEP, STL, glTF, and3MF formats.

## Table of Contents

1. [Export Failures](#export-failures)
2. [STL Mesh Quality Issues](#stl-mesh-quality-issues)
3. [STEP File Compatibility](#step-file-compatibility)
4. [Import Failures](#import-failures)
5. [Printability Check Failures](#printability-check-failures)
6. [Error Messages Reference](#error-messages-reference)

---

## Export Failures

### Symptoms
- "Export failed" error message
- Exported file is empty or corrupt
- Export takes extremely long
- Application crashes during export

### Root Causes

#### 1. Invalid Geometry for Export

**Diagnosis:**
```python
from modeling.export_validator import validate_for_export
result = validate_for_export(body, format="STEP")
if not result.valid:
    for issue in result.issues:
        print(f"Severity {issue.severity}: {issue.description}")
        print(f"  Location: {issue.location}")
```

**Common Issues:**
- Non-manifold geometry
- Open shells (not closed solids)
- Self-intersecting surfaces
- Degenerate faces (zero area)
- Invalid edge ordering

**Solution:**
```python
# Run geometry healing before export
from modeling.geometry_healer import heal_for_export
healed_body = heal_for_export(body, target_format="STEP")

# Validate after healing
result = validate_for_export(healed_body, format="STEP")
print(f"Ready for export: {result.valid}")
```

#### 2. Export Path Issues

**Problem:** Invalid file path or insufficient permissions

**Diagnosis:**
```python
import os
path = "/path/to/export.step"
print(f"Directory exists: {os.path.exists(os.path.dirname(path))}")
print(f"Writable: {os.access(os.path.dirname(path), os.W_OK)}")
print(f"File exists: {os.path.exists(path)}")
```

**Solution:**
- Ensure directory exists and is writable
- Check for file name conflicts
- Avoid special characters in file name

#### 3. Memory Issues During Export

**Problem:** Complex models exceed available memory

**Diagnosis:**
```python
# Estimate export memory requirements
from modeling.export_kernel import estimate_export_memory
estimate = estimate_export_memory(body, format="STL", mesh_quality="high")
print(f"Estimated memory: {estimate.mb} MB")
print(f"Available memory: {estimate.available_mb} MB")
```

**Solution:**
- Reduce mesh quality for STL exports
- Export assemblies as individual parts
- Enable export caching:
  ```python
  from config.feature_flags import set_flag
  set_flag("export_cache", True)
  ```

#### 4. Tessellation Failures

**Problem:** Cannot generate mesh from B-Rep geometry

**Solution:**
```python
# Use CAD tessellator with fallback
from modeling.cad_tessellator import tessellate_with_fallback
mesh, success = tessellate_with_fallback(
    body,
    linear_deflection=0.1,
    angular_deflection=0.5
)
if not success:
    print("Tessellation required simplification")
```

---

## STL Mesh Quality Issues

### Symptoms
- STL file has visible facets/triangles
- Mesh has holes or non-manifold edges
- File size is too large
- 3D printer software rejects the file

### Root Causes

#### 1. Low Mesh Resolution

**Problem:** Triangle size too large, visible facets

**Solution:**
```python
from modeling.export_kernel import export_stl

# Increase mesh quality
export_stl(
    body,
    filepath="output.stl",
    linear_deflection=0.01,  # Smaller = more triangles
    angular_deflection=0.1,  # Smaller = smoother curves
    binary=True  # Smaller file size
)
```

**Quality Presets:**

| Preset | Linear Deflection | Angular Deflection | Use Case |
|--------|-------------------|-------------------|----------|
| Draft | 1.0 | 1.0 | Preview, testing |
| Standard | 0.1 | 0.5 | General use |
| High | 0.01 | 0.1 | Final output |
| Production | 0.005 | 0.05 | 3D printing |

#### 2. Non-Manifold Mesh

**Problem:** Mesh has edges shared by more than 2 triangles

**Diagnosis:**
```python
from modeling.mesh_repair import analyze_mesh
analysis = analyze_mesh(stl_mesh)
print(f"Non-manifold edges: {analysis.non_manifold_edges}")
print(f"Holes: {analysis.holes}")
print(f"Inverted normals: {analysis.inverted_normals}")
```

**Solution:**
```python
from modeling.mesh_repair import repair_mesh
repaired = repair_mesh(
    stl_mesh,
    fix_holes=True,
    fix_normals=True,
    remove_duplicates=True
)
```

#### 3. Incorrect Mesh Orientation

**Problem:** Normals point inward, causing printability issues

**Solution:**
```python
from modeling.mesh_repair import fix_normals
fixed_mesh = fix_normals(stl_mesh, consistent_outward=True)
```

#### 4. File Size Too Large

**Problem:** STL file exceeds size limits

**Solutions:**
1. Use binary STL format (10x smaller than ASCII)
2. Reduce mesh resolution
3. Use decimation:
   ```python
   from modeling.mesh_repair import decimate_mesh
   reduced = decimate_mesh(stl_mesh, target_reduction=0.5)  # 50% fewer triangles
   ```

---

## STEP File Compatibility

### Symptoms
- STEP file won't open in other CAD software
- Geometry appears distorted after import
- Colors/metadata lost
- "Invalid STEP file" errors

### Root Causes

#### 1. STEP Version Incompatibility

**Problem:** Different STEP versions (AP203, AP214, AP242)

**Solution:**
```python
from modeling.export_kernel import export_step

# Use AP214 for broad compatibility
export_step(
    body,
    filepath="output.step",
    schema="AP214",  # Options: AP203, AP214, AP242
    write_colors=True,
    write_layers=True
)
```

**STEP Version Comparison:**

| Version | Features | Compatibility |
|---------|----------|---------------|
| AP203 | Basic geometry | Universal |
| AP214 | + Colors, layers, materials | Most CAD software |
| AP242 | + Tessellation, PMI, tessellation | Modern CAD (2015+) |

#### 2. Complex Geometry Issues

**Problem:** Advanced surfaces not supported in target format

**Solution:**
```python
# Convert complex surfaces to simpler types
from modeling.geometry_utils import simplify_for_step
simplified = simplify_for_step(body, max_degree=3)
export_step(simplified, "output.step")
```

#### 3. Unit Scale Issues

**Problem:** Model appears wrong size in other software

**Solution:**
```python
# Explicitly set units in STEP export
export_step(
    body,
    filepath="output.step",
    units="MM",  # MM, CM, M, IN, FT
    header_units=True
)
```

#### 4. Metadata Loss

**Problem:** Assembly structure or colors lost

**Solution:**
```python
# Preserve metadata
export_step(
    body,
    filepath="output.step",
    write_colors=True,
    write_layers=True,
    write_properties=True,
    assembly_structure=True
)
```

---

## Import Failures

### Symptoms
- "Failed to import file" error
- Imported geometry is incomplete
- Import takes extremely long
- Application crashes during import

### Root Causes

#### 1. Unsupported File Format

**Supported Formats:**

| Format | Extension | Import | Export |
|--------|-----------|--------|--------|
| STEP | .step, .stp | ✅ | ✅ |
| STL | .stl | ✅ | ✅ |
| glTF | .gltf, .glb | ✅ | ✅ |
| 3MF | .3mf | ✅ | ✅ |
| OBJ | .obj | ✅ | ❌ |
| IGES | .igs, .iges | ✅ | ❌ |
| BREP | .brep | ✅ | ✅ |

**Solution:**
- Convert file to supported format using external tool
- Check file extension matches content

#### 2. Corrupt or Invalid File

**Diagnosis:**
```python
from modeling.export_validator import validate_import_file
result = validate_import_file("input.step")
if not result.valid:
    print(f"File issues: {result.issues}")
```

**Solution:**
- Re-export from source application
- Try different STEP version
- Use file repair tools

#### 3. Complex Geometry Import

**Problem:** File contains very complex geometry

**Solution:**
```python
# Import with simplification
from meshconverter.mesh_converter import import_with_options
body = import_with_options(
    "complex.step",
    simplify=True,
    max_faces=100000,
    heal_geometry=True
)
```

#### 4. Memory Issues During Import

**Problem:** File too large to process

**Solution:**
- Import in parts if assembly
- Increase available memory
- Use streaming import for large files:
  ```python
  from modeling.export_kernel import import_step_streaming
  for part in import_step_streaming("large_assembly.step"):
      process(part)
  ```

---

## Printability Check Failures

### Symptoms
- "Model not printable" warning
- Printability check shows errors
- Slicer software rejects model

### Root Causes

#### 1. Non-Manifold Geometry

**Problem:** Model has edges shared by more than 2 faces

**Diagnosis:**
```python
from modeling.export_validator import check_printability
result = check_printability(body)
print(f"Manifold: {result.is_manifold}")
print(f"Non-manifold edges: {result.non_manifold_edges}")
```

**Solution:**
```python
from modeling.geometry_healer import heal_for_printing
healed = heal_for_printing(body, fix_non_manifold=True)
```

#### 2. Holes in Mesh

**Problem:** Model has gaps

**Solution:**
```python
from modeling.mesh_repair import find_and_fill_holes
max_hole_size = 1.0  # mm
repaired = find_and_fill_holes(body, max_hole_size=max_hole_size)
```

#### 3. Thin Features

**Problem:** Walls too thin for printing

**Diagnosis:**
```python
from modeling.export_validator import analyze_wall_thickness
analysis = analyze_wall_thickness(body, min_thickness=0.8)  # mm
print(f"Thin regions: {analysis.thin_regions}")
for region in analysis.thin_regions:
    print(f"  {region.location}: {region.thickness}mm")
```

**Solution:**
- Thicken thin walls in design
- Adjust print settings for thin features
- Consider material limitations

#### 4. Overhangs and Support Requirements

**Problem:** Geometry requires support material

**Diagnosis:**
```python
from modeling.export_validator import analyze_overhangs
analysis = analyze_overhangs(body, max_angle=45)  # degrees
print(f"Overhang areas: {analysis.overhang_areas}")
```

**Solution:**
- Redesign to reduce overhangs
- Orient model differently for printing
- Accept support material usage

#### 5. Model Size Issues

**Problem:** Model exceeds print volume

**Solution:**
```python
from modeling.geometry_utils import get_bounding_box
bbox = get_bounding_box(body)
print(f"Size: {bbox.width} x {bbox.depth} x {bbox.height} mm")

# Scale if needed
scaled = scale_body(body, factor=0.5)
```

---

## Error Messages Reference

### Export Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| EP-001 | "Invalid geometry for export" | Non-manifold or corrupt | Heal geometry |
| EP-002 | "Cannot write to path" | Permission denied | Check permissions |
| EP-003 | "Tessellation failed" | Cannot mesh geometry | Simplify geometry |
| EP-004 | "Memory allocation failed" | Model too complex | Reduce quality |
| EP-005 | "Unsupported format" | Unknown file extension | Use supported format |
| EP-006 | "Export timeout" | Operation too slow | Enable caching |

### STL Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| ST-001 | "Mesh has holes" | Non-closed mesh | Repair mesh |
| ST-002 | "Non-manifold edges detected" | Topology error | Heal geometry |
| ST-003 | "Inverted normals" | Wrong winding | Fix normals |
| ST-004 | "File size exceeds limit" | Too many triangles | Decimate mesh |
| ST-005 | "Degenerate triangles" | Zero-area faces | Clean mesh |

### STEP Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| SE-001 | "Invalid STEP schema" | Unsupported version | Use AP214 |
| SE-002 | "Geometry conversion failed" | Complex surfaces | Simplify |
| SE-003 | "Unit conversion error" | Unknown units | Specify units |
| SE-004 | "Assembly structure error" | Invalid hierarchy | Flatten assembly |

### Import Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| IM-001 | "File not found" | Invalid path | Check path |
| IM-002 | "Unsupported format" | Unknown extension | Convert format |
| IM-003 | "File corrupt" | Invalid data | Re-export source |
| IM-004 | "Import memory error" | File too large | Split file |
| IM-005 | "Geometry healing required" | Invalid topology | Auto-heal |

### Printability Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| PR-001 | "Non-manifold geometry" | Open or self-intersecting | Heal geometry |
| PR-002 | "Holes in mesh" | Gaps in surface | Fill holes |
| PR-003 | "Thin walls detected" | Below minimum thickness | Thicken walls |
| PR-004 | "Excessive overhangs" | Requires support | Redesign or orient |
| PR-005 | "Exceeds print volume" | Model too large | Scale or split |

---

## Debug Checklist

When experiencing export/import issues:

- [ ] Validate geometry before export
- [ ] Check file path and permissions
- [ ] Verify format compatibility
- [ ] Enable export caching for large models
- [ ] Run geometry healing on problematic bodies
- [ ] Check mesh quality settings
- [ ] Verify units are correct
- [ ] Test with simplified geometry

## Related Files

- [`modeling/export_kernel.py`](../../modeling/export_kernel.py) - Export/import core
- [`modeling/export_validator.py`](../../modeling/export_validator.py) - Validation tools
- [`modeling/cad_tessellator.py`](../../modeling/cad_tessellator.py) - Mesh generation
- [`modeling/mesh_repair.py`](../../modeling/mesh_repair.py) - Mesh repair tools
- [`modeling/geometry_healer.py`](../../modeling/geometry_healer.py) - Geometry healing
- [`meshconverter/`](../../meshconverter/) - Mesh conversion utilities

## Feature Flags for Export/Import

```python
from config.feature_flags import set_flag

# Export optimization
set_flag("export_cache", True)

# Validation
set_flag("export_validation", True)

# Debug
set_flag("export_debug", False)  # Enable for troubleshooting
```
