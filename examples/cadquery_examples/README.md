# CadQuery Import Examples for MashCad

This directory contains example Build123d scripts that can be imported into MashCad using the CadQuery Importer.

## How to Use

1. In MashCad, go to **File → Import → Import CadQuery Script...**
2. Select any `.py` file from this directory
3. The script will be executed and the resulting 3D model will appear as a new Body

Or use the **CadQuery Script Editor** (File → CadQuery Script Editor...) for live editing with parameter extraction.

## Examples

### Build123d Native Examples

### `bracket.py`
Simple mounting bracket with two holes. Demonstrates:
- BuildSketch with Rectangle
- Circle subtraction using Mode.SUBTRACT
- Locations for positioning
- Fillet operation

### `parametric_knob.py`
Parametric knob design with grip fins. Demonstrates:
- Parameter-driven design (variables at top)
- Polar array of features
- Trigonometric positioning
- Multiple boolean operations

### `flange_coupling.py`
Mechanical flange with bolt holes. Demonstrates:
- Circle primitive with extrusion
- Polar array of bolt holes
- Trigonometric positioning with sin/cos
- Center bore subtraction

### CadQuery-Style Chaining (Phase 4)

### `workplane_box.py`
Box with filleted edges using chaining:
```python
# NO import needed - cq is pre-defined
result = cq.Workplane('XY').box(50, 30, 10).faces('>Z').fillet(2)
```

### `workplane_bracket.py`
Bracket demonstrating chained operations:
```python
result = cq.Workplane('XY').box(100, 50, 10).edges('|Z').fillet(2)
```

### `workplane_flange.py`
Flange using cylinder primitives:
```python
result = cq.Workplane('XY').cylinder(50, 15).edges('|Z').fillet(3)
```

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

Allowed imports: `build123d`, `math`, `typing`
