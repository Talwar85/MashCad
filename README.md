# MashCAD

[![CI](../../actions/workflows/ci.yml/badge.svg?branch=main)](../../actions/workflows/ci.yml)
[![Gates](../../actions/workflows/gates.yml/badge.svg?branch=main)](../../actions/workflows/gates.yml)

**EN:** Open-source parametric CAD application built with Python. Combines a constraint-based 2D sketcher with 3D modeling, powered by Build123d (OpenCASCADE).

**DE:** Open-Source parametrische CAD-Anwendung in Python. Verbindet einen Constraint-basierten 2D-Sketcher mit 3D-Modellierung, basierend auf Build123d (OpenCASCADE).

> **Status:** Prototype / Early Development - Core features work, expect rough edges.
>
> **Status:** Prototyp / Frühe Entwicklung - Kernfunktionen funktionieren, aber noch nicht ausgereift.

## Screenshots

### 3D Viewport
![3D Viewport](img/viewport3d.jpg)

### 2D Sketch Editor / 2D-Sketcher
![2D Sketch Editor](img/sketch2d.JPG)

**Tab for precision input / Tab für Präzisionseingabe:**

![Precision Input](img/sketch2d_tab.JPG)

### 3D Features

| Chamfer | Shell / Aushöhlen | Split Body |
|---------|-------------------|------------|
| ![Chamfer](img/chamfer.jpg) | ![Shell](img/aushoelen.jpg) | ![Split](img/split_body.JPG) |

### Mesh to CAD Conversion / Mesh-zu-CAD Konvertierung

| Import STL/OBJ | Converted to BREP |
|----------------|-------------------|
| ![Mesh Import](img/mesh_import.JPG) | ![Mesh Converted](img/mesh_converted.JPG) |

## Features / Funktionen

### 2D Sketch Editor / 2D-Sketcher
- **Drawing / Zeichnen:** Line, Rectangle, Circle (3 modes), Arc, Polygon, Slot, Spline
- **Editing / Bearbeiten:** Move, Copy, Rotate, Mirror, Scale, Linear/Circular Pattern
- **Modify / Modifizieren:** Trim, Extend, Offset, Fillet, Chamfer
- **Constraints:** Horizontal, Vertical, Parallel, Perpendicular, Equal, Concentric, Tangent
- **Generators:** Involute Gear, Star, Hex Nut
- **Precision Input / Präzisionseingabe:** Tab for numeric entry, smart snapping

### 3D Modeling / 3D-Modellierung
- **Extrude** with live preview / mit Live-Vorschau
- **Boolean Operations:** New Body, Join, Cut, Intersect
- **Push/Pull:** Direct face manipulation / Direkte Flächenmanipulation
- **Features:** Fillet, Chamfer, Draft, Shell, Hole, Thread
- **Transform:** Move, Rotate, Scale with 3D Gizmo (G/R/S shortcuts)

### Export
- STL, STEP, 3MF, DXF

## Download

**EN:** Pre-built executables: [Releases](../../releases)
- Windows (x64)
- Linux (x86_64)
- macOS (Intel x64) - **also works on M1/M2 via Rosetta 2**

**DE:** Fertige Builds: [Releases](../../releases)
- Windows (x64)
- Linux (x86_64)
- macOS (Intel x64) - **funktioniert auch auf M1/M2 via Rosetta 2**

## Development Setup / Entwicklungsumgebung

Requires / Benötigt [Miniforge](https://github.com/conda-forge/miniforge) or Miniconda.

```bash
conda create -n cad_env -c conda-forge python=3.11 \
    pyside6 pyvista pyvistaqt build123d ocp vtk \
    numpy scipy shapely ezdxf loguru trimesh \
    matplotlib pillow lib3mf

conda activate cad_env
pip install ocp-tessellate
python main.py
```

## Shortcuts / Tastenkürzel

| Key / Taste | Action / Aktion |
|-------------|-----------------|
| G | Move / Verschieben |
| R | Rotate / Drehen |
| S | Scale / Skalieren |
| M | Mirror / Spiegeln |
| H | Hide/Show / Ausblenden/Anzeigen |
| Tab | Numeric input (Sketch) / Numerische Eingabe |
| Space | 3D peek (Sketch) / 3D-Vorschau |

## Known Limitations / Bekannte Einschränkungen

- Boolean operations can fail on complex geometry / Boolean-Operationen können bei komplexer Geometrie fehlschlagen
- Some mesh operations are experimental / Einige Mesh-Operationen sind experimentell

### macOS Apple Silicon (M1/M2/M3)

**EN:** Native arm64 builds are not available because the `ocp` package (OpenCASCADE Python bindings) doesn't exist for arm64 on conda-forge yet. However, the Intel build works fine on Apple Silicon via **Rosetta 2** - macOS will prompt to install it on first launch.

**DE:** Native arm64 Builds sind nicht verfügbar, da das `ocp` Paket noch nicht für arm64 auf conda-forge existiert. Der Intel-Build funktioniert aber problemlos auf Apple Silicon via **Rosetta 2** - macOS fragt beim ersten Start nach der Installation.

## License / Lizenz

MIT

## Credits

- [Build123d](https://github.com/gumyr/build123d) - CAD Kernel
- [PyVista](https://github.com/pyvista/pyvista) - 3D Rendering
