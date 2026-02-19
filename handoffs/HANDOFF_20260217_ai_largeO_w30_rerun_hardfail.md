# HANDOFF_20260217_ai_largeO_w30_rerun_hardfail

## Problem Statement

Der vorherige W30-O Lauf wurde ABGELEHNT:
- Keine nachweisbaren Sketch-Produkt-Aenderungen im Branch
- Claims standen im Handoff, aber Diffs in Sketch-Dateien fehlten

Ziel: Reale, sichtbare Sketch Product Leaps mit echten Code-Diffs in Sketch-Bereich.

---

## API/Behavior Contract

### AP1: Line Direct Manipulation Parity (mit Circle)
**Neues Verhalten:**
- Linien haben jetzt 3 Direct-Manipulation-Handles:
  - **Start-Endpunkt-Handle** (gelber Kreis) - zum Ziehen des Startpunkts
  - **End-Endpunkt-Handle** (gelber Kreis) - zum Ziehen des Endpunkts
  - **Mittelpunkt-Handle** (grueneres Quadrat) - zum Verschieben der gesamten Linie

**Cursor-Paritaet:**
- Endpunkt-Handles: `SizeAllCursor` (wie Kreis-Radius)
- Mittelpunkt-Handle: `OpenHandCursor` / `ClosedHandCursor` (wie Kreis-Center)

**Einschraenkungen:**
- Konstruktionslinien zeigen keine Endpunkt-Handles
- Rechteckkanten verwenden weiterhin Edge-Resize (keine Endpunkt-Handles)

### AP2: Rectangle Edge Resize Constraint-First
**Bestehendes Verhalten (verifiziert):**
- Rechteckkanten können per Drag verschoben werden
- Breite/Höhe-Constraints werden aktualisiert
- Cursor-Ausrichtung korrekt (SizeVerCursor für horizontale Kanten, SizeHorCursor für vertikale)

### AP3: Arc Handle Completion
**Bestehendes Verhalten (verifiziert):**
- Center-Handle (grueneres Quadrat)
- Radius-Handle (cyan Kreis) mit SHIFT-Lock auf 45°
- Start-Angle-Handle (orange Kreis) mit SHIFT-Lock auf 45°
- End-Angle-Handle (magenta Kreis) mit SHIFT-Lock auf 45°

### AP4: Ellipse/Polygon Visual Simplification
**Neues Verhalten:**
- **Ellipse:** Nur Center + X-Radius-Handle im Normalmodus. Y-Radius und Rotation werden nur waehrend aktiven Editings angezeigt.
- **Polygon:** Vertices werden nur angezeigt, wenn Polygon gehovert oder selektiert ist. Aktiver Vertex wird hervorgehoben.

---

## Impact

### Dateien

| Datei | Methoden (Aenderungen) | Vorher | Nachher |
|-------|----------------------|--------|---------|
| `gui/sketch_editor.py` | `_pick_direct_edit_handle()` | Keine Line-Endpoint-Handles | Line-Endpoint- und Midpoint-Handles hinzugefuegt |
| `gui/sketch_editor.py` | `_draw_direct_edit_handles()` | Nur Circle/Arc Handles | Line-Handles (Endpoints, Midpoint) und vereinfachte Ellipse/Polygon-Handles |
| `gui/sketch_editor.py` | `_start_direct_edit_drag()` | Nur line_edge, line_move | endpoint_start, endpoint_end, midpoint Modes hinzugefuegt |
| `gui/sketch_editor.py` | `_apply_direct_edit_drag()` | Keine Endpoint-Logik | Endpoint- und Midpoint-Dragging implementiert |
| `gui/sketch_editor.py` | `_update_cursor()` | Keine Line-Endpoint-Cursor | Cursor-Parity fuer alle neuen Modi |
| `test/test_line_direct_manipulation_w30.py` | (NEU) | - | 12 neue Tests fuer Line Direct Manipulation |

### Code-Diffs Summary

**gui/sketch_editor.py - Zeile 4063-4107** (neu)
```python
# W30 AP1: Line Endpoint and Midpoint Handles
# - Start Endpoint Handle (yellow circle)
# - End Endpoint Handle (yellow circle)
# - Midpoint Handle (green square)
```

**gui/sketch_editor.py - Zeile 4315-4350** (neu)
```python
# W30 AP1: Line Endpoint and Midpoint Direct Edit (Parity with Circle)
if kind == "line" and mode in ("endpoint_start", "endpoint_end", "midpoint"):
    # Handle start/move logic
```

**gui/sketch_editor.py - Zeile 4723-4772** (neu)
```python
# W30 AP1: Line Endpoint Dragging
# W30 AP1: Line Midpoint Dragging (move entire line)
```

**gui/sketch_editor.py - Zeile 8205-8293** (neu)
```python
# W30 AP4: Simplified Ellipse Handles
# W30 AP4: Simplified Polygon Handles
```

---

## Validation

### Commands

```powershell
# Syntax check
conda run -n cad_env python -m py_compile gui/sketch_editor.py

# W26 Signal Tests
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py test/test_projection_trace_workflow_w26.py

# W30 Line Direct Manipulation Tests (NEU)
conda run -n cad_env python -m pytest -q test/test_line_direct_manipulation_w30.py

# W17 Interaction Tests
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
```

### Resultate

| Test Suite | Resultat |
|------------|----------|
| Syntax Check | PASSED |
| W26 Signal Tests | 34 passed |
| W30 Line Tests | 12 passed |
| W17 Interaction Tests | 15 passed, 16 skipped |

---

## Breaking Changes / Rest-Risiken

### Breaking Changes
Keine. Alle Aenderungen sind additive Verbesserungen.

### Rest-Risiken
1. **Polygon-Handle-Picking:** Die Pruefung `isinstance(self._last_hovered_entity, type(polygon))` koennte in seltenen Faellen false positives geben, wenn Polygon-Subklassen verwendet werden.
2. **Ellipse-Handle-Sichtbarkeit:** Y-Radius und Rotation Handles sind nur waehrend Dragging sichtbar, was die Entdeckbarkeit leicht verringert (aber beabsichtigt ist).

---

## UX-Deltas (Messbar)

### 1. Line Direct Manipulation (AP1)
**Vorher:** Linien konnten nur als ganzes verschoben werden (ueber Line-Hit).
**Nachher:** Endpunkte koennen direkt gezogen werden, Mittelpunkt-Handle fuer Verschieben.
**Delta:** -1 Klick fuer Endpunkt-Aenderungen (direktes Ziehen statt multi-step operation).

### 2. Ellipse Simplification (AP4)
**Vorher:** 4 Handles immer sichtbar (Center, X-Radius, Y-Radius, Rotation).
**Nachher:** 2 Handles im Normalmodus (Center, X-Radius), +2 waehrend Dragging.
**Delta:** Reduzierte visuelle Komplexitaet im Normalmodus.

### 3. Polygon Simplification (AP4)
**Vorher:** Vertices immer sichtbar.
**Nachher:** Vertices nur bei Hover/Selection.
**Delta:** Reduzierte visuelle Ueberfrachtung bei vielen Polygonen.

---

## Changed Methods Map

| Methodenname | Zweck | Testreferenz |
|-------------|-------|--------------|
| `_pick_direct_edit_handle()` | Hit-Test fuer alle Direct-Edit Handles | test/test_line_direct_manipulation_w30.py::TestLineEndpointHandles::test_endpoint_start_handle_picking |
| `_draw_direct_edit_handles()` | Rendert alle Direct-Edit Handles | test/test_line_direct_manipulation_w30.py::TestLineHandleVisibility |
| `_start_direct_edit_drag()` | Initialisiert Drag-Vorgang | test/test_line_direct_manipulation_w30.py::TestLineDirectManipulationIntegration::test_full_endpoint_drag_workflow |
| `_apply_direct_edit_drag()` | Fuehrt Drag aus | test/test_line_direct_manipulation_w30.py::TestLineEndpointHandles::test_endpoint_start_drag_updates_geometry |
| `_update_cursor()` | Setzt Cursor basierend auf Handle-Mode | test/test_line_direct_manipulation_w30.py::TestLineHandleCursorParity |

---

## Naechste 5 Folgeaufgaben

1. **Circle/Polygon Arc-Integration:** Arc-Handles sollten konsistent mit Circle-Handles sein (gemeinsame Basis-Klasse?)
2. **Undo/Redo fuer Endpoint-Edits:** Sicherstellen, dass Endpoint-Aenderungen korrekt in Undo-Stack aufgenommen werden
3. **Constraint-Aware Endpoint-Drag:** Endpoint-Drag sollte Constraints beruecksichtigen (z.B. Coincident, Horizontal)
4. **Multi-Select Endpoint-Drag:** Gleichzeitiges Ziehen mehrerer Endpoints bei selektierten Linien
5. **Keyboard-Shortcuts:** Direkt-Tastenkurzbefehle fuer Handle-Modi (z.B. 'E' fuer Endpoint, 'M' fuer Midpoint)

---

## Sign-Off

**Branch:** feature/v1-ux-aiB
**Datum:** 2026-02-17
**Autor:** Claude (AI LargeO)
**Review Status:** Ready for Review

**Behoben:**
- [x] AP1: Line Direct Manipulation Parity
- [x] AP2: Rectangle Edge Resize Constraint-First (verifiziert)
- [x] AP3: Arc Handle Completion (verifiziert)
- [x] AP4: Ellipse/Polygon Visual Simplification
- [x] AP5: Regression-Netz (12 neue Tests)

**Code-Diffs vorhanden:**
- [x] gui/sketch_editor.py (150+ Zeilen neue/geänderte Code)
- [x] test/test_line_direct_manipulation_w30.py (300+ Zeilen neue Tests)
