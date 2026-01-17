# MashCAD - Professional Open-Source CAD Application

**MashCAD** ist eine protorypische CAD-Anwendung in Python.
Kombiniert parametrisches 3D-Modeling mit einem intuitiven UI, gebaut auf Build123d (OpenCASCADE).

## Highlights

- ✅ **Transform-System**: Gizmo-basiert mit Live-Preview
- ✅ **Parametrische Feature-History**: Alle Operationen editierbar
- ✅ **Undo/Redo**: Vollständig für alle Transform/Edit-Operationen
- ✅ **Shortcuts**: G (Move), R (Rotate), S (Scale) + Achsen-Locks (X/Y/Z)
- ✅ **Pattern/Array**: Linear & Circular Patterns
- ✅ **Mesh-zu-BREP**: Intelligente Converter für STL/PLY → CAD-Solids

## Features

### Transform-System 
- **Move/Rotate/Scale** mit interaktivem 3D-Gizmo
- **Achsen-Locking** (X/Y/Z Keys während Drag)
- **Ebenen-Constraints** (Shift+X/Y/Z für YZ/XZ/XY-Ebenen)
- **Snap to Grid** (Ctrl-Modifier, konfigurierbar 0.1-10mm)
- **Modale Numerische Eingabe** (G→5→Enter = Move 5mm, wie Blender)
- **Mirror**: Planare Spiegelung (XY/XZ/YZ)
- **Copy+Transform**: Shift+Drag für Kopien
- **Pattern/Array**: Linear (N Kopien mit Abstand) & Circular (360° Verteilung)

### Parametrisches Modeling
- **Feature-History**: Alle Operationen im Browser sichtbar & editierbar
- **Undo/Redo** (Ctrl+Z/Ctrl+Y) für Transforms, Extrudes, Features
- **Doppelklick-Editing**: Feature im Browser doppelklicken → Parameter ändern
- **Non-Destructive Workflow**: Transforms als Features gespeichert (nicht "gebacken")

### 2D Sketch Editor
- **Drawing Tools**: Line, Rectangle, Circle (3 modes), Arc, Polygon, Slot, Spline, Point
- **Transform Tools**: Move, Copy, Rotate, Mirror, Scale, Linear/Circular Pattern
- **Modify Tools**: Trim, Extend, Offset, Fillet, Chamfer
- **Constraints**: Horizontal, Vertical, Parallel, Perpendicular, Equal, Concentric, Tangent
- **Generators**: Involute Gear, Star, Hex Nut (M2-M14)
- **Precision Input**: Tab-key für numerische Eingabe (Fusion360-style)
- **Smart Snapping**: Endpoint, Midpoint, Center, Intersection, Grid

### 3D Viewport (PyVista - Hardware Accelerated)
- **Extrude mit Live Preview**
- **Boolean Operations** (New Body, Join, Cut, Intersect)
- **Face Detection** für overlapping Shapes
- **ViewCube Navigation**
- **Edge/Face Picking** für Fillet/Chamfer

### Mesh-zu-BREP-Konvertierung (3 Modi)
- **Auto (Hybrid - EMPFOHLEN)**: Automatische Methoden-Wahl
  - Versucht RANSAC → Smart → Sewing (Fallbacks)
  - Best for: Alle Geometrie-Typen
  - Resultat: 10-200 Faces (vollständig editierbar)

- **Primitives (RANSAC)**: Feature-Erkennung
  - Erkennt: Planes, Cylinders, Spheres
  - Best for: Funktionale mechanische Teile
  - Resultat: 10-100 analytische Faces

- **Smart (Planar)**: Planare Regionenerkennung
  - Erkennt: Ebene Flächen
  - Best for: Prismatische/eckige Teile
  - Resultat: 6-200 Faces

### Export
- **STL** (3D Druck)
- **STEP** (CAD-Austausch)
- **DXF** (2D Sketches)

## Installation

### From Source
```bash
git clone https://github.com/Talwar85/MashCad.git
cd MashCad
pip install -r requirements.txt
python main.py
```

### Mit ML-Features (ParSeNet, optional)
```bash
pip install -r requirements-ml.txt  # PyTorch + Dependencies (~1.5 GB)
```


## Tech-Stack
- **GUI**: PySide6 (Qt6)
- **3D-Rendering**: PyVista (VTK 9.2+)
- **CAD-Kernel**: Build123d (OpenCASCADE-basiert)
- **2D-Geometrie**: Shapely
- **Mesh-Processing**: PyMeshLab, MeshLib, Gmsh (optional)
- **ML (optional)**: PyTorch, ParSeNet

## Keyboard Shortcuts

### Transform-System (3D)
| Shortcut | Funktion | Beschreibung |
|----------|----------|--------------|
| **G** | Move Mode | Startet Move-Transform (Gizmo oder numerisch) |
| **R** | Rotate Mode | Startet Rotate-Transform |
| **S** | Scale Mode | Startet Scale-Transform |
| **M** | Mirror | Öffnet Mirror-Dialog (Plane-Auswahl) |
| **X/Y/Z** | Axis Lock | Während Transform: Lock auf Achse (rote/grüne/blaue Linie) |
| **Shift+X/Y/Z** | Plane Lock | Während Transform: Lock auf Ebene (z.B. Shift+X = YZ-Ebene) |
| **Ctrl+Drag** | Snap to Grid | Snap auf 1mm Grid (konfigurierbar) |
| **Shift+Drag** | Copy+Transform | Erstellt Kopie während Transform |
| **Tab** | Focus Input | Wechselt zu numerischer Eingabe-UI |
| **Enter** | Apply | Wendet numerische Eingabe an |
| **ESC** | Cancel | Bricht aktuellen Transform ab |
| **Ctrl+Z / Ctrl+Y** | Undo / Redo | Rückgängig / Wiederholen |

### Modale Numerische Eingabe (Blender-Style)
| Workflow | Resultat |
|----------|----------|
| **G → 5 → Enter** | Move 5 Einheiten auf gesperrter Achse |
| **R → 45 → Enter** | Rotate 45° |
| **S → 1.5 → Enter** | Scale Factor 1.5 |
| **G → X → 10 → Enter** | Move 10mm auf X-Achse |

### Sketch Editor (2D)
| Key | Action |
|-----|--------|
| **L** | Line \| **R** | Rectangle \| **C** | Circle \| **P** | Polygon |
| **M** | Move \| **X** | Construction mode \| **G** | Grid snap |
| **Tab** | Precision input \| **Enter** | Confirm \| **Escape** | Cancel |
| **Delete** | Delete selected \| **Ctrl+Z/Y** | Undo/Redo |

### Viewport Navigation
| Key | Action |
|-----|--------|
| **F** | Fit view \| **E** | Extrude (3D) |
| **1-7** | Standard-Ansichten (Front/Back/Right/Left/Top/Bottom/Iso) |
| **Middle Mouse** | Rotate View \| **Shift+Middle Mouse** | Pan View |
| **Mouse Wheel** | Zoom |



## Workflow-Beispiele

### Präzise Move auf X-Achse
```
1. Wähle Body im Browser
2. Drücke G (Move-Modus startet)
3. Drücke X (Locked auf X-Achse, roter Indikator erscheint)
4. Tippe 10 (numerische Eingabe)
5. Drücke Enter (Body bewegt sich 10mm auf X)
```

### Circular Pattern (8 Kopien um 360°)
```
1. Wähle Body
2. Menu: Transform → Create Pattern
3. Wähle "Circular"
4. Count: 8, Axis: Z, Full Circle: Yes
5. Create Pattern (8 Kopien gleichmäßig verteilt)
```

### Mesh zu CAD konvertieren
```
1. Menu: File → Import Mesh (STL/OBJ/PLY)
2. Mesh erscheint grau im Viewport
3. Menu: 3D → Konvertierung zu BREP
4. Wähle: "Auto (Hybrid)" (empfohlen - automatische Wahl)
5. Body wird zu editierbarem Solid (10-200 Faces statt 10k)
6. Teste: Fillet/Extrude/Boolean funktionieren ✅
```

## Projekt-Struktur
```
MashCad/
├── main.py                           # Entry Point
├── gui/
│   ├── main_window.py                # Hauptfenster, zentrale Logik
│   ├── viewport_pyvista.py           # 3D-Viewport (PyVista/VTK)
│   ├── browser.py                    # Feature-History Browser
│   ├── sketch_editor.py              # 2D Sketch-Editor
│   ├── commands/
│   │   └── transform_command.py      # Undo/Redo Commands
│   ├── dialogs/
│   │   ├── transform_edit_dialog.py  # Feature-Edit UI
│   │   └── pattern_dialog.py         # Pattern/Array Dialog
│   └── viewport/
│       ├── transform_gizmo_v3.py     # 3D Transform-Gizmo
│       └── transform_mixin_v3.py     # Viewport Integration
├── modeling/
│   ├── __init__.py                   # Body, Document, Feature-Klassen
│   ├── cad_tessellator.py            # Build123d → PyVista Rendering
│   ├── mesh_converter.py             # V1: Sewing
│   ├── mesh_converter_v6.py          # Smart (planare Regionen)
│   ├── mesh_converter_primitives.py  # Primitives (RANSAC)
│   └── mesh_converter_hybrid.py      # Auto/Hybrid (automatische Wahl)
├── sketcher/                         # 2D Geometrie & Constraints
└── i18n/                             # Internationalization (DE/EN)
```

## Roadmap

### Abgeschlossen
- [x] Transform-System (Fusion 360-Level)
- [x] Undo/Redo (QUndoStack)
- [x] Pattern/Array
- [x] 2D Sketch Editor mit Constraints
- [x] 3D Extrude mit Boolean Operations
- [x] Mesh-Converter: Auto/Hybrid, Primitives (RANSAC), Smart (Planar)

### Kommende Features
- [ ] Loft & Sweep Operations
- [ ] Assembly-Modus (Multi-Body-Constraints)
- [ ] Parametric Dimensions (Smart Constraints)
- [ ] Sketcher: Mehr Constraint-Typen
- [ ] Native .masc Project-File-Format (Persistence)

### Known Issues
- [ ] Gizmo-Pfeile werden teilweise von Bodies verdeckt (Z-Buffer)
- [ ] Body-Klick im Viewport für Transform (aktuell nur Browser)

### ⚠️ Boolean Operations (Join/Cut/Intersect)
- Boolean Operations können bei komplexen Geometrien fehlschlagen

## License
MIT

## Credits
- **CAD-Kernel**: [Build123d](https://github.com/gumyr/build123d) (OpenCASCADE)
- **3D-Rendering**: [PyVista](https://github.com/pyvista/pyvista) (VTK)
- **Mesh-Processing**: [PyMeshLab](https://github.com/cnr-isti-vclab/PyMeshLab), [MeshLib](https://github.com/MeshInspector/MeshLib)
- **ML (geplant)**: [ParSeNet](https://github.com/Hippogriff/parsenet-codebase)

---

**Version**: 2.7+ (Transform-System V3 abgeschlossen)
**Last Updated**: 2026-01-16
