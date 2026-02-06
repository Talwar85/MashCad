
# TNP v4.0 — Comprehensive Fix & Stabilization Plan

## 🔴 Root Cause Analysis

### Bug 1: HashCode API
The error `type object 'OCP.TopTools.TopTools_ShapeMapHasher' has no attribute 'HashCode'` occurs because **OCP Python bindings use a `_s` suffix for all static methods**. Throughout your entire codebase you correctly use:
- `BRepGProp.LinearProperties_s()` 
- `TopExp.MapShapes_s()`
- `TopoDS.Edge_s()`
- `BRepTools.Write_s()`

But in `tnp_system.py` (and also in `modeling/__init__.py`'s `_resolve_edges_by_hash`), the call is:
```python
TopTools_ShapeMapHasher.HashCode(shape, 2**31 - 1)  # ❌ WRONG
```
When it should be:
```python
TopTools_ShapeMapHasher.HashCode_s(shape, 2**31 - 1)  # ✅ CORRECT
```

**Proof**: Your own test file `tests/test_tnp_edge_accumulation.py` line ~175 already has the correct `HashCode_s()` syntax!

### Bug 2: Deeper Architecture Issues
Even after fixing HashCode, the TNP system has structural problems:
1. **`_shape_exists_in_solid()` always returns `True`** — shapes are never validated against current topology
2. **Registry grows unbounded** — no cleanup of stale shapes after operations
3. **Geometric matching is unreliable** — center-point + length matching can false-match when shapes are close
4. **No use of OCCT-native shape identity** — `TopTools_IndexedMapOfShape` is the OCCT way to track shape identity (already used in `brep_face_merger.py`, `brep_face_analyzer.py`, `cad_tessellator.py`)

### Bug 3: GeomType (side issue)
`edge.geom_type()` should be `edge.geom_type` (property, not callable) in `edge_selection_mixin.py`.

---

## 📐 Architecture: CAD-Kernel-First TNP

The core principle: **Use OCCT's own topology tracking mechanisms, not Python-level hashing.**

### New Shape Identity Strategy

Instead of fragile `HashCode_s` comparisons, use `TopTools_IndexedMapOfShape`:

```python
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopExp import TopExp

# Build map of all edges in a solid
edge_map = TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(solid.wrapped, TopAbs_EDGE, edge_map)

# Check identity: is this edge in the solid?
is_present = edge_map.Contains(edge)  # ✅ OCCT-native, O(1)

# Get total count
count = edge_map.Extent()

# Iterate
for i in range(1, edge_map.Extent() + 1):
    edge = TopoDS.Edge_s(edge_map.FindKey(i))
```

This is **guaranteed correct** because it's using OCCT's internal shape pointer equality (TShape), not geometric approximation.

---

## 🔧 Implementation Plan — 5 Phases

### Phase 1: Fix Critical HashCode Bug (30 min)
**Goal**: Make the existing code work without errors.

**Files**: 
- `modeling/tnp_system.py` — 3 calls
- `modeling/__init__.py` — 2 calls in `_resolve_edges_by_hash`

**Changes**:
```python
# ALL occurrences: Replace
TopTools_ShapeMapHasher.HashCode(shape, 2**31 - 1)
# With
TopTools_ShapeMapHasher.HashCode_s(shape, 2**31 - 1)
```

**Automated Test**:
```python
def test_hashcode_api():
    """Validates HashCode_s works on real OCP shapes."""
    from build123d import Box
    from OCP.TopTools import TopTools_ShapeMapHasher
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    
    box = Box(10, 10, 10)
    explorer = TopExp_Explorer(box.wrapped, TopAbs_EDGE)
    edge = TopoDS.Edge_s(explorer.Current())
    
    h = TopTools_ShapeMapHasher.HashCode_s(edge, 2**31 - 1)
    assert isinstance(h, int), f"HashCode_s should return int, got {type(h)}"
    assert h > 0, "HashCode should be positive"
```

---

### Phase 2: Replace Hash-Based Dedup with IndexedMapOfShape (1.5 hours)
**Goal**: Use OCCT-native shape identity instead of fragile hash comparisons.

**File**: `modeling/tnp_system.py` — rewrite `_register_unmapped_edges()`

**Current approach** (broken):
```python
# Collects hashes, compares hashes → fragile, wrong API
mapped_shapes = set()
shape_hash = TopTools_ShapeMapHasher.HashCode(...)  # broken
if edge_hash not in mapped_shapes: ...
```

**New approach** (OCCT-native):
```python
from OCP.TopTools import TopTools_IndexedMapOfShape

def _register_unmapped_edges(self, result_solid, feature_id, existing_mappings):
    # 1. Build map of ALL already-known edges (from registry)
    known_edges_map = TopTools_IndexedMapOfShape()
    for record in self._shapes.values():
        if record.shape_id.shape_type == ShapeType.EDGE and record.ocp_shape:
            known_edges_map.Add(record.ocp_shape)
    
    # 2. Iterate result solid edges
    result_shape = result_solid.wrapped if hasattr(result_solid, 'wrapped') else result_solid
    explorer = TopExp_Explorer(result_shape, TopAbs_EDGE)
    new_count = 0
    
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        
        if not known_edges_map.Contains(edge):
            # Truly new edge → register
            self.register_shape(edge, ShapeType.EDGE, feature_id, new_count)
            known_edges_map.Add(edge)  # prevent double-registration
            new_count += 1
        
        explorer.Next()
    
    return new_count
```

**Automated Test**:
```python
def test_no_duplicate_edges_after_pushpull():
    """After Push/Pull, registry should not contain duplicate edges."""
    doc = Document()
    body = Body(name="Test")
    doc.bodies.append(body)
    
    sketch = create_rectangle_sketch(100, 100)
    body.add_feature(ExtrudeFeature(sketch=sketch, distance=50), rebuild=True)
    
    # Do Push/Pull
    faces = list(body._build123d_solid.faces())
    top_face = max(faces, key=lambda f: f.center().Z)
    body.add_feature(PushPullFeature(...), rebuild=True)
    
    service = doc._shape_naming_service
    edge_records = [r for r in service._shapes.values() if r.shape_id.shape_type == ShapeType.EDGE]
    
    # Check for duplicates using IndexedMap
    edge_map = TopTools_IndexedMapOfShape()  
    for r in edge_records:
        if r.ocp_shape:
            edge_map.Add(r.ocp_shape)
    
    # Unique edges should equal total edges
    assert edge_map.Extent() == len([r for r in edge_records if r.ocp_shape]), \
        f"Duplicates found: {len(edge_records)} records but only {edge_map.Extent()} unique shapes"
```

---

### Phase 3: Fix `_shape_exists_in_solid()` (1 hour)
**Goal**: Actually validate if a stored shape still exists in the current solid.

**Current** (stub):
```python
def _shape_exists_in_solid(self, ocp_shape, current_solid):
    return True  # Always true = useless
```

**New** (real validation):
```python
def _shape_exists_in_solid(self, ocp_shape, current_solid):
    """Uses OCCT IndexedMap to check if shape still exists in solid."""
    if current_solid is None:
        return False
    
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopExp import TopExp
        
        shape_type = ocp_shape.ShapeType()
        solid_wrapped = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
        
        shape_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(solid_wrapped, shape_type, shape_map)
        
        return shape_map.Contains(ocp_shape)
    except Exception:
        return False  # Safe fallback
```

**Automated Test**:
```python
def test_shape_exists_after_modification():
    """Old edges should not exist after topology-changing ops."""
    box = Box(10, 10, 10)
    old_edges = list(box.edges())
    
    # Chamfer changes topology
    chamfered = Chamfer(box, 1.0, old_edges[0])
    
    service = ShapeNamingService()
    old_ocp = old_edges[0].wrapped
    
    # Old edge should NOT exist in new solid
    assert not service._shape_exists_in_solid(old_ocp, chamfered)
```

---

### Phase 4: Registry Cleanup & Lifecycle Management (1.5 hours)
**Goal**: Prevent unbounded growth. Add `invalidate_feature()` and `compact()`.

**New methods on ShapeNamingService**:

```python
def invalidate_feature(self, feature_id: str):
    """Remove all shapes from a feature (for undo/rebuild)."""
    if feature_id in self._by_feature:
        for shape_id in self._by_feature[feature_id]:
            if shape_id.uuid in self._shapes:
                del self._shapes[shape_id.uuid]
        del self._by_feature[feature_id]

def compact(self, current_solid):
    """Remove all shapes that no longer exist in the current solid."""
    to_remove = []
    for uuid, record in self._shapes.items():
        if record.ocp_shape and not self._shape_exists_in_solid(record.ocp_shape, current_solid):
            to_remove.append(uuid)
    
    for uuid in to_remove:
        feat_id = self._shapes[uuid].shape_id.feature_id
        del self._shapes[uuid]
        if feat_id in self._by_feature:
            self._by_feature[feat_id] = [
                sid for sid in self._by_feature[feat_id] if sid.uuid != uuid
            ]
    return len(to_remove)

def register_solid_edges(self, solid, feature_id: str):
    """Register ALL edges from a new solid. Replaces fragile incremental registration."""
    from OCP.TopTools import TopTools_IndexedMapOfShape
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(solid.wrapped, TopAbs_EDGE, edge_map)
    
    count = 0
    for i in range(1, edge_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_map.FindKey(i))
        self.register_shape(edge, ShapeType.EDGE, feature_id, i - 1)
        count += 1
    return count
```

**Automated Tests**:
```python
def test_invalidate_removes_shapes():
    """invalidate_feature should remove all shapes for that feature."""
    service = ShapeNamingService()
    # Register 5 shapes for feature "f1"
    box = Box(10, 10, 10)
    service.register_solid_edges(box, "f1")
    assert service.get_stats()['total_shapes'] > 0
    
    service.invalidate_feature("f1")
    assert service.get_stats()['total_shapes'] == 0

def test_compact_removes_stale_shapes():
    """compact should remove shapes not in current solid."""
    service = ShapeNamingService()
    box1 = Box(10, 10, 10)
    service.register_solid_edges(box1, "f1")
    
    before = service.get_stats()['total_shapes']
    
    # New solid has different topology
    box2 = Box(20, 20, 20)
    removed = service.compact(box2)
    
    assert removed == before, "All old shapes should be removed"
```

---

### Phase 5: Integration & Robustness (1.5 hours)
**Goal**: Wire everything together, fix side bugs, ensure end-to-end stability.

**5a. Fix GeomType bug** in `edge_selection_mixin.py`:
```python
# ❌ Current:
is_line = edge.geom_type() == GeomType.LINE
# ✅ Fix:
is_line = edge.geom_type == GeomType.LINE
```

**5b. Fix `_resolve_edges_by_hash` in `modeling/__init__.py`**:
- Change `HashCode()` → `HashCode_s()`
- Or better: replace with `TopTools_IndexedMapOfShape.Contains()`

**5c. Add `_safe_shape_hash()` utility** for anywhere hashing is still needed:
```python
def _safe_shape_hash(shape) -> int:
    """Safe shape hashing that works across OCP versions."""
    try:
        return TopTools_ShapeMapHasher.HashCode_s(shape, 2**31 - 1)
    except AttributeError:
        try:
            return shape.HashCode(2**31 - 1)
        except AttributeError:
            return id(shape)
```

**5d. Comprehensive Integration Tests**:
```python
def test_full_workflow_extrude_chamfer_pushpull():
    """End-to-end: Extrude → Chamfer → Push/Pull → Undo → Redo."""
    doc = Document()
    body = Body(name="Test")
    doc.bodies.append(body)
    
    # Step 1: Extrude
    body.add_feature(ExtrudeFeature(...), rebuild=True)
    assert body._build123d_solid is not None
    
    # Step 2: Chamfer 4 edges
    edges = list(body._build123d_solid.edges())[:4]
    body.add_feature(ChamferFeature(...), rebuild=True)
    assert body._build123d_solid is not None
    
    # Step 3: Push/Pull
    body.add_feature(PushPullFeature(...), rebuild=True)
    assert body._build123d_solid is not None
    
    # Step 4: Verify TNP registry
    service = doc._shape_naming_service
    stats = service.get_stats()
    real_edges = len(list(body._build123d_solid.edges()))
    assert stats['edges'] <= real_edges * 3  # No explosion
    
    # Step 5: Rebuild (simulates undo/redo)
    body._rebuild()
    assert body._build123d_solid is not None

def test_save_load_preserves_tnp():
    """TNP ShapeIDs should survive save/load cycle."""
    doc = Document()
    body = Body(name="Test")
    doc.bodies.append(body)
    body.add_feature(ExtrudeFeature(...), rebuild=True)
    
    # Save
    data = doc.to_dict()
    
    # Load
    doc2 = Document.from_dict(data)
    body2 = doc2.bodies[0]
    body2._rebuild()
    
    assert body2._build123d_solid is not None
    assert len(body2.features) == 1
```

---

## 📊 Test Matrix (Automated via pytest)

| Test | Phase | What it validates |
|---|---|---|
| `test_hashcode_api` | 1 | `HashCode_s` works on OCP shapes |
| `test_no_duplicate_edges_after_pushpull` | 2 | Registry dedup works |
| `test_shape_exists_after_modification` | 3 | Stale shape detection |
| `test_invalidate_removes_shapes` | 4 | Feature cleanup |
| `test_compact_removes_stale_shapes` | 4 | Registry compaction |
| `test_full_workflow_extrude_chamfer_pushpull` | 5 | End-to-end stability |
| `test_save_load_preserves_tnp` | 5 | Persistence |
| `test_edge_count_stability` | 5 | No exponential growth |

**Run**: `pytest tests/test_tnp_v4.py -v -s`

Each test is **self-contained** — creates its own Document, Body, shapes. No GUI dependency. No external state.

---

## ⏱ Estimated Effort

| Phase | Time | Risk |
|---|---|---|
| Phase 1: Fix HashCode_s | 30 min | LOW (mechanical fix) |
| Phase 2: IndexedMapOfShape | 1.5h | LOW (proven OCCT pattern) |
| Phase 3: _shape_exists_in_solid | 1h | LOW |
| Phase 4: Registry lifecycle | 1.5h | MEDIUM (integration points) |
| Phase 5: Integration & tests | 1.5h | MEDIUM |
| **Total** | **~6h** | **MEDIUM** |

---

## 🔑 Key Guarantees

1. **API Correctness**: Every OCP static call uses `_s` suffix — verified against your entire codebase pattern
2. **OCCT-Native**: Uses `TopTools_IndexedMapOfShape` (proven in `brep_face_merger.py`, `cad_tessellator.py`, `brep_face_analyzer.py`)
3. **No Memory Leaks**: `compact()` + `invalidate_feature()` prevent unbounded growth
4. **Testable**: Every phase has self-contained pytest tests — no GUI needed
5. **Backward Compatible**: Old `.mshcad` files load unchanged

---

Soll ich mit der Implementierung starten? Wenn ja, bitte **toggle to Act mode** und ich beginne mit Phase 1 (HashCode_s Fix) + den automatisierten Tests.
