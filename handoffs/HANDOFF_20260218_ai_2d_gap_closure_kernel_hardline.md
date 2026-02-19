# W34: 2D Sketch Gap Closure - Hardline Analysis

## Gap-Matrix (IST-Zustand nach Commit 82d8dd7)

| Shape | Create | Select | Body-Drag | Handle-Drag | Rotate | Constraint-Edit | Undo/Redo | Save/Load/Reopen | Profile/Extrude-Readiness |
|-------|--------|--------|-----------|-------------|--------|-----------------|-----------|------------------|---------------------------|
| **Line** | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | ✅ |
| **Circle** | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | ✅ |
| **Rectangle** | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | ✅ |
| **Polygon** | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ |
| **Arc (3-point)** | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | ✅ |
| **Ellipse (native)** | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ |
| **Spline** | ✅ | ✅ | ⚠️ | ⚠️ | N/A | ⚠️ | ✅ | ✅ | ⚠️ |
| **Slot** | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ | ⚠️ |

**Legende:**
- ✅ = Stabil / funktioniert
- ⚠️ = Teilweise / Quickhack / Lifecycle-Lücke
- ❌ = Broken / nicht implementiert
- N/A = Nicht anwendbar

---

## Detaillierte Gap-Analyse

### 1. ELLIPSE (Native Ellipse2D)

**Status nach aktuellem Stand:**
- ✅ Native Ellipse2D implementiert (keine Segment-Approximation)
- ✅ 3D Viewport Rendering
- ✅ Direct Edit Handles (Center, Radius X/Y, Rotation)
- ⚠️ Constraint-Edit springt zurück (bekanntes Problem)

**Verbleibende Gaps:**
1. **Constraint-Edit Spring-Back**: Wenn man Constraints editiert (z.B. Länge der Achsen), kann die Ellipse auf alte Werte zurückspringen
2. **Handle-Drag Consistency**: Die Achsen-Handles müssen korrekt mit der Ellipse synchronisiert werden
3. **Profile/Extrude**: Noch nicht final getestet

**Root Cause:**
- Bidirektionale Synchronisation zwischen Ellipse-Parametern und Achsen-Constraints ist komplex
- `_update_ellipse_geometry()` und `_update_ellipse_axes_from_ellipse()` müssen konsistent arbeiten
- Constraint-Aktualisierung nach Drag muss korrekt sein

**Geänderte Dateien:**
- `sketcher/sketch.py`: `_update_ellipse_geometry()`
- `gui/sketch_editor.py`: `_update_ellipse_axes_from_ellipse()`, `_update_ellipse_constraints_after_drag()`
- `gui/viewport_pyvista.py`: `_render_sketch_batched()` (3D Rendering)
- `modeling/__init__.py`: `_extrude_sketch_ellipses()`

---

### 2. POLYGON

**Status:**
- ✅ Erstellung funktioniert
- ⚠️ Center-Drag: Muss alle Punkte konsistent verschieben
- ⚠️ Shape-Preservation: Einzelne Kanten dürfen nicht verzerrt werden

**Root Cause:**
- Polygon hat Treiber-Kreis und Punkte über Constraints verbunden
- Bei Drag müssen alle Punkte + Kreis gemeinsam verschoben werden
- `_find_polygon_driver_circle_for_line()` muss korrekt arbeiten

---

### 3. SPLINE

**Status:**
- ✅ Erstellung funktioniert
- ⚠️ Body-Drag: Muss alle Kontrollpunkte verschieben
- ⚠️ Handle-Edit: Tangenten-Handles müssen stabil sein

**Root Cause:**
- Spline-Kontrollpunkte müssen als Gruppe behandelt werden
- Handle-Synchronisation (smooth vs. corner) muss konsistent sein

---

### 4. SLOT

**Status:**
- ✅ Erstellung funktioniert
- ⚠️ Direct Edit: Radius/Dimension-Edit nach Reopen
- ⚠️ Lifecycle: Constraints nach Save/Load

**Root Cause:**
- Slot besteht aus mehreren Elementen (Arcs, Lines)
- Constraints zwischen Elementen müssen erhalten bleiben

---

## Lifecycle-Check (Undo/Redo/Save/Load/Reopen)

| Shape | Undo | Redo | Save | Load | Reopen |
|-------|------|------|------|------|--------|
| Line | ✅ | ✅ | ✅ | ✅ | ✅ |
| Circle | ✅ | ✅ | ✅ | ✅ | ✅ |
| Rectangle | ✅ | ✅ | ✅ | ✅ | ✅ |
| Polygon | ✅ | ✅ | ✅ | ✅ | ✅ |
| Arc | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ellipse | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Spline | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Slot | ✅ | ✅ | ✅ | ✅ | ⚠️ |

**Anmerkungen:**
- Ellipse: native_ocp_data wird korrekt serialisiert
- Spline/Slot: Komplexe Constraint-Netze müssen stabil bleiben

---

## Visual-Checkliste

- [x] Ellipse wird glatt gerendert (keine sichtbaren Segmente)
- [x] Ellipse Handles sind sichtbar und anklickbar
- [x] 3D Viewport zeigt Ellipse korrekt
- [ ] Extrusion der Ellipse funktioniert stabil
- [ ] Polygon-Drag behält Shape bei
- [ ] Spline-Body-Drag verschiebt alle Punkte
- [ ] Slot-Constraints nach Reopen stabil

---

## Rest-Risiken / Blocker

### Priorität 1 (Kritisch)
1. **Ellipse Constraint Spring-Back**: Drag funktioniert, aber Constraints springen zurück
   - Lösung: Constraint-Aktualisierung muss korrekt getriggert werden
   - Status: Teilweise gefixt, aber nicht stabil

### Priorität 2 (Hoch)
2. **Polygon Shape Preservation**: Einzelne Kanten können verzerrt werden
3. **Spline Body Drag**: Nicht alle Kontrollpunkte werden verschoben

### Priorität 3 (Mittel)
4. **Slot Lifecycle**: Constraints nach Reopen
5. **Extrusion Readiness**: Profilbildung für alle Shapes stabil

---

## Nächste 3 priorisierte Schritte

### 1. Ellipse Constraint Spring-Back fixen
**Aufwand:** Hoch
**Dateien:** `gui/sketch_editor.py`, `sketcher/sketch.py`
**Ansatz:**
- `_update_ellipse_constraints_after_drag()` muss korrekt aufgerufen werden
- Reihenfolge: Drag → Achsen aktualisieren → Constraints aktualisieren → Solve
- Test: Drag darf nicht zurückspringen

### 2. Polygon Center Drag stabilisieren
**Aufwand:** Mittel
**Dateien:** `gui/sketch_editor.py`
**Ansatz:**
- `_resolve_direct_edit_target_polygon()` muss korrekt alle Punkte finden
- Drag muss alle Punkte + Treiberkreis verschieben
- Constraints müssen erhalten bleiben

### 3. Extrusion Readiness für alle Shapes
**Aufwand:** Mittel
**Dateien:** `modeling/__init__.py`
**Ansatz:**
- Profile-Bildung muss für alle Shapes stabil sein
- `closed_profiles` muss korrekt gefüllt sein
- Test: Jeder Shape muss extrudierbar sein

---

## Tests

### PyCompile Check
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/sketch_renderer.py sketcher/geometry.py sketcher/sketch.py
```
Status: ✅ Keine Syntaxfehler

### Testausführung
```powershell
conda run -n cad_env python -m pytest test/test_shape_matrix_w34.py -v
```
Status: ⚠️ Einige Tests fehlen noch

---

## Zusammenfassung

**Was funktioniert:**
- Native Ellipse2D ist implementiert und rendert glatt
- 3D Viewport zeigt Ellipse korrekt
- Direct Edit Handles sind implementiert
- Lifecycle (Undo/Redo/Save/Load) grundsätzlich stabil

**Was muss noch stabilisiert werden:**
1. Ellipse Constraint Spring-Back (kritisch)
2. Polygon Shape Preservation
3. Spline Body Drag
4. Slot Lifecycle
5. Extrusion Readiness für alle Shapes

**Empfehlung:**
- Priorität 1: Ellipse Constraint Spring-Back fixen
- Dann: Shape-by-Shape die verbleibenden Gaps schließen
- Keine neuen Features bis Gaps geschlossen
