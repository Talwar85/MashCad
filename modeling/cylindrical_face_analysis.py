"""
Cylindrical Face Edit - Edge Cases Analysis
============================================

Analyse der Edge-Cases bei zylindrischen Face-Modifikationen, speziell
beim Verkleinern von Löchern (Material hinzufügen).

Problem: Loch verkleinern = Material hinzufügen
------------------------------------------------
Im Gegensatz zum Vergrößern (einfacher Cut) muss beim Verkleinern Material
"zurückgegeben" werden. Das raises Fragen über die Geometrie:

1. Woher kommt das Material?
2. Wie bleibt die umgebende Geometrie konsistent?
3. Was passiert mit benachbarten Features?

Szenarien und Lösungen
----------------------

Szenario 1: Einfaches Durchgangsloch in Block
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ausgangslage:
  - Block 50x50x10 mit Loch Durchmesser 10mm
  - Loch soll auf 8mm verkleinert werden

Lösung A: Boolean Union mit Zylinder
  - Zylinder mit 8mm Durchmesser an gleicher Position erstellen
  - Union mit Block ausführen
  - Problem: Zylinder ist "unendlich" - muss auf Block-Größe beschränkt werden

Lösung B: Zylinder auf Block-Maße beschränken
  - Zylinder mit 8mm Durchmesser und Höhe = Block-Höhe
  - Position korrekt ausrichten
  - Union mit Block ausführen
  - ✓ Konsistente Geometrie


Szenario 2: Bohrung mit konischer Öffnung (Countersink)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ausgangslage:
  - Block mit Loch 10mm + Senkung 15mm, 90°
  - Loch soll auf 8mm verkleinert werden

Problem:
  - Senkung bleibt 15mm, aber Loch wird 8mm
  - Übergang zwischen Senkung und neuem Loch

Lösung:
  - Nur den zylindrischen Teil ersetzen
  - Senkung beibehalten
  - Benötigt präzise Face-Selektion (TNP v4.1)


Szenario 3: Multiple Bohrungen auf gleicher Achse
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ausgangslage:
  - Block mit 3 Löchern auf gleicher Achse (verschachtelte Bohrungen)
  - Loch-Set soll verkleinert werden

Problem:
  - Welche Löcher gehören zusammen?
  - Wie bleibt die Verschachtelung konsistent?

Lösung:
  - Feature-Gruppierung erforderlich
  - Alle zylindrischen Faces auf gleicher Achse identifizieren
  - Zusammen verarbeiten


Szenario 4: Loch im Assembly (Multi-Body)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ausgangslage:
  - Assembly mit 2 Bodies, die durch Bohrung verbunden werden
  - Bohrung soll verkleinert werden

Problem:
  - Bohrung existiert nicht als Feature - ist Ergebnis von Assembly
  - Verkleinern würde Assembly "zerstören"

Lösung:
  - Assembly-Bearbeitung verbieten oder
  - Explizites "Bohrung durch Assembly" Feature erstellen


Szenario 5: Gelochte Fläche (Face mit vielen Löchern)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ausgangslage:
  - Fläche mit 10x10 Lochmuster (100 Löcher)
  - Ein Loch soll verkleinert werden

Problem:
  - Performance bei 100 Boolean-Operationen
  - Identifikation des korrekten Lochs

Lösung:
  - Single-Loch-Edit Feature (nur ein Loch pro Feature)
  - Pattern-Feature für Wiederholungen


Empfohlene Implementierung
---------------------------

1. **Erkennung (Detection)**
   - BRepAdaptor_Surface für zylindrische Faces
   - Parameter extrahieren (Location, Axis, Radius)
   - Typ bestimmen (Hole, Pocket, Solid Cylinder)

2. **Vergrößern (Enlarge)**
   - Boolean Cut mit größerem Zylinder
   - Zylinder-Höhe = BoundingBox der Face
   - Einfach und robust

3. **Verkleinern (Shrink)**
   - Boolean Union mit kleinerem Zylinder
   - Zylinder muss exakt auf BoundingBox beschränkt werden
   - Edge-Case: Angrenzende Features (Fillet, Chamfer) müssen beachtet werden

4. **TNP v4.1 Tracking**
   - ShapeID der zylindrischen Face speichern
   - Nach Boolean-Operation ShapeID aktualisieren
   - History-Tracking für Undo/Redo


Feature-Design
--------------

class CylindricalFaceEditFeature(Feature):
    \"\"\"Zylindrische Face Radius-Modifikation (Fusion360-style)\"\"\"

    face_shape_id: ShapeID        # TNP v4.1 Reference
    original_radius: float        # Ursprünglicher Radius
    new_radius: float             # Neuer Radius
    operation: Literal["enlarge", "shrink"]  # Art der Modifikation
    cylinder_params: CylinderParams  # Location, Axis, Height


Validierung
-----------
- Nur einfache zylindrische Faces (kein Sweep/Loft)
- Radius-Change begrenzen (min/max Validierung)
- Prüfen ob andere Features davon betroffen sind
- Boolean-Pre-Check (Self-Intersection)


Tests erforderlich
------------------
- test_cylindrical_face_enlarge_hole()
- test_cylindrical_face_shrink_hole()
- test_cylindrical_face_shrink_with_countersink()
- test_cylindrical_face_multiple_holes_same_axis()
- test_cylindrical_face_pocket_shrink()
- test_cylindrical_face_solid_cylinder_enlarge()
- test_cylindrical_face_undo_redo()
- test_cylindrical_face_tnp_tracking()


Fazit
-----
Die Boolean-basierte Lösung mit TNP v4.1 Tracking ist der robuste Ansatz.
"Loch verkleinern" ist über Boolean Union lösbar, wenn der Zylinder korrekt
auf die BoundingBox der Face beschränkt wird.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from build123d import Face, Solid


class CylindricalFaceType(Enum):
    """Typ der zylindrischen Face"""
    HOLE_OUTER = "hole_outer"      # Äußere Mantelfläche eines Lochs
    HOLE_INNER = "hole_inner"      # Innere Mantelfläche (bei konischen Löchern)
    POCKET_SIDE = "pocket_side"    # Seitenfläche einer Sackloch-Bohrung
    SOLID_CYLINDER = "solid"       # Voller Zylinder (kein Loch)
    UNKNOWN = "unknown"


@dataclass
class CylinderParams:
    """Extrahierte Zylinder-Parameter"""
    location: gp_Pnt              # Ursprung (Location)
    axis: gp_Dir                  # Achsenrichtung
    radius: float                 # Aktueller Radius
    height: Optional[float] = None  # Höhe (aus BBox)
    face_type: CylindricalFaceType = CylindricalFaceType.UNKNOWN


def analyze_cylindrical_face(face: Face) -> Optional[CylinderParams]:
    """
    Analysiert eine zylindrische Face und extrahiert Parameter.

    Args:
        face: Die zu analysierende Face

    Returns:
        CylinderParams mit extrahierten Parametern oder None wenn keine zylindrische Face
    """
    adaptor = BRepAdaptor_Surface(face.wrapped)

    if adaptor.GetType() != GeomAbs_Cylinder:
        return None

    cyl = adaptor.Cylinder()
    location = cyl.Location()
    axis = cyl.Axis().Direction()
    radius = cyl.Radius()

    # Face-Type bestimmen
    face_type = _determine_cylindrical_face_type(face, radius)

    return CylinderParams(
        location=location,
        axis=axis,
        radius=radius,
        face_type=face_type
    )


def _determine_cylindrical_face_type(face: Face, radius: float) -> CylindricalFaceType:
    """
    Bestimmt den Typ der zylindrischen Face.

    Hinweis: Vollständige Implementierung erfordert Edge-Analyse:
    - Durchgangsloch: 2 zirkuläre Edges
    - Sackloch: 1 zirkuläre Edge
    - Voller Zylinder: 0 oder 2 zirkuläre Edges (andere Topologie)

    Diese Analyse ist Teil der zukünftigen CylindricalFaceEditFeature Implementierung.
    Für den Moment wird UNKNOWN zurückgegeben.
    """
    # Analyse der Edges um Typ zu bestimmen
    edges = list(face.edges())

    # Einfache Heuristik - für vollständige Implementierung Edge-Analyse erforderlich
    return CylindricalFaceType.UNKNOWN


def can_enlarge_safely(params: CylinderParams, new_radius: float) -> bool:
    """
    Prüft ob ein Vergrößern sicher ist.

    Args:
        params: Aktuelle Zylinder-Parameter
        new_radius: Neuer Radius

    Returns:
        True wenn sicher, False wenn Probleme zu erwarten sind

    Hinweis: Zukünftige Implementierung sollte prüfen:
    - Ob andere Features im Weg sind (Fillet, Chamfer, etc.)
    - Ob Self-Intersection droht
    """
    if new_radius <= params.radius:
        return False  # Das ist Verkleinern, nicht Vergrößern

    # Für zukünftige Implementierung: Feature-Intersection und Self-Intersection Checks
    return True


def can_shrink_safely(params: CylinderParams, new_radius: float) -> bool:
    """
    Prüft ob ein Verkleinern sicher ist.

    Args:
        params: Aktuelle Zylinder-Parameter
        new_radius: Neuer Radius

    Returns:
        True wenn sicher, False wenn Probleme zu erwarten sind

    Hinweis: Zukünftige Implementierung sollte prüfen:
    - Ob Material vorhanden ist zum "Auffüllen" (bei Löchern)
    - Ob benachbarte Features (Fillet, Chamfer) betroffen sind
    """
    if new_radius >= params.radius:
        return False  # Das ist Vergrößern, nicht Verkleinern

    if new_radius <= 0:
        return False  # Radius muss positiv sein

    # Für zukünftige Implementierung: Material- und Feature-Abhängigkeits-Checks
    return True
