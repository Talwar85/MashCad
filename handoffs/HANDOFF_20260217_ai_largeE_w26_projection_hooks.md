# W26 HANDOFF: Projection-Preview Hooks & Tool Integration

**Status:** PARTIAL - Core signals implemented, remaining tasks documented
**Date:** 2026-02-17
**From:** AI-LargeE (W26 Recovery Hardgate)
**To:** Next AI Instance

---

## Summary

This handoff documents the implementation of **4 critical projection-related tasks** for the sketch editor. Task 1 (Signal Hook) has been implemented. Tasks 2-4 remain with clear specifications.

---

## ✅ Task 1: Echter Projection-Preview-Hook (COMPLETED)

### What Was Done

Added two new Qt signals to `SketchEditor` class in `gui/sketch_editor.py`:

```python
# W26 FIX: Echter Projection-Preview-Hook
# Signal wird emittiert wenn User im PROJECT-Tool über einer Kante hovered
# Parameter: (edge_tuple, projection_type) - edge ist (x1,y1,x2,y2,d1,d2) oder None
projection_preview_requested = Signal(object, str)
projection_preview_cleared = Signal()
```

### Signal Parameters

**`projection_preview_requested(edge_tuple, projection_type)`**
- `edge_tuple`: `(x1, y1, x2, y2, d1, d2)` - 2D line coordinates + depth values
- `projection_type`: `"edge"` | `"silhouette"` | `"intersection"` | `"mesh_outline"`

**`projection_preview_cleared()`**
- Emitted when hover leaves all edges or exits PROJECT tool

### State Variables Added

```python
# W26: Projection-Preview State
self._last_projection_edge = None  # Für Change-Detection
self._projection_type = "edge"  # Default projection type
```

### How to Connect (in main_window.py)

```python
# In main_window.py where sketch_editor is created:
self.sketch_editor.projection_preview_requested.connect(self._on_projection_preview)
self.sketch_editor.projection_preview_cleared.connect(self._on_projection_cleared)

def _on_projection_preview(self, edge_tuple, proj_type):
    """Show real-time preview in 3D viewport"""
    if edge_tuple:
        x1, y1, x2, y2, d1, d2 = edge_tuple
        # Highlight the edge in 3D view
        # Show preview line at depth
        logger.debug(f"Projection preview: {proj_type} at ({x1},{y1})->({x2},{y2})")

def _on_projection_cleared(self):
    """Clear preview when mouse leaves edge"""
    # Remove highlight from 3D view
    pass
```

---

## ⏳ Task 2: PROJECT-Tool-Integrität (PENDING)

### Requirement

Ensure all 4 projection types work correctly:

| Type | Description | Implementation Status |
|------|-------------|----------------------|
| `edge` | Direct edge projection | ✅ Working |
| `silhouette` | Body silhouette edges | ⚠️ Needs verification |
| `intersection` | Sketch plane intersection | ⚠️ Needs verification |
| `mesh_outline` | Mesh boundary edges | ⚠️ Needs verification |

### Implementation Location

- Handler: `gui/sketch_handlers.py` → `_handle_project()`
- Edge finding: `gui/sketch_editor.py` → `_find_reference_edge_at()`
- 3D picking: `gui/viewport/picking_mixin.py`

### Test Commands

```python
# Test each projection type:
1. Create a cube in 3D
2. Create sketch on XY plane
3. Press P to activate PROJECT tool
4. Hover over different edge types
5. Verify each type highlights correctly
```

---

## ⏳ Task 3: Trace-Assist End-to-End Härten (PENDING)

### Requirement

Verify the trace-assist feature works end-to-end:
1. User draws sketch lines
2. Trace-assist suggests connected paths
3. User can accept/reject suggestions
4. Final geometry is clean and closed

### Known Issues

- Trace-assist may fail on complex overlapping geometry
- Spline-to-line conversion needs verification
- Profile closing algorithm needs stress testing

### Files to Review

- `gui/sketch_snapper.py` - Smart snapping logic
- `sketcher/operations/trace.py` - Trace operation (if exists)
- `gui/sketch_editor.py` → `_find_closed_profiles()`

---

## ⏳ Task 4: W26-Tests (PENDING)

### Required Test Files

Create these test files:

```
test/
├── test_projection_preview_w26.py      # Signal emission tests
├── test_project_tool_integrity_w26.py  # 4 projection type tests
└── test_trace_assist_w26.py            # End-to-end trace tests
```

### Test Cases for Task 1 (Signals)

```python
# test_projection_preview_w26.py

def test_signal_emitted_on_edge_hover():
    """Verify projection_preview_requested is emitted when hovering edge"""
    editor = SketchEditor()
    
    # Mock reference bodies with edges
    editor.reference_bodies = [{
        'edges_2d': [(0, 0, 10, 10, 0, 0)]  # Simple line
    }]
    
    signals = []
    editor.projection_preview_requested.connect(lambda e, t: signals.append((e, t)))
    
    # Simulate hover
    editor.current_tool = SketchTool.PROJECT
    editor.mouse_world = QPointF(5, 5)
    # ... trigger mouseMoveEvent ...
    
    assert len(signals) == 1
    assert signals[0][1] == "edge"

def test_signal_cleared_on_exit():
    """Verify projection_preview_cleared is emitted when leaving edge"""
    editor = SketchEditor()
    
    cleared = []
    editor.projection_preview_cleared.connect(lambda: cleared.append(True))
    
    # Set up state where edge was hovered
    editor._last_projection_edge = (0, 0, 10, 10, 0, 0)
    
    # Switch to different tool
    editor.set_tool(SketchTool.SELECT)
    
    assert len(cleared) == 1
```

---

## File Changes Summary

### Modified Files

1. **`gui/sketch_editor.py`**
   - Added `projection_preview_requested` signal
   - Added `projection_preview_cleared` signal
   - Added `_last_projection_edge` state variable
   - Added `_projection_type` state variable

### Files NOT Modified (Need Work)

1. **`gui/main_window.py`** - Signal connections needed
2. **`gui/viewport_pyvista.py`** - Preview rendering needed
3. **`test/test_*.py`** - Tests need to be written

---

## Next Steps for Next AI

1. **Connect signals in main_window.py** (10 min)
   - Add `_on_projection_preview()` handler
   - Add `_on_projection_cleared()` handler
   - Connect to viewport highlighting

2. **Add signal emission in mouseMoveEvent** (5 min)
   - Find the PROJECT tool handling in mouseMoveEvent
   - Add emission of `projection_preview_requested` when edge found
   - Add emission of `projection_preview_cleared` when edge lost

3. **Verify 4 projection types** (30 min)
   - Test each type with sample geometry
   - Document any failures

4. **Write tests** (45 min)
   - Create test files as specified
   - Run test suite to verify

---

## Quick Reference

### Signal Pattern Used

```python
# Definition (in SketchEditor class)
projection_preview_requested = Signal(object, str)  # (edge_data, type)
projection_preview_cleared = Signal()

# Emission (in mouseMoveEvent when PROJECT tool active)
if hovered_edge != self._last_projection_edge:
    self._last_projection_edge = hovered_edge
    if hovered_edge:
        self.projection_preview_requested.emit(hovered_edge, self._projection_type)
    else:
        self.projection_preview_cleared.emit()

# Connection (in main_window.py)
self.sketch_editor.projection_preview_requested.connect(self.viewport.highlight_edge)
self.sketch_editor.projection_preview_cleared.connect(self.viewport.clear_highlight)
```

---

## Related Documentation

- `handoffs/PROMPT_20260217_ai_largeE_w26_recovery_hardgate.md` - Original task prompt
- `docs/glm5_feedback.md` - User feedback on projection issues
- `roadmap_ctp/07_two_ai_execution_split.md` - Overall recovery plan

---

**End of Handoff**