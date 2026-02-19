# Handoff: Slot Radius Drag Fix

**Datum:** 2026-02-19 08:49  
**Branch:** `stabilize/2d-sketch-gap-closure-w34`  
**Autor:** Kimi  
**Status:** ✅ Slot Radius Drag korrigiert

---

## Problem

Beim Slot-Radius-Drag passierten folgende Fehler:
1. **Nur Arcs wurden aktualisiert**, aber die Top/Bottom Linien blieben an ihrer Position
2. **Constraints nicht erfüllt** - Solver konnte die Geometrie nicht auflösen
3. **Vorschau nicht aktualisiert** - Änderungen nur nach Solve sichtbar

**Root Cause:**
- Die Top/Bottom Linien mussten mit dem neuen Radius weiter nach außen rutschen
- Die DISTANCE-Constraints mussten auf den neuen Radius aktualisiert werden

---

## Lösung

### Slot-Radius-Drag Code (`gui/sketch_editor.py`)

```python
elif mode == "radius":
    arc = self._direct_edit_slot_arc
    if arc is not None:
        dx = world_pos.x() - self._direct_edit_start_pos.x()
        new_radius = self._direct_edit_slot_start_radius + dx
        new_radius = max(0.01, abs(new_radius))
        
        # WICHTIG: Radius-Delta berechnen für Linien-Verschiebung
        radius_delta = new_radius - self._direct_edit_slot_start_radius

        # Update both arc caps
        for slot_arc in self.sketch.arcs:
            if hasattr(slot_arc, '_slot_arc') and slot_arc._slot_arc:
                slot_arc.radius = new_radius
                # ... marker updates ...
        
        # WICHTIG: Top/Bottom Linien mit verschieben!
        cx1, cy1 = slot.start.x, slot.start.y
        cx2, cy2 = slot.end.x, slot.end.y
        dx_line = cx2 - cx1
        dy_line = cy2 - cy1
        length = math.hypot(dx_line, dy_line)
        if length > 1e-9:
            # Normalisierte Normale (senkrecht zur Center-Line)
            nx = -dy_line / length
            ny = dx_line / length
            
            # Finde Top/Bottom Linien und deren Punkte verschieben
            for line in self.sketch.lines:
                if getattr(line, '_slot_parent_center_line', None) is slot:
                    # Bestimme ob Top oder Bottom
                    mid_x = (line.start.x + line.end.x) / 2
                    mid_y = (line.start.y + line.end.y) / 2
                    center_mid_x = (cx1 + cx2) / 2
                    center_mid_y = (cy1 + cy2) / 2
                    dir_x = mid_x - center_mid_x
                    dir_y = mid_y - center_mid_y
                    dot = dir_x * nx + dir_y * ny
                    
                    # Punkte verschieben (nicht Linien direkt!)
                    if dot > 0:  # Top
                        line.start.x += nx * radius_delta
                        line.start.y += ny * radius_delta
                        line.end.x += nx * radius_delta
                        line.end.y += ny * radius_delta
                    else:  # Bottom
                        line.start.x -= nx * radius_delta
                        line.start.y -= ny * radius_delta
                        line.end.x -= nx * radius_delta
                        line.end.y -= ny * radius_delta
```

---

## Wichtige Änderungen

### 1. Radius-Delta berechnen
```python
radius_delta = new_radius - self._direct_edit_slot_start_radius
```

### 2. Normale zur Center-Line berechnen
```python
nx = -dy_line / length  # Senkrecht zur Center-Line
ny = dx_line / length
```

### 3. Punkte verschieben (nicht Linien direkt)
- Die Linien verwenden Point2D-Objekte als start/end
- Wenn die Punkte verschoben werden, folgen die Linien automatisch
- Die Cap-Linien folgen automatisch, da sie dieselben Punkte verwenden

### 4. Top vs Bottom unterscheiden
- Skalarprodukt `dot` bestimmt, auf welcher Seite der Center-Line die Linie liegt
- `dot > 0`: Top (in Richtung Normale)
- `dot < 0`: Bottom (entgegen Normale)

---

## Slot Geometrie (Reminder)

```
        t1 -------- t2
       /               \
      |   Center-Line   |
       \               /
        b1 -------- b2

- Center-Line: Verbindet Arc-Center (c1, c2)
- Top-Linie: Verbindet t1, t2
- Bottom-Linie: Verbindet b1, b2
- Caps: Senkrechte Linien bei c1, c2
- Arcs: Halbkreise bei c1, c2

Abstand Center-Line zu Top/Bottom = Radius
```

---

## Constraint-Update

Die `_update_slot_constraints_after_drag()` aktualisiert DISTANCE-Constraints:
- Findet Slot-Arcs über `_slot_arc` Marker
- Aktualisiert DISTANCE-Constraints auf neuen Radius
- Wird in `_finish_direct_edit_drag()` aufgerufen

---

## Testing

### Slot Radius Drag Test:
1. Slot erstellen
2. Radius-Handle (auf Arc) draggen
3. **Erwartet:** 
   - Beide Arcs werden größer/kleiner
   - Top/Bottom Linien rutschen mit
   - Vorschau wird aktualisiert
   - Solver convergiert ohne Fehler

---

## Nächste Schritte

1. **Manuelles Testing** des Slot-Radius-Drag
2. **Polygon & Spline** auf gleichem Niveau bringen
   - Polygon: bereits OK
   - Spline: Einzelsegment-Selektion fixen
3. **Gap Closure abschließen**

---

## Dateien geändert

- `gui/sketch_editor.py` - Slot-Radius-Drag aktualisiert
  - Punkte werden mit verschoben
  - Top/Bottom korrekt identifiziert

---

## Bemerkung zu Spline

Wie bemerkt: Spline hat das Problem, dass einzelne Segmente selektiert werden statt des gesamten Splines. Das macht Drag&Drop kaputt.

**Mögliche Lösung:**
- Spline als einheitliches Objekt behandeln
- Keine Einzelsegment-Selektion zulassen
- Oder: Einzelsegment-Drag verschiebt gesamten Spline
