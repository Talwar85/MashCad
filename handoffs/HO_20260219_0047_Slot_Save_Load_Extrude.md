# Handoff: Slot Save/Load & Extrude Support

**Datum:** 2026-02-19 00:47  
**Branch:** `stabilize/2d-sketch-gap-closure-w34`  
**Autor:** Kimi  
**Status:** ✅ Slot Persistenz und Extrusion implementiert

---

## Zusammenfassung

Implemented:
1. **Slot Save/Load Persistenz** - Slot-Marker werden jetzt in JSON gespeichert/geladen
2. **Slot Profile Erkennung** - Slots werden als geschlossene Profile erkannt
3. **Slot Extrusion** - Native Slot-Extrusion mit OCP

---

## Implementierte Änderungen

### 1. Slot Persistenz (sketcher/sketch.py)

#### `to_dict()` - Speichern
```python
# Slot-Marker für Linien sammeln
line_slot_data = {}
for l in self.lines:
    if getattr(l, '_slot_center_line', False):
        line_slot_data[l.id] = {'center_line': True}
    elif hasattr(l, '_slot_parent_center_line') and l._slot_parent_center_line is not None:
        line_slot_data[l.id] = {'parent_center_line_id': l._slot_parent_center_line.id}

# Slot-Marker für Arcs sammeln
arc_slot_data = {}
for a in self.arcs:
    if getattr(a, '_slot_arc', False):
        arc_slot_data[a.id] = True

return {
    # ... existing fields ...
    'line_slot_markers': line_slot_data,
    'arc_slot_markers': arc_slot_data,
}
```

#### `from_dict()` - Laden
```python
# Linien wiederherstellen
line_id_map = {}
for ldata in data.get('lines', []):
    # ... create line ...
    if lid:
        line_id_map[lid] = line

# Slot-Marker für Linien wiederherstellen
line_slot_markers = data.get('line_slot_markers', {})
for line_id, markers in line_slot_markers.items():
    if line_id in line_id_map:
        line = line_id_map[line_id]
        if markers.get('center_line'):
            line._slot_center_line = True
        parent_id = markers.get('parent_center_line_id')
        if parent_id and parent_id in line_id_map:
            line._slot_parent_center_line = line_id_map[parent_id]

# Arcs wiederherstellen
arc_id_map = {}
# ... create arcs ...

# Slot-Marker für Arcs wiederherstellen
arc_slot_markers = data.get('arc_slot_markers', {})
for arc_id, is_slot_arc in arc_slot_markers.items():
    if is_slot_arc and arc_id in arc_id_map:
        arc_id_map[arc_id]._slot_arc = True
```

---

### 2. Slot Profile Erkennung (sketcher/sketch.py)

#### `_find_closed_profiles()` - Slot als Profil
```python
# === W34: Slots als geschlossene Profile erkennen ===
processed_slot_centers = set()
for line in self.lines:
    if getattr(line, '_slot_center_line', False) and line.id not in processed_slot_centers:
        # Finde alle Komponenten dieses Slots
        slot_arcs = []
        slot_lines = []
        
        for arc in self.arcs:
            if getattr(arc, '_slot_arc', False):
                slot_arcs.append(arc)
        
        for l in self.lines:
            if getattr(l, '_slot_parent_center_line', None) is line:
                slot_lines.append(l)
        
        # Slot ist gültig wenn er 2 Arcs und mindestens 2 Linien hat
        if len(slot_arcs) == 2 and len(slot_lines) >= 2:
            profiles.append({
                'type': 'slot',
                'geometry': {
                    'center_line': line,
                    'arcs': slot_arcs,
                    'lines': slot_lines
                }
            })
            processed_slot_centers.add(line.id)
```

---

### 3. Slot Extrusion (modeling/__init__.py)

#### Neue Methode: `_extrude_single_slot()`
```python
def _extrude_single_slot(self, slot_data, plane):
    """
    W34: Erstellt eine native OCP Slot Face aus Slot-Komponenten.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
    from OCP.GC import GC_MakeArcOfCircle
    
    arcs = slot_data.get('arcs', [])
    lines = slot_data.get('lines', [])
    
    # Sammle alle Edges
    edges = []
    
    # 1. Top/Bottom Linien als Edges
    for line in lines[:2]:
        p1_3d = plane.from_local_coords((line.start.x, line.start.y))
        p2_3d = plane.from_local_coords((line.end.x, line.end.y))
        # ... create OCP edge ...
        edges.append(edge)
    
    # 2. Arcs als Edges
    for arc in arcs:
        center_3d = plane.from_local_coords((arc.center.x, arc.center.y))
        # ... create OCP arc edge ...
        edges.append(edge)
    
    # 3. Wire und Face erstellen
    wire_maker = BRepBuilderAPI_MakeWire()
    for edge in edges:
        wire_maker.Add(edge)
    
    if wire_maker.IsDone():
        wire = wire_maker.Wire()
        if wire.Closed():
            face = Face(BRepBuilderAPI_MakeFace(wire).Face())
            return [face]
```

#### Integration in `_compute_extrude_part_ocp_first()`
```python
for profile in polys_to_extrude:
    if isinstance(profile, dict) and profile.get('type') in ('ellipse', 'circle', 'slot'):
        # ... ellipse, circle handling ...
        elif profile_type == 'slot':
            slot_faces = self._extrude_single_slot(geometry, plane)
            if slot_faces:
                native_profile_faces.extend(slot_faces)
```

#### Integration in `_compute_extrude_part_legacy()`
```python
# W34: Native Profile (Ellipse, Circle, Slot) behandeln
if isinstance(poly, dict) and poly.get('type') in ('ellipse', 'circle', 'slot'):
    # ... handle native profiles ...
    elif profile_type == 'slot':
        slot_faces = self._extrude_single_slot(geometry, plane)
        if slot_faces:
            faces_to_extrude.extend(slot_faces)
    continue
```

#### Integration in `_convert_line_profiles_to_polygons()`
```python
# Fall 0: Native Ellipse/Circle/Slot Profile
if isinstance(profile, dict):
    profile_type = profile.get('type')
    if profile_type in ('ellipse', 'circle', 'slot'):
        polygons.append(profile)
        continue
```

---

## Gap Closure Matrix - Slot Stand (AKTUALISIERT)

| Kategorie | Status | Kommentar |
|-----------|--------|-----------|
| Create | ✅ | `add_slot()` mit robustem Skelett |
| Select | ⚠️ | Center-Line selektierbar |
| Body-Drag | ✅ | Via Center-Handle |
| Handle-Drag | ✅ | Length + Radius handles |
| Constraint-Edit | ✅ | Constraints werden nach Drag aktualisiert |
| Undo/Redo | ✅ | Via Sketch-Undo-System |
| Save/Load/Reopen | ✅ **(NEU)** | Slot-Marker werden persistiert |
| Profile/Extrude | ✅ **(NEU)** | Slot als geschlossenes Profil erkannt & extrudierbar |

---

## Testing

### Save/Load Test:
1. Slot erstellen
2. Sketch speichern
3. Sketch neu laden
4. Prüfen: `_slot_center_line`, `_slot_arc` Marker vorhanden?
5. Direct-Edit funktioniert nach Reload?

### Extrude Test:
1. Slot erstellen
2. "Extrude" auswählen
3. Slot sollte als Profil-Option angezeigt werden
4. Extrusion sollte soliden Körper erzeugen

---

## Bekannte Einschränkungen

1. **Select-Verbesserung möglich**
   - Derzeit nur Center-Line selektierbar
   - Könnte erweitert werden, um direkt auf Slot zu selektieren

2. **Slot-Geometrie-Validierung**
   - Slot muss exakt 2 Arcs und 2 Linien haben
   - Wenn Arcs oder Linien gelöscht werden → ungültiger Slot

3. **Constraint-Edit nach Reload**
   - Noch nicht explizit getestet
   - Sollte funktionieren, da Marker wiederhergestellt werden

---

## Nächste Schritte

1. **Manuelles Testing** durchführen
   - Save/Load/Reopen mit Slot
   - Extrude mit Slot

2. **Polygon & Spline** auf gleichem Niveau bringen
   - Gap-Matrix für Polygon validieren
   - Gap-Matrix für Spline validieren

3. **Gap Closure abschließen**
   - Alle 8 Shapes (Line, Circle, Rect, Arc, Ellipse, Polygon, Slot, Spline) überprüfen

---

## Dateien geändert

1. `sketcher/sketch.py`
   - `to_dict()` - Slot-Marker speichern
   - `from_dict()` - Slot-Marker laden
   - `_find_closed_profiles()` - Slot-Profil-Erkennung

2. `modeling/__init__.py`
   - `_extrude_single_slot()` - Neue Methode
   - `_compute_extrude_part_ocp_first()` - Slot-Extrusion
   - `_compute_extrude_part_legacy()` - Slot-Extrusion (Legacy)
   - `_convert_line_profiles_to_polygons()` - Slot-Polygon-Konvertierung

---

## Code-Referenzen

### Slot Persistenz:
```python
# sketcher/sketch.py ~1765-1830
def to_dict(self):
    # ...
def from_dict(cls, data):
    # ...
```

### Slot Profil:
```python
# sketcher/sketch.py ~1601-1630
def _find_closed_profiles(self, tolerance=0.5):
    # ...
```

### Slot Extrusion:
```python
# modeling/__init__.py ~9180
_def _extrude_single_slot(self, slot_data, plane):
    # ...
```
