# MashCad – Projektdokumentation

> **Zweck:** Zentrale Referenz für alle Claude-Arbeitsessions. Diese Doku ist **lebend** – wird bei jeder größeren Änderung aktualisiert. Stand: Januar 2026, V12+

---

## 🎯 Claude AI – Verhaltensrichtlinien & Standards

### Philosophie: Senior Product Designer + Senior Engineer

Du agierst nicht nur als Coder, sondern als **Senior Product Designer & UX Architect**. Oberste Direktive: **Exzellenz in der Benutzerführung (UX)**.

#### 1. Das "Fusion-Plus"-Prinzip

- **Benchmark:** Mindeststandard = Fusion 360 Feature-Implementierung
- **Ziel:** Wir machen es **besser** → flüssiger UX, weniger Klicks
- **Abbruchkriterium:** Eine Implementierung ist NICHT "fertig", wenn sie nur funktioniert. Sie ist fertig, wenn sie sich **gut anfühlt**

#### 2. Konsistenz & Integration (Anti-Insel-Policy)

- **Bevor** du ein neues Feature baust (z.B. Chamfer), analysiere **zwingend** die UX der Best-Practice-Features (aktuell: **Transform V3**)
- **Workflow-Konsistenz:** Wenn Feature A interaktive Selektion im Viewport erlaubt → Feature B muss das auch können
- **UI-Integration:** Neue Features passen nahtlos in bestehende Panel-Strukturen
- **Fehlerbehandlung:** Keine Insel-Lösungen – konsistente Error-Signaling über alle Features

#### 3. Rigorosität & Observability (Anti-Schwammig-Policy)

- **Fehlerkultur:** Fehler müssen **glasklar** unterscheidbar sein
- **Result-Pattern:** Nutze strukturierte Rückgabetypen:
  - `CRITICAL`: Code gecrasht / Recovery notwendig
  - `FALLBACK`: Alternative Berechnung genutzt (Warnung)
  - `EMPTY_SUCCESS`: Technisch okay, aber logisch kein Ergebnis (z.B. keine Kante)
  - `SUCCESS`: Alles okay

- **Test-Mentalität:** Kein Code ohne Verifikationsplan. "Sollte gehen" ist nicht akzeptabel

---

## 📋 Projektübersicht

**MashCad** (ehemals LiteCad) ist eine professionelle CAD-Anwendung in Python, die Fusion360-Level-Funktionalität anstrebt.

### Tech-Stack

| Komponente | Stack |
|-----------|-------|
| **GUI** | PySide6 (Qt6) |
| **3D-Rendering** | PyVista (VTK-basiert) |
| **CAD-Kernel** | Build123d (OpenCASCADE-basiert) |
| **2D-Geometrie** | Shapely |
| **Logging** | Loguru |
| **Constraints (Sketcher)** | Custom Solver (Lagrange Multiplier) |

---

## 🏗️ Architektur

### Directory-Struktur

```
LiteCad/
├── main.py                          # Entry Point
│
├── gui/
│   ├── main_window.py               # Zentrale App-Logik, Signal-Routing
│   ├── viewport_pyvista.py          # 3D-Viewport Backbone
│   ├── browser.py                   # Projektbaum (Bodies, Sketches, Planes, Features)
│   ├── sketch_editor.py             # 2D-Sketching-Editor
│   │
│   ├── tool_panel.py                # Sketch-Tools (Toolbar)
│   ├── tool_panel_3d.py             # 3D-Tools (Extrude, Fillet, Chamfer, etc.)
│   ├── input_panels.py              # Modal/Dock-Panels (Extrude-Parameter, Fillet-Radius, etc.)
│   ├── geometry_detector.py         # Face/Edge-Picking & Raytracing
│   │
│   ├── viewport/
│   │   ├── transform_gizmo_v3.py    # 🟢 Transform-Gizmo (Move/Rotate/Scale) – REFERENZ-UX
│   │   ├── transform_mixin_v3.py    # Viewport-Integration für Transform
│   │   ├── picking_mixin.py         # Picking-Logik (Raycasting)
│   │   ├── body_mixin.py            # Body-Rendering & Mesh-Updates
│   │   ├── extrude_mixin.py         # Extrude-Preview-System
│   │   └── chamfer_mixin.py         # Chamfer-Preview (neuer Standard)
│   │
│   └── widgets/
│       ├── transform_panel.py       # Transform-Eingabe-Panel
│       ├── notification.py          # Toast/Benachrichtigungen
│       └── property_panel.py        # Feature-Eigenschaften & History
│
├── modeling/
│   ├── __init__.py                  # Document, Body, Feature Basis-Klassen
│   ├── cad_tessellator.py           # Build123d → PyVista Konvertierung (mit Cache)
│   ├── mesh_converter.py            # BREP ↔ Mesh Konvertierung
│   └── feature_registry.py          # Feature-Typ-Registry & Factory
│
├── sketcher/
│   ├── __init__.py                  # Sketch-Klasse, Sketch-State
│   ├── geometry.py                  # 2D-Primitive (Line, Arc, Circle, Point, etc.)
│   ├── constraints.py               # Geometrische Constraints (Coincident, Tangent, etc.)
│   ├── solver.py                    # Constraint-Solver (Lagrange)
│   └── evaluator.py                 # Sketch-Evaluierung & Validation
│
├── i18n/
│   ├── de.json                      # Deutsche Strings
│   ├── en.json                      # Englische Strings
│   └── __init__.py                  # i18n-System
│
└── config/
    └── defaults.py                  # Globale Settings (Grid, Colors, Shortcuts)
```

---

## 🧠 Kernkonzepte

### 1. Document-Body-Feature-Hierarchie

```python
Document
├── bodies: List[Body]              # 3D-Körper
├── sketches: List[Sketch]          # 2D-Skizzen (können an Bodies gebunden sein)
├── planes: List[Plane]             # Referenz-Planes
├── active_body: Optional[Body]     # Aktiver Body für neue Features
└── active_sketch: Optional[Sketch] # Aktive Skizze für Editing

Body
├── _build123d_solid: Solid         # Build123d Solid-Objekt (CAD-Geometrie)
├── vtk_mesh: PolyData              # PyVista PolyData (Visualization)
├── vtk_edges: PolyData             # Kanten-Rendering
├── vtk_normals: ndarray            # Für Normale Picking
├── features: List[Feature]         # Feature-Geschichte (Extrude, Fillet, etc.)
└── metadata: Dict                  # Name, Color, Visibility, etc.

Feature (abstrakt)
├── id: str                         # Eindeutige ID
├── name: str                       # "Extrude1", "Fillet2", etc.
├── type: str                       # "extrude", "fillet", "chamfer"
├── params: Dict                    # Feature-Parameter (Höhe, Radius, etc.)
├── depends_on: List[str]           # Feature-Dependencies (für Recompute)
└── suppressed: bool                # Kann deaktiviert werden
```

### 2. Transform-System V3 – UX Referenzstandard

**Dies ist der Gold-Standard für Interaktion.** Alle neuen Features sollten diesen UX-Standard als Vorlage nutzen.

#### Komponenten

| Komponente | Verantwortung |
|-----------|---------------|
| `transform_gizmo_v3.py` | Rendering der 3D-Gizmo (Pfeile, Ringe, Würfel) |
| `transform_mixin_v3.py` | Event-Handling & Viewport-Integration |
| `transform_panel.py` | Numerische Eingabe & Live-Werte |

#### Workflow

```
1. User klickt Body im Viewport
   ↓
2. Viewport.body_selected Signal emittiert
   ↓
3. MainWindow._show_transform_gizmo() aktiviert
   ↓
4. Gizmo wird gerendert (Pfeile/Ringe/Würfel)
   ↓
5. User dragged Pfeil (z.B. X-Achse Move)
   ↓
6. Live-Preview: VTK UserTransform anwenden (KEIN Build123d!)
   ↓
7. Transform-Panel zeigt Live-Werte
   ↓
8. User release Maus
   ↓
9. Apply Transform:
   - CADTessellator.clear_cache()  🔴 WICHTIG!
   - body._build123d_solid = body._build123d_solid.move(Location(...))
   - Body._update_mesh_from_solid()
```

#### Cache-Invalidierung (KRITISCH)

```python
# cad_tessellator.py
_CACHE_INVALIDATION_COUNTER = 0

def clear_cache():
    """Invalidiert ALLE Caches (lokal + ocp_tessellate)"""
    global _CACHE_INVALIDATION_COUNTER
    _CACHE_INVALIDATION_COUNTER += 1  # Notwendig für ocp_tessellate!
    CAD_TESSELLATOR._cache.clear()
```

**Wichtig:** Nach **jedem** Transform, Extrude, Fillet etc. muss `clear_cache()` aufgerufen werden!

### 3. CAD Tessellator-Cache

Build123d/OpenCASCADE ist rechenintensiv. Der Tessellator cached Mesh-Daten aggressiv.

```python
class CADTessellator:
    _cache: Dict[str, Tuple[PolyData, PolyData]] = {}
    
    @staticmethod
    def tessellate(solid, quality=0.5):
        # Cache-Key basiert auf Shape + Quality + globaler Version-Counter
        cache_key = f"{id(solid)}_{quality}_v{VERSION}_c{_CACHE_INVALIDATION_COUNTER}"
        
        if cache_key in _cache:
            return _cache[cache_key]  # Hit
        
        # Miss: Konvertiere mit ocp_tessellate
        mesh_data = ocp_tessellate(solid, quality)
        _cache[cache_key] = mesh_data
        return mesh_data
```

**Merksätze:**
- Jeder Build123d Transform → `clear_cache()`
- Cache-Key enthält `_CACHE_INVALIDATION_COUNTER`
- Ohne Counter = alte Meshes werden wiederverwendet = visuelle Bugs

### 4. Signal-Flow (Qt Signals)

```
┌─────────────────────────────────────────────────────────────┐
│                    Qt Signal-Topologie                       │
└─────────────────────────────────────────────────────────────┘

Browser.feature_selected(body_id, feature_id)
    ↓
MainWindow._on_feature_selected()
    ├─ Highlight Feature in Viewport
    └─ MainWindow._show_feature_properties()

Viewport.body_clicked(body_id)
    ↓
MainWindow._on_body_clicked()
    ├─ CADTessellator.clear_cache()
    └─ Viewport.show_transform_gizmo(body_id)

Viewport.body_transform_requested(body_id, mode, data)
    ├─ (mode = "move" | "rotate" | "scale" | "mirror")
    ↓
MainWindow._on_body_transform_requested()
    ├─ CADTessellator.clear_cache()
    ├─ body._build123d_solid = body._build123d_solid.<transform>()
    ├─ Body._update_mesh_from_solid()
    └─ Viewport.refresh()

Tool_3D.extrude_requested(face_ids, height, mode)
    ↓
MainWindow._on_extrude_requested()
    ├─ CADTessellator.clear_cache()
    ├─ new_solid = current_body.extrude(faces, height)
    ├─ Body._update_mesh_from_solid()
    └─ Viewport.refresh()
```

---

## 🔴 Bekannte Probleme & TODOs

### Priorität 1 (Critical UX)

- [ ] **Body-Klick im Viewport funktioniert nicht** → Nur Browser-Klick funktioniert
  - Impact: User kann Body nicht direkt auswählen zum Transformieren
  - Fix: `geometry_detector.py` – Raycasting verbessern
  
- [ ] **Gizmo-Pfeile teilweise vom Body verdeckt** → Z-Buffer-Konflikte
  - Impact: Schwierig, Gizmo zu greifen
  - Fix: Gizmo mit `depth_peeling` rendern oder separaten Layer nutzen

- [ ] **Undo/Redo für Transforms**
  - Impact: User muss manuell rückgängig machen
  - Architecture: `main_window.py` – Command-Pattern implementieren

### Priorität 2 (Feature-Vollständigkeit)

- [ ] Multi-Select für Transforms (mehrere Bodies gleichzeitig)
- [ ] Mirror-Feature (aktuell nur Dialog, nicht implementiert)
- [ ] Fillet-Kanten-Picking im Viewport (aktuell nur über Browser)
- [ ] Chamfer-Feature (UX-Standard wie Transform V3)

### Priorität 3 (Polish)

- [ ] Transform-Panel Layout optimieren (zu viel Whitespace)
- [ ] Keyboard-Shortcuts vollständig dokumentieren
- [ ] Tooltips auf allen UI-Elementen
- [ ] Constraint-Solver Stabilität (seltene Edge-Cases)

---

## 💻 Wichtige Code-Patterns

### Pattern 1: Body zu Viewport hinzufügen

```python
# In viewport_pyvista.py, BodyRenderingMixin

def add_body(self, body_id: str, body: Body):
    """Fügt Body zur Viewport hinzu oder updated existierenden."""
    
    # Schritt 1: Alte Actors ZUERST entfernen!
    self._remove_body_actors(body_id)
    
    # Schritt 2: Neue Meshes generieren
    mesh_data, edges_data = CADTessellator.tessellate(body._build123d_solid)
    
    # Schritt 3: Actors hinzufügen
    body_mesh_actor = self.plotter.add_mesh(
        mesh_data,
        name=f"body_{body_id}_mesh",
        color=body.metadata.get("color", [0.7, 0.7, 0.7]),
        opacity=0.9
    )
    
    body_edges_actor = self.plotter.add_mesh(
        edges_data,
        name=f"body_{body_id}_edges",
        color=[0, 0, 0],
        line_width=1.5
    )
    
    # Schritt 4: Metadata speichern
    self._body_actors[body_id] = {
        "mesh_actor": body_mesh_actor,
        "edges_actor": body_edges_actor,
        "body": body
    }
    
    # Schritt 5: Viewport Refresh
    self.plotter.reset_camera()
```

### Pattern 2: Transform anwenden

```python
# In main_window.py

def _on_body_transform_requested(self, body_id: str, mode: str, data: Dict):
    """
    Args:
        body_id: ID des zu transformierenden Bodies
        mode: "move", "rotate", "scale", "copy", "mirror"
        data: Transformations-Parameter
            - move: {"dx": float, "dy": float, "dz": float}
            - rotate: {"axis": (x,y,z), "angle": float}
            - scale: {"factor": float}
    """
    
    # Schritt 1: Alte Cache invalidieren
    CADTessellator.clear_cache()
    
    # Schritt 2: Body abrufen
    body = self.document.get_body(body_id)
    if not body:
        logger.error(f"Body {body_id} nicht gefunden")
        return
    
    # Schritt 3: Transform auf Build123d Solid anwenden
    try:
        if mode == "move":
            location = Location(translation=(data["dx"], data["dy"], data["dz"]))
            body._build123d_solid = body._build123d_solid.move(location)
        
        elif mode == "rotate":
            axis = Axis(data["axis"])
            angle = data["angle"]
            body._build123d_solid = body._build123d_solid.rotate(axis, angle)
        
        elif mode == "scale":
            # Skalierung ist komplexer – Center beachten!
            factor = data["factor"]
            body._build123d_solid = body._build123d_solid.scale(factor)
        
        logger.success(f"Transform {mode} angewendet: {body.name}")
    
    except Exception as e:
        logger.error(f"Transform fehlgeschlagen: {e}")
        self.show_notification("Transform fehlgeschlagen", "error")
        return
    
    # Schritt 4: Mesh updaten
    body._update_mesh_from_solid()
    
    # Schritt 5: Viewport refresh
    self.viewport.add_body(body_id, body)
    self.viewport.plotter.render()
```

### Pattern 3: Neues Feature mit UX-Konsistenz (Chamfer-Beispiel)

```python
# In tool_panel_3d.py

def request_chamfer(self):
    """Startet Chamfer-Feature mit Transform-V3-UX-Standard"""
    
    # Schritt 1: Selektion validieren
    selected_edges = self.viewport.geometry_detector.get_selected_edges()
    
    if not selected_edges:
        self.show_notification("Bitte Kanten selektieren", "warning")
        return
    
    # Schritt 2: Feature erstellen
    chamfer_feature = Feature(
        name="Chamfer1",
        type="chamfer",
        depends_on=self.document.active_body.features[-1].id,
        params={
            "edge_ids": selected_edges,
            "size": 2.0,  # Standard 2mm
            "mode": "size"  # oder "angle"
        }
    )
    
    # Schritt 3: Mit Transform-V3 Pattern arbeiten!
    # → Interaktives Gizmo im Viewport für Radius-Adjustment
    # → Live-Preview während Drag
    # → Numerische Eingabe im Panel
    # → Consistency-Check: Ist UX gleich wie Transform V3?
    
    self.viewport.show_chamfer_gizmo(
        chamfer_feature,
        on_changed=self._on_chamfer_changed,  # Live-Preview Callback
        on_applied=self._on_chamfer_applied   # Final Apply
    )
    
    # Schritt 4: Viewport aktualisieren (Kanten-Highlight)
    self.viewport.highlight_edges(selected_edges)

def _on_chamfer_changed(self, size: float):
    """Live-Preview während Gizmo-Drag"""
    # KEIN Build123d Update hier! Nur Visual Preview
    self.viewport.preview_chamfer_radius(size)

def _on_chamfer_applied(self, size: float):
    """Final Apply nach Release"""
    CADTessellator.clear_cache()  # 🔴 WICHTIG!
    
    # Feature-Compute
    new_solid = self.document.active_body.compute_chamfer(size)
    
    # Build123d Update
    self.document.active_body._build123d_solid = new_solid
    
    # Viewport Update
    self.viewport.add_body(self.document.active_body.id, self.document.active_body)
    logger.success("Chamfer angewendet")
```

### Pattern 4: Mixin-Architektur für Viewport

```python
# In viewport_pyvista.py

class PyVistaViewport(QWidget, ExtrudeMixin, PickingMixin, BodyRenderingMixin, TransformMixinV3, ChamferMixin):
    """
    Viewport kombiniert mehrere Mixins für saubere Separation of Concerns.
    
    Mixin-Aufteilung:
    - ExtrudeMixin: Extrude-Preview-System
    - PickingMixin: Raycasting & Face/Edge-Selection
    - BodyRenderingMixin: Body-Rendering & Mesh-Lifecycle
    - TransformMixinV3: Transform-Gizmo & Interaktion
    - ChamferMixin: Chamfer-Gizmo & Preview
    """
    
    def __init__(self):
        super().__init__()
        self.plotter = PyVistaPlotter()
        self._body_actors = {}
        self._gizmo_system = GizmoManager()  # Zentrale Gizmo-Verwaltung
        
        # Mixin-Initialisierung
        self._init_picking()
        self._init_transform_gizmo()
        self._init_chamfer_gizmo()
        self._init_extrude_preview()
```

---

## 🚀 Entwicklungshinweise

### Starten

```bash
cd LiteCad
conda activate cad_env
python main.py
```

### Abhängigkeiten

```bash
pip install pyside6 pyvista build123d loguru shapely numpy scipy
```

### Debug-Logging

```python
from loguru import logger

logger.debug("...")       # Detailliert (nur in Dev-Mode)
logger.info("...")        # Normal
logger.success("...")     # Erfolg (grün) – NUR bei User-Facing Success
logger.warning("...")     # Warnung – Fallbacks
logger.error("...")       # Fehler – Exceptions mit Kontext
logger.critical("...")    # Kritisch – App-Stop
```

### Keyboard-Shortcuts

| Taste | Funktion |
|-------|----------|
| `G` | Move-Gizmo aktivieren |
| `R` | Rotate-Gizmo aktivieren |
| `S` | Scale-Gizmo aktivieren |
| `M` | Mirror-Dialog öffnen |
| `Shift+Drag` | Copy + Transform |
| `Esc` | Abbrechen / Deselektieren / Gizmo ausblenden |
| `Tab` | Numerische Eingabe fokussieren |
| `Enter` | Transform/Feature anwenden |
| `Delete` | Body/Feature löschen |
| `H` | Body verstecken/zeigen |

---

## 📊 Architektur-Versionshistorie

Dokumentiert größere Architektur-Änderungen für Kontextualität.

### V12 (aktuell – Januar 2026)

**Neue Features:**
- Transform-System V3 aktiviert (Move/Rotate/Scale/Copy/Mirror mit Gizmo)
- Cache-Counter für Tessellator-Invalidierung
- Zentrales Hinweis-Widget für Benutzerführung
- Live-Werte-Anzeige im Transform-Panel

**Breaking Changes:**
- Cache-API geändert (jetzt mit Counter)
- Transform-Mixin-Signale neu strukturiert

**Bekannte Issues:**
- Body-Klick im Viewport funktioniert nicht (nur Browser)
- Gizmo-Z-Buffer-Konflikte

### V11 (Dezember 2025)

- Sketch-Solver verbessert (Lagrange Multiplier)
- Constraint-Types erweitert

### V10 (November 2025)

- Initiale PyVista-Integration
- Body-Rendering-System

---

## 🎓 Lern-Ressourcen

### Build123d Dokumentation

- Offizielle Docs: [build123d GitHub](https://github.com/CadQuery/build123d)
- Wichtig: `Solid` API, `Location` für Transforms, `BuildPart` für Features

### PyVista / VTK

- [PyVista Docs](https://docs.pyvista.org/)
- Kritisch: `Plotter`, `PolyData`, `UserTransform`, Picking mit Raycasting

### Qt/PySide6

- [PySide6 Dokumentation](https://doc.qt.io/qtforpython-6/)
- Patterns: Signal/Slot, Mixin-Architektur, MDI-Widgets

### CAD-Theorie

- **BREP vs Mesh:** BREP = Boundary Representation (exakt), Mesh = Tessellation (visual)
- **Constraints:** Lagrange Multiplier Method für Sketch-Solver
- **Transforms:** OpenCASCADE `Location` API

---

## 📝 Schnelle Referenz für häufige Aufgaben

### Neue Features hinzufügen

1. Feature-Klasse in `modeling/__init__.py` registrieren
2. Feature-Compute-Logik schreiben (mit Build123d)
3. **UX-Konsistenz-Check:** Transform V3 als Referenz nutzen
4. Viewport-Mixin hinzufügen (z.B. `ChamferMixin`)
5. Tool-Button in `tool_panel_3d.py`
6. Internationalisierung (DE + EN) in `i18n/`

### Viewport-Updates nach Änderungen

```python
# IMMER diese Reihenfolge:
1. CADTessellator.clear_cache()
2. body._build123d_solid = <new solid>
3. body._update_mesh_from_solid()
4. self.viewport.add_body(body_id, body)
5. self.viewport.plotter.render()
```

### Performance-Bottlenecks debuggen

```python
# In viewport_pyvista.py
import time

def add_body_debug(self, body_id, body):
    t0 = time.time()
    
    mesh_data, edges_data = CADTessellator.tessellate(body._build123d_solid)
    logger.debug(f"Tessellate: {time.time()-t0:.2f}s")
    
    t0 = time.time()
    self.plotter.add_mesh(mesh_data, ...)
    logger.debug(f"Add Mesh: {time.time()-t0:.2f}s")
```

---

## 🔗 Abhängigkeiten zwischen Komponenten

```
main_window.py
├─ Browser (Feature-Auswahl)
├─ Viewport (Rendering)
│  ├─ TransformMixinV3 (Transform-Gizmo)
│  ├─ PickingMixin (Raycasting)
│  ├─ BodyRenderingMixin (Mesh-Lifecycle)
│  └─ ExtrudeMixin (Extrude-Preview)
├─ ToolPanel3D (3D-Tool-Buttons)
├─ InputPanels (Feature-Parameter)
└─ CADTessellator (Mesh-Generation)

Document
├─ bodies: [Body]
├─ sketches: [Sketch]
└─ planes: [Plane]

Body
├─ _build123d_solid (CAD-Geometrie)
├─ vtk_mesh (Visualization)
└─ features: [Feature]

Sketch
├─ geometry: [Line, Arc, Circle, ...]
└─ constraints: [Constraint]
```

---

## ✅ Pre-Commit Checklist (für neue Features)

- [ ] Alle Tests grün
- [ ] Logging-Level auf `INFO` (nicht `DEBUG`)
- [ ] Keine `print()` Statements (nur `logger`)
- [ ] Internationalisierung (DE + EN)
- [ ] Cache-Invalidierung nach Build123d Updates
- [ ] UX-Konsistenz mit Transform V3 geprüft
- [ ] Keine unerwarteten Fehlerseiten möglich
- [ ] Dokumentation aktualisiert (diese Doku)
- [ ] Keyboard-Shortcuts dokumentiert
- [ ] Viewport-Performance akzeptabel (<100ms bei Standard-Model)

---

**Letzte Aktualisierung:** Januar 2026, V12+  
**Nächste Review:** Nach Major-Feature-Implementierung  
**Verantwortung:** Claude (kontinuierliche Architektur-Überblicke)