# CadQuery Import Examples for MashCad

This directory contains example Build123d scripts that can be imported into MashCad using the CadQuery Importer.

## How to Use

1. In MashCad, go to **File → Import → Import CadQuery Script...**
2. Select any `.py` file from this directory
3. The script will be executed and the resulting 3D model will appear as a new Body

## Examples

### Build123d Native Examples

### `bracket.py`
Simple mounting bracket with two holes. Demonstrates:
- Basic sketch creation
- Extrusion
- Boolean subtraction

### `parametric_knob.py`
Parametric knob design with grip fins. Demonstrates:
- Parameter-driven design
- Circular patterns
- Multiple boolean operations

### `flange_coupling.py`
Mechanical flange with bolt holes. Demonstrates:
- Circular hole patterns
- Cylindrical bores
- Trigonometric positioning

### CadQuery-Style Chaining (Phase 4)

### `workplane_box.py`
Box with filleted edges using chaining:
```python
# NO import needed - cq is pre-defined
result = cq.Workplane('XY').box(50, 30, 10).faces('>Z').fillet(2)
```

### `workplane_bracket.py`
Bracket demonstrating chained operations.

### `workplane_flange.py`
Flange using cylinder primitives.

## Writing Your Own Scripts

### Build123d Native (Recommended)

```python
import build123d as b

with b.BuildPart() as my_part:
    with b.BuildSketch(b.Plane.XY):
        b.Rectangle(10, 20)
    b.extrude(amount=5)
    b.fillet(my_part.edges(), radius=1)
```

### CadQuery-Style Chaining

MashCad provides `cq` object in the namespace:

```python
# NO import needed - cq is pre-defined
result = cq.Workplane('XY').box(10, 20, 30).faces('>Z').fillet(2)
```

**Supported:**
- `.box(l,w,h)`, `.cylinder(r,h)` - Primitives
- `.circle(r)` - Add circle (before extrude)
- `.extrude(d)` - Extrude sketch
- `.faces('>Z')`, `.edges('|Z')` - Selectors
- `.fillet(r)`, `.chamfer(d)` - Edge operations

**Selectors:**
- `'>Z'` - Positive Z, `'<Z'` - Negative Z, `'|Z'` - Parallel to Z

## Security

Scripts are executed in a sandboxed namespace. Access to:
- File system (os, pathlib) - **BLOCKED**
- Subprocess/network - **BLOCKED**
- eval/exec - **BLOCKED**
