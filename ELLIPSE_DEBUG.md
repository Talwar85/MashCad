# Ellipse Debug Guide

## Letzte Änderungen (Fixes für Drag & 3D)

### 1. Drag & Drop Fix
**Problem**: Handles wurden selektiert aber nicht verschoben

**Fix**: `gui/sketch_editor.py`
- Neue Methode `_update_ellipse_axes_from_ellipse()` 
- Aktualisiert Achsen-Endpunkte aus Ellipse-Parametern (nach Drag)
- Vorher: `_update_ellipse_geometry()` hat Ellipse aus Achsen berechnet → überschrieb Drag!

### 2. 3D Visualisierung
**Problem**: Ellipse nicht sichtbar im 3D Viewport

**Fix**: `gui/viewport_pyvista.py` 
- Code für Ellipsen ist in `_render_sketch()` drin (Zeilen ~7013-7024)
- Zeichnet Ellipse als geschlossene Linie mit 64 Segmenten

## Debugging

### Teste Drag & Drop:
```python
conda activate cad_env
python -c "
from sketcher import Sketch
s = Sketch()
e = s.add_ellipse(0, 0, 10, 5, 0)

# Prüfe Handle-Attribute
print('Center:', hasattr(e, '_center_point'))
print('Major axis:', hasattr(e, '_major_axis'))
print('Major pos:', hasattr(e, '_major_pos'))

# Simuliere Drag
e.center.x = 5
e.center.y = 3

# Aktualisiere Achsen (wie im Editor)
from gui.sketch_editor import SketchEditor
ed = SketchEditor()
ed._update_ellipse_axes_from_ellipse(e)

print('After drag:')
print(f'Center: ({e.center.x}, {e.center.y})')
print(f'Major pos: ({e._major_pos.x}, {e._major_pos.y})')
"
```

### Teste 3D Visualisierung:
```python
python -c "
from sketcher import Sketch
from sketcher.geometry import Ellipse2D, Point2D
import math

s = Sketch()
e = s.add_ellipse(0, 0, 10, 5, 0)

# Prüfe ob Ellipse in Liste
print(f'Sketch has {len(s.ellipses)} ellipses')

# Prüfe point_at_angle
pt = e.point_at_angle(0)
print(f'point_at_angle(0): ({pt.x}, {pt.y})')

# Prüfe 3D Punkte
pts = []
for j in range(65):
    angle = math.radians(j * 360 / 64)
    pt = e.point_at_angle(angle)
    pts.append((pt.x, pt.y))
    
print(f'Generated {len(pts)} 3D points')
print(f'First: {pts[0]}, Last: {pts[-1]}')
"
```

## Bekannte Probleme & Lösungen

| Problem | Lösung |
|---------|--------|
| Handles selektierbar aber kein Drag | `_update_ellipse_axes_from_ellipse()` muss aufgerufen werden |
| 3D: Nur Achsen sichtbar | Prüfe ob `s.ellipses` gefüllt ist |
| 3D: Ellipse fehlt komplett | `point_at_angle()` muss funktionieren |
| Constraint-Änderung keine Wirkung | `_update_ellipse_geometry()` prüfen |

## Files geändert:
- `sketcher/sketch.py` - `_update_ellipse_geometry()` 
- `gui/sketch_editor.py` - `_update_ellipse_axes_from_ellipse()`, `_apply_direct_edit_drag()`
- `gui/viewport_pyvista.py` - Ellipse Rendering in `_render_sketch()`
- `modeling/__init__.py` - `_extrude_sketch_ellipses()`

## Testen:
```bash
conda activate cad_env
python -m py_compile sketcher/sketch.py gui/sketch_editor.py gui/viewport_pyvista.py
python main.py
```
