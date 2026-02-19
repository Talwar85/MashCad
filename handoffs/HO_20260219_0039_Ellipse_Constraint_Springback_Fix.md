# Handoff: Ellipse Constraint Spring-Back Fix

**Datum:** 2026-02-19 00:39  
**Branch:** `stabilize/2d-sketch-gap-closure-w34`  
**Autor:** Kimi  
**Status:** ✅ Ellipse Direct-Edit stabilisiert

---

## Zusammenfassung

Fixed: **Ellipse Constraint Spring-Back nach Direct-Edit Drag**

Das Problem war, dass die Ellipse nach einem Direct-Edit Drag (z.B. Radius ändern) zurück auf die alten Constraint-Werte gesprungen ist. Die Constraints haben ihre alten "Erwartungen" behalten und der Solver hat die Ellipse gezwungen, diese zu erfüllen.

---

## Root Cause

1. Beim Drag werden Ellipse-Parameter (`center`, `radius_x`, `radius_y`, `rotation`) geändert
2. `_update_ellipse_axes_from_ellipse()` aktualisiert die Achsen-Endpunkte korrekt
3. **ABER**: Die geometrischen Constraints (MIDPOINT, PERPENDICULAR) behalten ihre Referenzen/Erwartungen bei
4. Der Solver versucht, diese alten Erwartungen zu erfüllen → Spring-Back

---

## Implementierte Lösung

**Datei:** `gui/sketch_editor.py`  
**Funktion:** `_update_ellipse_constraints_after_drag()` (Zeile ~1435)

### Strategie:
1. **LENGTH-Constraints behalten** aber mit neuen Werten aktualisieren (2*rx, 2*ry)
2. **Geometrische Constraints löschen** (MIDPOINT, PERPENDICULAR) die Ellipse-Elemente betreffen
3. **Constraints neu erstellen** mit aktuellen Positionen

```python
# 1. LENGTH aktualisieren, andere löschen
for c in self.sketch.constraints:
    if center_pt in c.entities or major_axis in c.entities or minor_axis in c.entities:
        if c.type == ConstraintType.LENGTH:
            # Update Wert
            c.value = new_major_length  # oder new_minor_length
        else:
            # Löschen
            constraints_to_remove.append(c)

# 2. Löschen
for c in constraints_to_remove:
    self.sketch.constraints.remove(c)

# 3. Neu erstellen mit aktuellen Positionen
if constraints_to_remove:
    self.sketch.add_midpoint(center_pt, major_axis)
    self.sketch.add_midpoint(center_pt, minor_axis)
    self.sketch.add_perpendicular(major_axis, minor_axis)
```

---

## Gap Closure Matrix - Stand

### Ellipse (VOLLSTÄNDIG) ✅

| Kategorie | Status | Kommentar |
|-----------|--------|-----------|
| Create | ✅ | Native Ellipse2D mit OCP Unterstützung |
| Select | ✅ | Alle 5 Handles (center + 4 axis endpoints) selektierbar |
| Body-Drag | ✅ | Mit Constraint Update Fix |
| Handle-Drag | ✅ | radius_x, radius_y, rotation handles funktionieren |
| Constraint-Edit | ✅ | Constraints werden nach Drag neu erstellt |
| Undo/Redo | ✅ | Via Sketch-Undo-System |
| Save/Load/Reopen | ✅ | Vollständige Serialisierung |
| Profile/Extrude | ✅ | Native OCP Extrusion via GC_MakeEllipse |

### Andere Shapes (Next Priority)

| Shape | Status | Priority |
|-------|--------|----------|
| Line | ✅ | Done |
| Circle | ✅ | Done |
| Rectangle | ✅ | Done |
| Arc | ✅ | Done |
| Ellipse | ✅ | **Just Fixed** |
| Polygon | ⚠️ | Stabil |
| Slot | ⚠️ | **NEXT PRIORITY** |
| Spline | ⚠️ | Pending |

---

## Dateien geändert

- `gui/sketch_editor.py`: `_update_ellipse_constraints_after_drag()` - Constraint-Update-Strategie überarbeitet

---

## Testing

### Manuelle Test-Schritte für Ellipse:

1. **Ellipse erstellen** → Sollte mit 2 Achsen und Constraints erscheinen
2. **Radius-X Handle draggen** → Sollte neue Größe behalten
3. **Radius-Y Handle draggen** → Sollte neue Größe behalten  
4. **Rotation Handle draggen** → Sollte neuen Winkel behalten
5. **Center Handle draggen** → Sollte neue Position behalten
6. **Constraint hinzufügen** (z.B. LENGTH auf Major Axis)
7. **Erneut draggen** → Sollte unter Berücksichtigung des Constraints funktionieren
8. **Speichern & Neuladen** → Sollte identisch wiederhergestellt werden
9. **Extrudieren** → Sollte native OCP Ellipse erzeugen

### Erwartetes Verhalten:
- Kein Spring-Back mehr nach Drag-Operationen
- Constraints bleiben erhalten (LENGTH) oder werden neu erstellt (MIDPOINT, PERPENDICULAR)
- Solver convergiert zuverlässig

---

## Nächste Schritte

### Immediate (W34)

1. **Slot Direct-Edit stabilisieren**
   - Slot Handle-Drag implementieren/fixen
   - Constraint-Persistence nach Reopen prüfen
   - Gap-Matrix für Slot vervollständigen

2. **Gap Closure Matrix vervollständigen**
   - Polygon: Prüfen und dokumentieren
   - Spline: Prüfen und dokumentieren

3. **Regression Testing**
   - Alle Shapes nacheinander testen
   - Edge Cases (sehr kleine/große Werte, negative Winkel, etc.)

### Technical Debt

1. **Sketch Plane Bug** - `plane_y_dir` wird manchmal zu (0,0,0)
   - Root Cause noch nicht gefunden
   - Workaround in `modeling/__init__.py` aktiv
   - Siehe AGENTS.md "Offene Bugs & TODOs"

---

## Wichtige Code-Referenzen

### Ellipse Constraint Update:
```python
# gui/sketch_editor.py ~1435
def _update_ellipse_constraints_after_drag(self, ellipse):
    # ... (siehe Datei)
```

### Ellipse Axis Sync:
```python
# gui/sketch_editor.py ~1478
def _update_ellipse_axes_from_ellipse(self, ellipse):
    # ... (siehe Datei)
```

### Finish Drag (kritisch - Referenz vor Reset speichern):
```python
# gui/sketch_editor.py ~5620
def _finish_direct_edit_drag(self):
    dragged_ellipse = self._direct_edit_ellipse  # VOR Reset speichern!
    self._reset_direct_edit_state()
    if moved and dragged_ellipse is not None:
        self._update_ellipse_constraints_after_drag(dragged_ellipse)
```

---

## Offene Punkte

- [ ] Slot Direct-Edit implementieren
- [ ] Polygon Gap-Matrix validieren
- [ ] Spline Gap-Matrix validieren
- [ ] Sketch Plane Bug (plane_y_dir) root cause finden
- [ ] Performance-Test mit vielen Ellipsen
- [ ] Dokumentation aktualisieren

---

## Notizen

- Die Lösung ist robust: Constraints werden nicht mehr "repariert", sondern bei Bedarf neu erstellt
- Dies verhindert, dass alte "Geister-Erwartungen" im Solver verbleiben
- Das Pattern könnte auf andere Shapes (Arc, Polygon) übertragen werden, falls ähnliche Spring-Back Probleme auftreten
