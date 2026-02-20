# 3D Operations Troubleshooting Guide

This guide covers common 3D modeling operation failures in MashCAD, including extrude, fillet, chamfer, boolean, and advanced operations.

## Table of Contents

1. [Extrude Failures](#extrude-failures)
2. [Fillet/Chamfer Errors](#filletchamfer-errors)
3. [Boolean Operation Failures](#boolean-operation-failures)
4. [Shell/Sweep/Loft Issues](#shellsweeploft-issues)
5. [Geometry Drift After Edits](#geometry-drift-after-edits)
6. [Error Messages Reference](#error-messages-reference)

---

## Extrude Failures

### Symptoms
- "Extrude failed" error message
- Extrusion produces no visible result
- Extruded shape differs from expected
- Application crashes during extrude

### Root Causes

#### 1. Invalid Sketch Profile

**Diagnosis:**
```python
from sketcher.profile_detector_b3d import ProfileDetector
detector = ProfileDetector(sketch)
valid, issues = detector.validate_for_extrude()
if not valid:
    for issue in issues:
        print(f"Issue: {issue.description} at {issue.location}")
```

**Common Issues:**
- Open profile (gaps in sketch)
- Self-intersecting profile
- Multiple disconnected profiles without proper selection
- Zero-area profile

**Solution:**
1. Return to sketch mode and fix profile issues
2. Ensure all endpoints are connected with coincident constraints
3. Remove self-intersections

#### 2. Extrude Parameters Out of Range

**Problem:** Extrusion distance too small or too large

**Solution:**
```python
# Check valid range for extrusion
from modeling.geometry_validator import validate_extrude_params
result = validate_extrude_params(
    sketch=sketch,
    distance=extrude_distance,
    direction=direction
)
if not result.valid:
    print(f"Invalid: {result.reason}")
    print(f"Suggested range: {result.suggested_range}")
```

**Guidelines:**
- Minimum extrusion distance: 0.001mm (configurable)
- Maximum depends on model scale and available memory
- Negative distances (cut) require existing solid geometry

#### 3. Non-Planar Sketch

**Problem:** Sketch is not on a flat plane

**Solution:**
```python
# Verify sketch is planar
from modeling.geometry_validator import is_planar
if not is_planar(sketch):
    print("Sketch must be planar for extrusion")
    # Option: Project to plane
    projected = project_to_plane(sketch, target_plane)
```

#### 4. TNP (Topology Naming Protocol) Failure

**Symptoms:**
- Extrude works initially but fails after model edits
- "Cannot find face" errors

**Debug Mode:**
```python
from config.feature_flags import set_flag
set_flag("tnp_debug_logging", True)
set_flag("extrude_debug", True)

# Check TNP tracking
from modeling.feature_dependency import get_topology_tracker
tracker = get_topology_tracker()
print(tracker.get_status_report())
```

**Solution:**
1. Enable TNP debug logging to identify the tracking failure
2. Re-select the sketch plane if face reference is lost
3. Use datum planes instead of model faces for stable references

---

## Fillet/Chamfer Errors

### Symptoms
- "Failed to create fillet" error
- Fillet radius ignored or incorrect
- Edges disappear after fillet
- Geometry becomes invalid

### Root Causes

#### 1. Radius Too Large

**Problem:** Fillet radius exceeds available space

**Diagnosis:**
```python
from modeling.edge_operations import analyze_edge_for_fillet
analysis = analyze_edge_for_fillet(edge)
print(f"Maximum fillet radius: {analysis.max_radius}")
print(f"Minimum adjacent face angle: {analysis.min_angle}")
```

**Solution:**
1. Reduce fillet radius below the maximum
2. For complex corners, use smaller radius or multiple fillets
3. Check adjacent geometry for conflicts

#### 2. Edge Selection Issues

**Problem:** Selected edges are not valid for filleting

**Valid Edge Types:**
- Linear edges
- Circular arcs
- Elliptical edges (with limitations)
- BSpline edges (with limitations)

**Invalid Cases:**
- Edges already filleted
- Edges at sharp corners with insufficient space
- Edges belonging to degenerate faces

**Solution:**
```python
# Validate edge selection
from modeling.edge_operations import validate_fillet_edges
valid, invalid_edges = validate_fillet_edges(selected_edges)
if not valid:
    for edge, reason in invalid_edges:
        print(f"Edge {edge.id}: {reason}")
```

#### 3. Topology Conflicts

**Problem:** Fillet would create invalid topology (self-intersection, etc.)

**Solution:**
1. Enable self-intersection checking:
   ```python
   from config.feature_flags import set_flag
   set_flag("boolean_self_intersection_check", True)
   ```
2. Try filleting edges in a different order
3. Use smaller radius and incrementally increase

#### 4. Batch Fillet Issues

**Problem:** Multiple fillets in one operation fail

**Solution:**
```python
# Enable batch fillet optimization
from config.feature_flags import set_flag
set_flag("batch_fillets", True)

# Or fillet individually
for edge in edges_to_fillet:
    try:
        body = fillet_edge(body, edge, radius)
    except Exception as e:
        print(f"Failed on edge {edge.id}: {e}")
```

### Chamfer-Specific Issues

#### Unequal Chamfer Distances

**Problem:** Asymmetric chamfer creates unexpected geometry

**Solution:**
- Verify both distance values are positive
- Check that distances don't exceed available face area
- Use distance-angle mode instead of distance-distance for better control

---

## Boolean Operation Failures

### Symptoms
- "Boolean operation failed" error
- Result has missing faces or holes
- Operation produces unexpected geometry
- Application hangs during boolean

### Root Causes

#### 1. Invalid Input Geometry

**Diagnosis:**
```python
from modeling.geometry_validator import validate_solid
for body in [body_a, body_b]:
    result = validate_solid(body)
    if not result.valid:
        print(f"{body.name}: {result.issues}")
```

**Common Issues:**
- Non-manifold geometry
- Self-intersecting solids
- Nearly degenerate faces
- Open shells (not closed solids)

**Solution:**
1. Run geometry healing:
   ```python
   from modeling.geometry_healer import heal_solid
   healed = heal_solid(body, auto_fix=True)
   ```
2. Re-create problematic bodies from scratch
3. Use simpler operations to achieve the same result

#### 2. Overlapping or Tangent Geometry

**Problem:** Bodies share faces or are tangent at contact points

**Solution:**
```python
# Enable argument analyzer for better diagnostics
from config.feature_flags import set_flag
set_flag("boolean_argument_analyzer", True)

# Check for problematic overlaps
from modeling.boolean_engine_v4 import analyze_boolean_args
analysis = analyze_boolean_args(body_a, body_b)
print(analysis.recommendations)
```

**Workarounds:**
- Offset one body slightly (0.001mm) to avoid exact tangency
- Use "fuse" with glue option for coincident faces:
  ```python
  from config.feature_flags import set_flag
  set_flag("ocp_glue_auto_detect", True)
  ```

#### 3. Complex Boolean Operations

**Problem:** Operation too complex for single step

**Solution:**
1. Break into simpler operations:
   ```python
   # Instead of complex multi-body boolean
   result = body_a
   for tool in tools:
       result = boolean_union(result, tool)
   ```
2. Enable post-validation:
   ```python
   from config.feature_flags import set_flag
   set_flag("boolean_post_validation", True)
   ```

#### 4. Numerical Precision Issues

**Problem:** Very small features cause numerical instability

**Solution:**
- Work in appropriate units (mm for mechanical parts)
- Avoid features smaller than 0.001mm
- Enable validation:
  ```python
  from modeling.boolean_engine_v4 import BooleanEngineV4
  engine = BooleanEngineV4(tolerance=0.0001)
  result = engine.union(body_a, body_b, validate=True)
  ```

---

## Shell/Sweep/Loft Issues

### Shell Operation Failures

#### 1. Thickness Too Large

**Problem:** Shell thickness exceeds face dimensions

**Diagnosis:**
```python
from modeling.geometry_validator import analyze_shell_thickness
analysis = analyze_shell_thickness(body, thickness)
print(f"Maximum safe thickness: {analysis.max_thickness}")
print(f"Problematic faces: {analysis.problem_faces}")
```

**Solution:**
- Reduce shell thickness
- Remove problematic faces before shelling
- Shell faces individually

#### 2. Non-Shellable Geometry

**Problem:** Some geometry cannot be shelled (e.g., sharp corners)

**Solution:**
- Add fillets to sharp corners before shelling
- Use offset surface operation instead

### Sweep Operation Failures

#### 1. Invalid Sweep Path

**Problem:** Path has discontinuities or sharp corners

**Solution:**
```python
from modeling.geometry_validator import validate_sweep_path
result = validate_sweep_path(path)
if not result.valid:
    print(f"Path issues: {result.issues}")
    # Smooth the path
    smoothed_path = smooth_path(path, tolerance=0.01)
```

#### 2. Profile Rotation Issues

**Problem:** Profile twists unexpectedly along path

**Solution:**
- Use "Fixed" profile mode instead of "Normal to path"
- Add guide curves to control rotation
- Check path direction (reverse if needed)

### Loft Operation Failures

#### 1. Incompatible Profiles

**Problem:** Profiles have different numbers of vertices or incompatible shapes

**Solution:**
```python
# Check profile compatibility
from modeling.geometry_validator import validate_loft_profiles
result = validate_loft_profiles(profiles)
if not result.valid:
    print(f"Incompatible profiles: {result.issues}")
    # Try adding vertices to match
    adjusted = adjust_profile_vertices(profiles)
```

#### 2. Loft Self-Intersection

**Problem:** Loft surface crosses itself

**Solution:**
- Reduce profile complexity
- Add intermediate profiles
- Use guide curves to control shape

---

## Geometry Drift After Edits

### Symptoms
- Features shift position after editing parent features
- Dimensions change unexpectedly
- Faces reference wrong geometry after regeneration

### Root Causes

#### 1. TNP (Topology Naming Protocol) Failure

The topology naming system loses track of faces/edges after edits.

**Diagnosis:**
```python
from modeling.geometry_drift_detector import detect_drift
drift_report = detect_drift(before_model, after_model)
for drift in drift_report.drifts:
    print(f"{drift.element_type} {drift.element_id}: {drift.description}")
```

**Solution:**
```python
# Enable TNP debugging
from config.feature_flags import set_flag
set_flag("tnp_debug_logging", True)

# Check dependency graph integrity
from modeling.feature_dependency import DependencyGraph
graph = DependencyGraph.get_instance()
integrity = graph.check_integrity()
print(integrity.report)
```

#### 2. Unstable References

Features reference model geometry that changes unpredictably.

**Prevention:**
- Use datum planes/axes for references instead of model faces
- Name and tag important features for stable reference
- Avoid referencing faces that will be modified

**Solution:**
```python
# Re-establish references
from modeling.feature_dependency import rebuild_references
rebuild_references(feature_with_drift)
```

#### 3. Circular Dependencies

Features depend on each other in a cycle.

**Diagnosis:**
```python
from modeling.feature_dependency import find_circular_dependencies
cycles = find_circular_dependencies(document)
for cycle in cycles:
    print(f"Circular dependency: {' -> '.join(cycle)}")
```

**Solution:**
- Break the cycle by removing one dependency
- Reorder features in history
- Use reference geometry to break the dependency chain

---

## Error Messages Reference

### Extrude Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| EX-001 | "No valid profile found" | Sketch profile not closed | Fix sketch gaps |
| EX-002 | "Invalid extrusion distance" | Distance ≤ 0 or too large | Use valid distance |
| EX-003 | "Cannot extrude on non-planar sketch" | Sketch not flat | Use planar sketch |
| EX-004 | "Face reference lost" | TNP tracking failed | Re-select face |
| EX-005 | "Insufficient memory for extrusion" | Result too complex | Simplify sketch |

### Fillet/Chamfer Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| FI-001 | "Radius exceeds maximum" | Radius too large for edge | Reduce radius |
| FI-002 | "Edge not filletable" | Invalid edge type | Select different edge |
| FI-003 | "Fillet would cause self-intersection" | Topology conflict | Reduce radius or reorder |
| FI-004 | "Adjacent fillets conflict" | Multiple fillets incompatible | Adjust radii |
| CH-001 | "Chamfer distance invalid" | Distance exceeds face | Reduce distance |

### Boolean Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| BO-001 | "Input body invalid" | Non-manifold or corrupt geometry | Heal geometry |
| BO-002 | "Bodies do not intersect" | No overlap for operation | Move bodies to intersect |
| BO-003 | "Tangent faces detected" | Exact tangency causes issues | Add small offset |
| BO-004 | "Result validation failed" | Output is invalid | Simplify operation |
| BO-005 | "Numerical precision error" | Features too small | Scale up model |

### Shell/Sweep/Loft Errors

| Code | Message | Cause | Solution |
|------|---------|-------|----------|
| SH-001 | "Shell thickness invalid" | Thickness too large | Reduce thickness |
| SH-002 | "Cannot shell this geometry" | Non-shellable shape | Modify geometry |
| SW-001 | "Invalid sweep path" | Path has discontinuities | Smooth path |
| SW-002 | "Profile rotation failed" | Twisting issue | Use fixed profile |
| LO-001 | "Incompatible profiles" | Different vertex counts | Adjust profiles |
| LO-002 | "Loft self-intersects" | Surface crosses itself | Add guide curves |

---

## Debug Checklist

When experiencing 3D operation issues:

- [ ] Enable relevant debug flags:
  ```python
  from config.feature_flags import set_flag
  set_flag("extrude_debug", True)
  set_flag("tnp_debug_logging", True)
  ```
- [ ] Validate input geometry
- [ ] Check operation parameters are in valid range
- [ ] Run geometry healer on problematic bodies
- [ ] Try operation with simplified parameters
- [ ] Check dependency graph for issues
- [ ] Review feature history for conflicts

## Related Files

- [`modeling/__init__.py`](../../modeling/__init__.py) - Core modeling operations
- [`modeling/boolean_engine_v4.py`](../../modeling/boolean_engine_v4.py) - Boolean operations
- [`modeling/edge_operations.py`](../../modeling/edge_operations.py) - Fillet/chamfer
- [`modeling/geometry_validator.py`](../../modeling/geometry_validator.py) - Validation tools
- [`modeling/geometry_healer.py`](../../modeling/geometry_healer.py) - Geometry repair
- [`modeling/geometry_drift_detector.py`](../../modeling/geometry_drift_detector.py) - Drift detection
- [`modeling/feature_dependency.py`](../../modeling/feature_dependency.py) - Dependency tracking

## Feature Flags for 3D Operations

```python
# Boolean robustness
"boolean_self_intersection_check": True
"boolean_post_validation": True
"boolean_argument_analyzer": True

# OCP features
"ocp_glue_auto_detect": True
"batch_fillets": True
"native_ocp_helix": True

# Debug
"extrude_debug": False  # Enable for troubleshooting
"tnp_debug_logging": False  # Enable for topology issues
```
