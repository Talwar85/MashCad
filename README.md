# MashCAD - Open-Source CAD Application

**MashCAD** ist eine protorypische CAD-Anwendung in Python.
Kombiniert parametrisches 3D-Modeling mit einem intuitiven UI, gebaut auf Build123d (OpenCASCADE).
Fokus der Entwicklung ist aktuell ein guter 2D-Sketcher und erste primitive 3D-Funktionen

Es ist noch keine sinnvolle produktive Bedienbarkeit möglich.

## Highlights

- ✅ **2D-Sketcher**: Gute Bedienbarkeit im 2D Sketcher.
- ✅ **2D-Sketcher - Bearbeiten**: Fokus auf transparenz und leicht zugängliche Funktion. 
- ✅ **Undo/Redo**: Vollständig für alle Transform/Edit-Operationen
- ✅ **Shortcuts**: G (Move), R (Rotate), S (Scale) + Achsen-Locks (X/Y/Z)
- ✅ **Transform-System**: Gizmo-basiert mit Live-Preview


## Features

### Transform-System 
- **Move/Rotate/Scale** mit interaktivem 3D-Gizmo
- **Achsen-Locking** (X/Y/Z Keys während Drag)
- **Ebenen-Constraints** (Shift+X/Y/Z für YZ/XZ/XY-Ebenen)
- **Snap to Grid** (Ctrl-Modifier, konfigurierbar 0.1-10mm)
- **Modale Numerische Eingabe** (G→5→Enter = Move 5mm, wie Blender)
- **Mirror**: Planare Spiegelung (XY/XZ/YZ)
- **Copy+Transform**: Shift+Drag für Kopien


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


### Export
- **STL** (3D Druck)
- **STEP** (CAD-Austausch)
- **DXF** (2D Sketches)

#


## Tech-Stack
- **GUI**: PySide6 (Qt6)
- **3D-Rendering**: PyVista (VTK 9.2+)
- **CAD-Kernel**: Build123d (OpenCASCADE-basiert)
- **2D-Geometrie**: Shapely
- **Mesh-Processing**: PyMeshLab, MeshLib, Gmsh (optional)
- **ML (optional)**: PyTorch, ParSeNet

## Keyboard Shortcuts



### Abgeschlossen
- Proof of Concept. --> 2D Sketches
- Proof of Concept. --> Extrude
- Proof of Concept. --> 3D Transform



### ⚠️ Boolean Operations (Join/Cut/Intersect)
- Boolean Operations können bei komplexen Geometrien fehlschlagen
- Mesh-zu-BREP-Konvertierung schlagen aktuell immer fehl. Prüfe verschiedene ansätze

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
