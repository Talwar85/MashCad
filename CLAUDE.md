# MashCad - Projektdokumentation für Claude Code

## Projektübersicht

**MashCad** (ehemals LiteCad) ist eine professionelle CAD-Anwendung in Python, die Fusion360-Level-Funktionalität anstrebt. Das Projekt kombiniert parametrisches 3D-Modeling mit einem intuitiven UI.

### Tech-Stack
- **GUI**: PySide6 (Qt6)
- **3D-Rendering**: PyVista (VTK-basiert)
- **CAD-Kernel**: Build123d (OpenCASCADE-basiert)
- **2D-Geometrie**: Shapely
- **Logging**: Loguru

## Architektur

```
LiteCad/
├── main.py                 # Entry Point
├── gui/
│   ├── main_window.py      # Hauptfenster, zentrale Logik
│   ├── viewport_pyvista.py # 3D-Viewport mit PyVista
│   ├── browser.py          # Projektbaum (Bodies, Sketches, Planes)
│   ├── sketch_editor.py    # 2D-Sketching-Editor
│   ├── tool_panel.py       # Werkzeug-Panel (Sketch-Tools)
│   ├── tool_panel_3d.py    # 3D-Werkzeuge (Extrude, etc.)
│   ├── input_panels.py     # Eingabe-Panels (Extrude, Fillet)
│   ├── geometry_detector.py # Face/Edge-Picking
│   ├── viewport/
│   │   ├── transform_gizmo_v3.py  # Transform-Gizmo (Move/Rotate/Scale)
│   │   ├── transform_mixin_v3.py  # Viewport-Integration
│   │   ├── picking_mixin.py       # Picking-Logik
│   │   ├── body_mixin.py          # Body-Rendering
│   │   └── extrude_mixin.py       # Extrude-Preview
│   └── widgets/
│       ├── transform_panel.py     # Transform-Eingabe-UI
│       └── notification.py        # Benachrichtigungen
├── modeling/
│   ├── __init__.py         # Body, Document, Feature-Klassen
│   ├── cad_tessellator.py  # Build123d → PyVista Konvertierung
│   └── mesh_converter*.py  # Mesh → BREP Konvertierung
├── sketcher/
│   ├── __init__.py         # Sketch-Klasse
│   ├── geometry.py         # 2D-Primitive (Line, Arc, Circle, etc.)
│   ├── constraints.py      # Geometrische Constraints
│   └── solver.py           # Constraint-Solver
└── i18n/                   # Internationalisierung (DE/EN)
```

## Kernkonzepte

### 1. Document-Body-Feature Hierarchie
```python
Document
├── bodies: List[Body]      # 3D-Körper
├── sketches: List[Sketch]  # 2D-Skizzen
└── active_body / active_sketch

Body
├── _build123d_solid        # Build123d Solid (CAD-Geometrie)
├── vtk_mesh               # PyVista PolyData (Visualisierung)
├── vtk_edges              # PyVista PolyData (Kanten)
└── features: List[Feature] # Feature-History
```

### 2. Transform-System (V3 - aktuell)
- **Gizmo-basiert**: Pfeile (Move), Ringe (Rotate), Würfel (Scale)
- **Live-Preview**: VTK UserTransform während Drag
- **Apply**: Build123d .move()/.rotate()/.scale() bei Release
- **Cache-Invalidierung**: Globaler Counter für ocp_tessellate Cache

```python
# Wichtig: Nach Transform IMMER Cache leeren!
CADTessellator.clear_cache()
body._build123d_solid = body._build123d_solid.move(Location((dx, dy, dz)))
```

### 3. Tessellator-Cache
Der `CADTessellator` cached Mesh-Daten. **Kritisch**: `ocp_tessellate` hat internen Cache basierend auf Cache-Key. Bei Transforms muss der Counter erhöht werden:

```python
# cad_tessellator.py
_CACHE_INVALIDATION_COUNTER = 0  # Global

def clear_cache():
    global _CACHE_INVALIDATION_COUNTER
    _CACHE_INVALIDATION_COUNTER += 1  # Invalidiert auch ocp_tessellate!
    ...

# Cache-Key enthält Counter
cache_key = f"{shape_id}_{quality}_v{VERSION}_c{_CACHE_INVALIDATION_COUNTER}"
```

### 4. Signal-Flow (Qt)
```
Browser.feature_selected → MainWindow._on_feature_selected
                        → MainWindow._show_transform_ui
                        → Viewport.show_transform_gizmo

Viewport.body_transform_requested → MainWindow._on_body_transform_requested
                                 → Build123d Transform
                                 → CADTessellator.clear_cache()
                                 → Body._update_mesh_from_solid()
```

## Bekannte Probleme / TODOs

### Transform-System
- [ ] Body-Klick im Viewport funktioniert nicht (nur Browser)
- [ ] Gizmo-Pfeile werden teilweise vom Body verdeckt (Z-Buffer)
- [ ] Multi-Select für Transforms
- [ ] Undo/Redo für Transforms

### UI/UX
- [ ] Transform-Panel Layout optimieren
- [ ] Keyboard-Shortcuts dokumentieren
- [ ] Tooltips vervollständigen

### Sketcher
- [ ] Constraint-Solver Stabilität
- [ ] Mehr Constraint-Typen

## Wichtige Code-Patterns

### 1. Body zu Viewport hinzufügen
```python
# In viewport_pyvista.py
def add_body(self, body_id, mesh, edges, ...):
    # WICHTIG: Alte Actors ZUERST entfernen!
    self._remove_body_actors(body_id)
    
    # Neue Actors hinzufügen
    self.plotter.add_mesh(mesh, name=f"body_{body_id}_m", ...)
    self.plotter.add_mesh(edges, name=f"body_{body_id}_e", ...)
```

### 2. Transform anwenden
```python
# In main_window.py
def _on_body_transform_requested(self, body_id, mode, data):
    CADTessellator.clear_cache()  # IMMER ZUERST!
    
    if mode == "move":
        body._build123d_solid = body._build123d_solid.move(Location((dx, dy, dz)))
    elif mode == "rotate":
        body._build123d_solid = body._build123d_solid.rotate(axis, angle)
    
    self._update_body_from_build123d(body, body._build123d_solid)
```

### 3. Mixin-Pattern für Viewport
```python
class PyVistaViewport(QWidget, ExtrudeMixin, PickingMixin, BodyRenderingMixin, TransformMixinV3):
    # Mixins fügen Funktionalität hinzu ohne Vererbungshierarchie
```

## Entwicklungshinweise

### Starten
```bash
cd LiteCad
python main.py
```

### Abhängigkeiten
```bash
pip install pyside6 pyvista build123d loguru shapely numpy
```

### Debug-Logging
```python
from loguru import logger
logger.debug("...")   # Detailliert
logger.info("...")    # Normal
logger.success("...")  # Erfolg (grün)
logger.warning("...")  # Warnung
logger.error("...")   # Fehler
```

## Keyboard-Shortcuts

| Taste | Funktion |
|-------|----------|
| G | Move-Modus |
| R | Rotate-Modus |
| S | Scale-Modus |
| M | Mirror-Dialog |
| Shift+Drag | Copy+Transform |
| ESC | Abbrechen / Deselektieren |
| Tab | Numerische Eingabe fokussieren |
| Enter | Transform anwenden |

## Letzte Änderungen (V12)

1. Transform-System V3 aktiviert (Move/Rotate/Scale/Copy/Mirror)
2. Zentrales Hinweis-Widget für Benutzerführung
3. Live-Werte-Anzeige im Transform-Panel
4. Tessellator-Cache-Fix für Transforms (Counter-basiert)
