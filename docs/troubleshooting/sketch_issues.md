# Sketch Issues Troubleshooting Guide

This guide covers common sketch-related problems in MashCAD, their root causes, and solutions.

## Table of Contents

1. [Sketch Won't Solve](#sketch-wont-solve)
2. [Constraints Not Working](#constraints-not-working)
3. [Profile Not Detected](#profile-not-detected)
4. [Sketch Plane Issues](#sketch-plane-issues)
5. [Performance Problems](#performance-problems)
6. [Error Messages Reference](#error-messages-reference)

---

## Sketch Won't Solve

### Symptoms
- Solver indicator shows red or yellow status
- Sketch elements don't snap to expected positions
- "Over-constrained" or "Under-constrained" warnings appear
- Degrees of freedom (DOF) count shows unexpected values

### Root Causes

#### 1. Over-Constrained Sketch
Too many constraints for the available degrees of freedom.

**Diagnosis:**
```python
# Enable debug logging
from config.feature_flags import set_flag
set_flag("sketch_debug", True)

# Check constraint count vs DOF
sketch = document.active_sketch
print(f"DOF: {sketch.degrees_of_freedom}")
print(f"Constraints: {len(sketch.constraints)}")
```

**Solution:**
1. Identify redundant constraints using the constraint diagnostics:
   ```python
   from sketcher.constraint_diagnostics import analyze_constraints
   report = analyze_constraints(sketch)
   print(report.redundant_constraints)
   ```
2. Remove conflicting constraints (highlighted in red in the UI)
3. Re-add constraints one at a time, verifying solver status after each

**Prevention:**
- Start with minimal constraints and add incrementally
- Use the DOF indicator to track remaining freedom
- Avoid duplicate constraints (e.g., both horizontal AND two-point horizontal on same line)

#### 2. Under-Constrained Sketch
Not enough constraints to fully define the sketch.

**Diagnosis:**
```python
# Check which elements are under-constrained
from sketcher.constraint_diagnostics import find_under_constrained
result = find_under_constrained(sketch)
for element, missing in result.items():
    print(f"{element}: missing {missing}")
```

**Solution:**
1. Add dimensions to fix sizes (length, radius, angle)
2. Add geometric constraints (horizontal, vertical, coincident, etc.)
3. Anchor the sketch to the origin with at least one fixed point

**Prevention:**
- Fully constrain sketches before extruding (green indicator)
- Use construction geometry as reference

#### 3. Conflicting Constraints
Constraints that mathematically cannot all be satisfied.

**Solution:**
1. Enable constraint diagnostics:
   ```python
   from sketcher.constraint_diagnostics import ConstraintDiagnostics
   diag = ConstraintDiagnostics(sketch)
   conflicts = diag.find_conflicts()
   ```
2. Remove one of the conflicting constraints
3. Re-evaluate if the remaining constraints achieve the design intent

---

## Constraints Not Working

### Symptoms
- Constraints appear to be added but don't affect geometry
- Dimension changes don't update the sketch
- Coincident constraints don't join points

### Root Causes

#### 1. Wrong Constraint Type
Using a constraint that doesn't match the selected geometry.

**Solution:**
Check constraint compatibility:

| Constraint | Valid Selections |
|------------|------------------|
| Distance | Two points, or point and line |
| Angle | Two lines |
| Radius/Diameter | Arc or circle |
| Coincident | Two points, or point and curve |
| Horizontal/Vertical | Line, or two points |
| Parallel/Perpendicular | Two lines |
| Tangent | Line and arc, or two arcs |
| Equal | Two lines (length) or two arcs (radius) |

#### 2. Solver Not Triggered
The solver may not be set to auto-solve.

**Solution:**
```python
# Check solver settings
from config.feature_flags import get_flag
print(f"Auto-solve enabled: {get_flag('sketch_auto_solve')}")

# Manually trigger solve
sketch.solve()
```

#### 3. Reference Geometry Issues
Constraints on construction geometry may behave unexpectedly.

**Solution:**
- Ensure you're constraining actual geometry, not construction lines
- Toggle construction mode off before adding constraints

---

## Profile Not Detected

### Symptoms
- "No valid profile found" error when extruding
- Profile preview doesn't appear
- Expected closed region shows as open

### Root Causes

#### 1. Open Contour
The sketch has gaps preventing profile closure.

**Diagnosis:**
```python
from sketcher.profile_detector_b3d import ProfileDetector
detector = ProfileDetector(sketch)
gaps = detector.find_gaps()
for gap in gaps:
    print(f"Gap at: {gap.start} to {gap.end}, distance: {gap.distance}")
```

**Solution:**
1. Use the gap detection tool in Sketch mode
2. Add coincident constraints to close gaps
3. Check for nearly-but-not-quite touching endpoints

**Prevention:**
- Use the automatic coincident constraint on endpoint snapping
- Zoom in to verify connections before finishing sketch

#### 2. Self-Intersecting Profile
The sketch crosses itself, creating ambiguous regions.

**Solution:**
1. Identify intersection points:
   ```python
   intersections = detector.find_self_intersections()
   ```
2. Redesign to avoid crossings, or
3. Use multiple separate profiles instead

#### 3. Multiple Nested Profiles
Complex nesting confuses the detector.

**Solution:**
- Ensure proper nesting hierarchy (outer → inner islands)
- Check that all profiles are properly closed
- Use the profile preview to verify selection

---

## Sketch Plane Issues

### Symptoms
- Sketch appears in wrong location/orientation
- `plane_y_dir` becomes (0, 0, 0)
- Geometry distorted after plane change

### Known Issue: plane_y_dir Bug

**Status:** Workaround implemented in [`modeling/__init__.py`](../../modeling/__init__.py)

**Root Cause:**
When creating a sketch plane from certain face selections, the Y-direction vector can become zero if the face normal and reference direction are parallel or nearly parallel.

**Symptoms:**
```python
# This error may appear in logs
plane_y_dir = (0, 0, 0)  # Should never be zero
```

**Workaround (Automatic):**
The system automatically detects and corrects this:
```python
# From modeling/__init__.py:1526-1527
if y_dir.X == 0 and y_dir.Y == 0 and y_dir.Z == 0:
    y_dir = z_dir.cross(x_dir)  # Fallback calculation
```

**Manual Fix:**
If you encounter this issue:
1. Cancel the current sketch operation
2. Select a different face or use a datum plane
3. If using a datum plane, ensure it has explicit X and Y directions

**Debug Mode:**
```python
# Enable sketch debug logging
from config.feature_flags import set_flag
set_flag("sketch_debug", True)
set_flag("sketch_input_logging", True)

# Check plane vectors
print(f"Plane origin: {sketch.plane.origin}")
print(f"Plane normal (Z): {sketch.plane.z_dir}")
print(f"Plane X: {sketch.plane.x_dir}")
print(f"Plane Y: {sketch.plane.y_dir}")
```

### Sketch Plane Orientation Issues

**Problem:** Sketch appears rotated 90° from expected

**Solution:**
1. Check the face's natural UV direction
2. Use "Align to Edge" option when creating sketch
3. Manually specify X-direction reference edge

---

## Performance Problems

### Symptoms
- Sketch becomes sluggish with many elements
- Solver takes long to complete
- UI freezes during constraint operations

### Root Causes

#### 1. Too Many Elements
Large sketches with hundreds of elements slow down the solver.

**Solution:**
```python
# Check sketch complexity
element_count = len(sketch.elements)
constraint_count = len(sketch.constraints)
print(f"Elements: {element_count}, Constraints: {constraint_count}")

# If > 200 elements, consider splitting
```

**Best Practice:**
- Keep sketches under 100 elements when possible
- Use multiple sketches for complex shapes
- Use patterns instead of individual copies

#### 2. Complex Constraint Network
Interdependent constraints create solver difficulties.

**Solution:**
1. Simplify constraint structure
2. Use reference dimensions instead of driving dimensions where possible
3. Break into multiple sketches with references

#### 3. Solver Algorithm Issues

**Debug Solver Performance:**
```python
from sketcher.performance_monitor import PerformanceMonitor
monitor = PerformanceMonitor(sketch)
monitor.enable()
sketch.solve()
print(monitor.report())
```

**Enable Staged Solver:**
```python
# The staged solver handles complex sketches better
from config.feature_flags import set_flag
set_flag("staged_solver", True)
```

---

## Error Messages Reference

### "Sketch is over-constrained"

| Code | Meaning | Action |
|------|---------|--------|
| OC-001 | Redundant distance constraint | Remove duplicate dimension |
| OC-002 | Fixed point conflicts with other constraints | Remove fixed constraint or conflicting dimension |
| OC-003 | Symmetric constraint creates redundancy | Simplify constraint scheme |

### "Sketch is under-constrained"

| Code | Meaning | Action |
|------|---------|--------|
| UC-001 | Point has no position constraints | Add horizontal/vertical or coincident |
| UC-002 | Line has no length constraint | Add dimension |
| UC-003 | Arc has no radius constraint | Add radius dimension |

### "Profile not closed"

| Code | Meaning | Action |
|------|---------|--------|
| PN-001 | Gap between endpoints | Add coincident constraint |
| PN-002 | Duplicate points at same location | Merge points |
| PN-003 | Curve doesn't connect | Extend/trim curves |

### "Solver failed to converge"

| Code | Meaning | Action |
|------|---------|--------|
| SF-001 | Initial guess too far from solution | Reset sketch positions |
| SF-002 | Conflicting constraints | Review constraint list |
| SF-003 | Numerical instability | Simplify geometry |

---

## Debug Checklist

When experiencing sketch issues, run through this checklist:

- [ ] Enable debug logging: `set_flag("sketch_debug", True)`
- [ ] Check DOF count matches expected
- [ ] Verify all endpoints are connected (no gaps)
- [ ] Look for red-highlighted constraints (conflicts)
- [ ] Check plane vectors are valid (non-zero Y direction)
- [ ] Review constraint count vs element count
- [ ] Test with a simplified version of the sketch

## Related Files

- [`sketcher/sketch.py`](../../sketcher/sketch.py) - Sketch data model
- [`sketcher/solver.py`](../../sketcher/solver.py) - Constraint solver
- [`sketcher/constraint_diagnostics.py`](../../sketcher/constraint_diagnostics.py) - Diagnostics tools
- [`sketcher/profile_detector_b3d.py`](../../sketcher/profile_detector_b3d.py) - Profile detection
- [`config/feature_flags.py`](../../config/feature_flags.py) - Debug flags

## Feature Flags for Debugging

```python
# Enable all sketch debugging
from config.feature_flags import set_flag
set_flag("sketch_debug", True)
set_flag("sketch_input_logging", True)
set_flag("tnp_debug_logging", True)  # For topology tracking
```
