# Handoff: Slot Direct-Edit Constraint Update

**Datum:** 2026-02-19 00:42  
**Branch:** `stabilize/2d-sketch-gap-closure-w34`  
**Autor:** Kimi  
**Status:** ✅ Slot Constraint Update implementiert

---

## Zusammenfassung

Implemented: **Slot Constraint Update nach Direct-Edit Drag**

Analog zum Ellipse-Fix wurde jetzt auch für Slots eine Constraint-Aktualisierung implementiert. Beim Radius-Change müssen die DISTANCE-Constraints aktualisiert werden, die den Slot-Radius definieren.

---

## Problem

Beim Slot-Drag (besonders Radius-Change) wurden die Constraints nicht aktualisiert:
- Der Slot besteht aus 2 Arcs (Endkappen) und 2 Linien (Kanten)
- Die DISTANCE-Constraints definieren den Abstand vom Arc-Center zu den Top/Bottom Punkten (= Radius)
- Nach einem Radius-Drag waren diese Constraints auf dem alten Wert
- Der Solver hat versucht, die alten Werte zu erzwingen → unerwartetes Verhalten

---

## Implementierung

### Neue Funktion: `_update_slot_constraints_after_drag()`

**Datei:** `gui/sketch_editor.py` (nach `_update_ellipse_axes_from_ellipse`)

```python
def _update_slot_constraints_after_drag(self, slot_line, mode):
    """
    Aktualisiert Constraints nach Slot Direct-Edit Drag.
    """
    from sketcher.constraints import ConstraintType
    
    # Finde alle Slot-Arcs und deren Center-Punkte
    slot_arc_centers = set()
    current_radius = None
    for arc in self.sketch.arcs:
        if hasattr(arc, '_slot_arc') and arc._slot_arc:
            slot_arc_centers.add(id(arc.center))
            if current_radius is None:
                current_radius = arc.radius
    
    if not slot_arc_centers or current_radius is None:
        return
    
    # DISTANCE-Constraints aktualisieren
    updated_count = 0
    for c in self.sketch.constraints:
        if c.type == ConstraintType.DISTANCE:
            entities = c.entities
            if len(entities) >= 2:
                # Prüfe, ob eines der Entities ein Slot-Arc-Center ist
                is_slot_distance = any(id(e) in slot_arc_centers for e in entities)
                if is_slot_distance:
                    c.value = current_radius
                    updated_count += 1
    
    if updated_count > 0:
        logger.debug(f"[Slot] Updated {updated_count} DISTANCE constraints to radius={current_radius}")
```

### Integration in `_finish_direct_edit_drag()`

```python
# WICHTIG: Ellipse und Slot VOR dem Reset speichern!
dragged_ellipse = self._direct_edit_ellipse
dragged_slot = self._direct_edit_slot

self._reset_direct_edit_state()

if moved:
    # Ellipse Constraints aktualisieren
    if dragged_ellipse is not None and mode in ("center", "radius_x", "radius_y", "rotation"):
        self._update_ellipse_constraints_after_drag(dragged_ellipse)
    
    # NEU: Slot-Constraints aktualisieren
    if dragged_slot is not None and mode in ("center", "length_start", "length_end", "radius"):
        self._update_slot_constraints_after_drag(dragged_slot, mode)
    
    result = self.sketch.solve()
```

### Status-Meldung hinzugefügt

```python
elif mode in ("length_start", "length_end"):
    self.status_message.emit(tr("Slot length updated"))
```

---

## Slot Struktur (Reminder)

Ein Slot besteht aus:

1. **Center-Line** (Konstruktion): `line_center` mit `_slot_center_line = True`
2. **Top/Bottom Linien**: `line_top`, `line_bot` mit `_slot_parent_center_line = line_center`
3. **Endkappen (Arcs)**: `arc1`, `arc2` mit `_slot_arc = True`
4. **Constraints**:
   - 2x `PERPENDICULAR` (Caps senkrecht zu Center)
   - 2x `MIDPOINT` (Center-Punkte sind Mittelpunkte der Caps)
   - 4x `DISTANCE` (Radius: Center → Top/Bottom Punkte)
   - 2x `COINCIDENT` (Arc-Center = Center-Line Endpunkte)
   - 4x `POINT_ON_CIRCLE` (Top/Bottom auf Arcs)
   - 1x `TANGENT` (Tangentialer Übergang)

---

## Gap Closure Matrix - Slot Stand

| Kategorie | Status | Kommentar |
|-----------|--------|-----------|
| Create | ✅ | `add_slot()` mit robustem Skelett |
| Select | ⚠️ | Center-Line selektierbar, aber nicht intuitiv |
| Body-Drag | ✅ | Via Center-Line (mode="center") |
| Handle-Drag | ✅ | Length + Radius handles implementiert |
| Constraint-Edit | ✅ | **NEU: Constraints werden nach Drag aktualisiert** |
| Undo/Redo | ✅ | Via Sketch-Undo-System |
| Save/Load/Reopen | ⚠️ | Muss validiert werden |
| Profile/Extrude | ⚠️ | Muss validiert werden |

---

## Testing

### Manuelle Test-Schritte für Slot:

1. **Slot erstellen** → Sollte 2 Arcs + 2 Linien mit Constraints zeigen
2. **Slot verschieben** (Center-Handle) → Sollte alle Komponenten bewegen
3. **Länge ändern** (Start/End-Handle) → Sollte Slot verlängern/verkürzen
4. **Radius ändern** (Arc-Handle) → Sollte neuen Radius behalten
5. **Constraint prüfen** → DISTANCE-Constraints sollten neuen Radius-Wert haben
6. **Solver** → Sollte convergieren ohne Spring-Back
7. **Speichern & Neuladen** → Slot sollte identisch wiederhergestellt werden
8. **Extrudieren** → Sollte soliden Slot erzeugen

### Erwartetes Verhalten:
- Kein Spring-Back nach Radius-Change
- DISTANCE-Constraints aktualisieren sich auf neuen Radius
- Solver convergiert zuverlässig

---

## Bekannte Probleme / TODOs

1. **Save/Load/Reopen** noch nicht validiert
   - Slot-Marker (`_slot_arc`, `_slot_center_line`) müssen persistiert werden
   - Oder: Slot-Struktur muss bei Reload neu aufgebaut werden

2. **Profile/Extrude** noch nicht validiert
   - Slot sollte als geschlossenes Profil erkannt werden
   - Extrusion sollte soliden Körper erzeugen

3. **Select-Verbesserung** möglich
   - Derzeit nur Center-Line selektierbar
   - Könnte verbessert werden, um direkt auf Slot-Komponenten zu selektieren

---

## Nächste Schritte

### Immediate (W34)

1. **Slot Save/Load/Reopen validieren**
   - Test: Slot erstellen → Speichern → Neuladen
   - Prüfen: Alle Marker vorhanden?
   - Prüfen: Direct-Edit funktioniert nach Reload?

2. **Slot Profile/Extrude validieren**
   - Test: Slot als Profil verwenden
   - Test: Slot extrudieren

3. **Gap Closure Matrix vervollständigen**
   - Polygon: Prüfen und dokumentieren
   - Spline: Prüfen und dokumentieren

---

## Code-Referenzen

### Slot-Constraint-Update:
```python
# gui/sketch_editor.py ~1555
def _update_slot_constraints_after_drag(self, slot_line, mode):
    # ... (siehe Datei)
```

### Slot-Drag-Handling:
```python
# gui/sketch_editor.py ~5478
if self._direct_edit_slot is not None:
    slot = self._direct_edit_slot
    mode = self._direct_edit_mode
    # ... (siehe Datei)
```

### Slot-Erstellung:
```python
# sketcher/sketch.py ~715
def add_slot(self, x1, y1, x2, y2, radius, construction=False):
    # ... (siehe Datei)
```

---

## Zusammenhang mit Ellipse-Fix

Dieser Slot-Fix folgt dem gleichen Muster wie der Ellipse-Fix:
- Constraints werden nach Drag aktualisiert
- Vor dem `self._reset_direct_edit_state()` die Referenz speichern
- Nach dem Reset die Update-Funktion aufrufen
- Dann erst `self.sketch.solve()`

Das Pattern könnte auf andere komplexe Shapes (Polygon, Spline) übertragen werden.
