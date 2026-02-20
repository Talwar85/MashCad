# Sketch Workflow

![Sketch Editor](../../img/sketch2d.JPG)

The sketch workflow is the foundation of parametric CAD design in MashCAD. This guide covers creating, editing, and constraining 2D sketches that form the basis for 3D operations.

---

## Table of Contents

1. [Creating a New Sketch](#creating-a-new-sketch)
2. [Selecting Sketch Planes](#selecting-sketch-planes)
3. [Drawing Tools](#drawing-tools)
4. [Adding Constraints](#adding-constraints)
5. [Finishing and Editing Sketches](#finishing-and-editing-sketches)
6. [Tips & Best Practices](#tips--best-practices)

---

## Creating a New Sketch

### From the Toolbar

1. Click the **New Sketch** button in the toolbar
2. Or use the menu: **Sketch → New Sketch**
3. Or press the shortcut key (default: `N`)

### From the Browser

1. Right-click on **Sketches** in the browser panel
2. Select **New Sketch** from the context menu
3. Enter a name for your sketch

### Sketch Properties

When creating a sketch, you can set:

| Property | Description | Default |
|----------|-------------|---------|
| **Name** | Identifier for the sketch | "Sketch_1" |
| **Plane** | The 2D plane for the sketch | XY Plane |
| **Construction** | Mark as construction geometry | False |

---

## Selecting Sketch Planes

### Default Planes

MashCAD provides three default planes:

```
[Screenshot placeholder: Plane selection dialog]
```

| Plane | Description | Normal Vector |
|-------|-------------|---------------|
| **XY Plane** | Top view, horizontal | (0, 0, 1) |
| **XZ Plane** | Front view | (0, 1, 0) |
| **YZ Plane** | Right side view | (1, 0, 0) |

### Face Selection

To sketch on an existing face:

1. Select a **planar face** in the 3D viewport
2. Click **New Sketch** - the face becomes your sketch plane
3. The sketch origin is set at the face center

### Custom Planes

Create custom sketch planes:

1. **Offset Plane** - Parallel to existing plane at a distance
2. **Angle Plane** - Rotated around an edge
3. **3-Point Plane** - Defined by three points

### Plane Orientation

When entering sketch mode:

- The view automatically orients to look perpendicular to the plane
- The grid aligns with the sketch plane
- Coordinate axes show local X and Y directions

---

## Drawing Tools

### Tool Palette

Access drawing tools from the right panel or keyboard shortcuts:

```
[Screenshot placeholder: Drawing tools panel]
```

### Basic Shapes

#### Line

**Toolbar:** Line icon | **Shortcut:** `L`

```
[Screenshot placeholder: Line tool in action]
```

**Steps:**
1. Click to set the **start point**
2. Move mouse to preview the line
3. Click to set the **end point**
4. Continue clicking for connected lines
5. Press `Escape` to finish

**Numeric Input:** Press `Tab` during drawing to enter precise coordinates:
- Start: (x1, y1)
- End: (x2, y2)
- Length and angle

#### Rectangle

**Toolbar:** Rectangle icon | **Shortcut:** `R`

**Two modes:**

1. **Corner to Corner** (default)
   - Click first corner
   - Drag to opposite corner
   - Release to create

2. **Center to Corner**
   - Click center point
   - Drag to define half-width and half-height
   - Release to create

**Result:** Creates 4 lines with automatic horizontal/vertical constraints.

#### Circle

**Toolbar:** Circle icon | **Shortcut:** `C`

**Three modes:**

| Mode | Description | Steps |
|------|-------------|-------|
| **Center + Radius** | Default mode | Click center, drag radius |
| **Center + Diameter** | Diameter input | Click center, enter diameter |
| **3-Point Circle** | Circumscribed | Click 3 points on circumference |

**Properties:**
- Center point (x, y)
- Radius or diameter
- Construction mode toggle

#### Arc

**Toolbar:** Arc icon | **Shortcut:** `A`

**Three modes:**

1. **Center + 2 Points**
   - Click center
   - Click start point (defines radius)
   - Click end point (defines sweep)

2. **3-Point Arc**
   - Click start point
   - Click a point on the arc
   - Click end point

3. **Tangent Arc**
   - Select existing curve endpoint
   - Click to define arc end
   - Arc is automatically tangent to selected curve

#### Polygon

**Toolbar:** Polygon icon | **Shortcut:** `P`

**Regular Polygon:**
1. Click center point
2. Drag to define radius
3. Set number of sides (3-100) in property panel

**Irregular Polygon:**
1. Click vertices in sequence
2. Double-click or press `Enter` to close

#### Slot

**Toolbar:** Slot icon | **Shortcut:** `S` (in sketch mode)

Creates a slot (rounded rectangle with semicircular ends):

1. Click center of first arc
2. Click center of second arc
3. Drag to define width/radius

**Use cases:**
- Mounting holes
- Adjustment slots
- Slider mechanisms

#### Spline

**Toolbar:** Spline icon | **Shortcut:** `B` (Bézier)

**Control Point Spline:**
1. Click to add control points
2. Drag handles to adjust curvature
3. Press `Enter` to finish

**Properties:**
- Smooth/sharp toggle per point
- Handle visibility
- Weight (NURBS-style)

### Precision Input

Press `Tab` while drawing to access the numeric input panel:

```
[Screenshot placeholder: Numeric input panel]
```

**Available inputs:**
- Absolute coordinates (X, Y)
- Relative coordinates (ΔX, ΔY)
- Polar coordinates (Length, Angle)
- Reference to existing geometry

### Snapping

Automatic snapping helps with precision:

| Snap Type | Indicator | Description |
|-----------|-----------|-------------|
| **Endpoint** | Green square | Line/arc endpoints |
| **Midpoint** | Green triangle | Center of lines |
| **Center** | Green circle | Circle/arc centers |
| **Intersection** | Green X | Crossing points |
| **On Edge** | Green line | Point on curve |
| **Grid** | Gray dot | Grid intersection |

**Toggle snapping:** `Shift` key temporarily disables snapping

---

## Adding Constraints

Constraints define geometric relationships and dimensions, making your sketch parametric.

### Constraint Types

#### Geometric Constraints

| Constraint | Shortcut | Description |
|------------|----------|-------------|
| **Coincident** | `Shift+C` | Two points share the same location |
| **Horizontal** | `H` | Line is parallel to X-axis |
| **Vertical** | `V` | Line is parallel to Y-axis |
| **Parallel** | `Shift+P` | Two lines are parallel |
| **Perpendicular** `Shift+T` | Two lines at 90° |
| **Tangent** | `T` | Line/arc touches curve smoothly |
| **Equal** | `E` | Equal length or radius |
| **Concentric** | `O` | Same center point |
| **Symmetric** | `Shift+S` | Symmetric about a line |
| **Midpoint** | `M` | Point at line center |
| **Fixed** | `F` | Lock point position |

#### Dimensional Constraints

| Constraint | Shortcut | Description |
|------------|----------|-------------|
| **Distance** | `D` | Distance between two points |
| **Length** | `D` on line | Line length |
| **Angle** | `Shift+A` | Angle between two lines |
| **Radius** | `D` on circle/arc | Radius value |
| **Diameter** | `Shift+D` on circle | Diameter value |

### Adding Constraints

#### Method 1: Selection-Based

1. **Select** the geometry (click or box select)
2. Click the **constraint button** in the toolbar
3. Enter value if dimensional

#### Method 2: Quick Constraints

1. Select geometry
2. Press the **keyboard shortcut**
3. Constraint is applied immediately

#### Method 3: Auto-Constraint

While drawing, MashCAD automatically suggests constraints:
- Lines near horizontal/vertical get H/V constraints
- Connected endpoints get coincident constraints
- Press `Tab` to see/accept suggestions

### Constraint Display

```
[Screenshot placeholder: Constraint visualization]
```

- **Green:** Satisfied constraint
- **Yellow:** Warning (nearly violated)
- **Red:** Violated constraint
- **Gray:** Disabled/reference constraint

### Constraint Solver

The constraint solver automatically adjusts geometry to satisfy all constraints.

**Solver Status:**

| Status | Color | Description |
|--------|-------|-------------|
| **Fully Constrained** | Green | All DOF resolved, stable |
| **Under Constrained** | Yellow | DOF remaining, can drag |
| **Over Constrained** | Red | Conflicting constraints |
| **Inconsistent** | Red | No solution exists |

**Degrees of Freedom (DOF):**
- Unconstrained point: 2 DOF (X, Y)
- Unconstrained line: 4 DOF (2 endpoints × 2)
- Each constraint removes DOF

### Constraint Best Practices

1. **Start with geometric constraints** (horizontal, parallel, etc.)
2. **Add dimensions last** (length, angle, etc.)
3. **Avoid over-constraining** - delete conflicting constraints
4. **Use construction geometry** for reference
5. **Fix one point** to ground the sketch

---

## Finishing and Editing Sketches

### Finishing a Sketch

When your sketch is complete:

1. Click **Finish Sketch** in the toolbar
2. Or press `Escape` twice
3. Or use menu: **Sketch → Finish Sketch**

The sketch closes and becomes available for 3D operations.

### Sketch Status

Before finishing, check the status:

- **Green checkmark:** Fully constrained, ready for 3D
- **Yellow warning:** Under-constrained, may change unexpectedly
- **Red error:** Invalid or over-constrained

### Re-editing a Sketch

To modify an existing sketch:

1. **Double-click** the sketch in the browser
2. Or right-click → **Edit Sketch**
3. Or select the sketch and press `Enter`

### Sketch Operations

Right-click a sketch in the browser for options:

| Operation | Description |
|-----------|-------------|
| **Edit** | Enter sketch mode |
| **Rename** | Change sketch name |
| **Delete** | Remove sketch |
| **Duplicate** | Create a copy |
| **Mirror** | Mirror sketch about a line |
| **Move** | Translate entire sketch |
| **Rotate** | Rotate sketch around point |

### Profile Detection

MashCAD automatically detects closed profiles for extrusion:

```
[Screenshot placeholder: Profile highlighting]
```

- **Closed profiles** are highlighted in green
- **Open contours** shown in yellow
- **Multiple profiles** can be selected separately

---

## Tips & Best Practices

### Workflow Tips

1. **Plan before drawing** - Know what profile you need
2. **Use construction geometry** for reference lines and circles
3. **Name your sketches** - Helps with complex designs
4. **Solve incrementally** - Add constraints as you draw
5. **Check DOF count** - Aim for 0 DOF (fully constrained)

### Common Patterns

#### Centered Rectangle

```python
# Python console example
sketch.add_rectangle(-20, -15, 40, 30)  # Centered at origin
```

1. Draw rectangle from corner
2. Add construction lines from origin to midpoints
3. Add symmetric constraints

#### Circle Tangent to Lines

1. Draw the two lines first
2. Draw circle approximately in position
3. Add tangent constraints to both lines
4. Add radius dimension

#### Equally Spaced Holes

1. Draw first circle
2. Use linear pattern (specify count and spacing)
3. Or use equal distance constraints

### Troubleshooting

#### Solver Won't Solve

- Check for conflicting constraints (red indicators)
- Remove redundant constraints
- Try fixing a point to ground the sketch

#### Profile Not Closing

- Check for gaps between endpoints (zoom in)
- Add coincident constraints at corners
- Look for duplicate points

#### Unexpected Behavior

- Check constraint priority (geometric before dimensional)
- Verify you're not in construction mode
- Reset view to check 3D orientation

### Keyboard Shortcuts Summary

| Key | Action |
|-----|--------|
| `L` | Line tool |
| `R` | Rectangle tool |
| `C` | Circle tool |
| `A` | Arc tool |
| `P` | Polygon tool |
| `S` | Slot tool |
| `B` | Spline tool |
| `H` | Horizontal constraint |
| `V` | Vertical constraint |
| `D` | Dimension/Distance |
| `T` | Tangent constraint |
| `E` | Equal constraint |
| `Tab` | Numeric input |
| `Escape` | Finish/Cancel |
| `Space` | 3D peek (preview in 3D) |
| `Delete` | Delete selected |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |

---

## Next Steps

Now that you understand sketching, continue with:

- **[3D Operations](03_3d_operations.md)** - Transform sketches into 3D models
- **[Export & Import](04_export_import.md)** - Work with external files
- **[Keyboard Shortcuts](05_keyboard_shortcuts.md)** - Master all shortcuts

---

*Last updated: February 2026 | MashCAD v0.3.0*
