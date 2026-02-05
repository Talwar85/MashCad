"""
MashCad - Zentralisierte Toleranz-Konfiguration
================================================

Phase 5: Alle Toleranzen an einem Ort.

Toleranz-Philosophie:
- CAD-Kernel (OCP): 1e-4 (0.1mm) - CAD Standard
- Tessellation: 0.01 (10µm) - Visuelle Qualität
- Mesh-Cleaning: 1e-4 (0.1mm) - Nicht zu streng für 3D-Druck!
- Sketch: 1e-5 (1µm) - Präzision für Constraints

Verwendung:
    from config.tolerances import Tolerances

    # Direkt als Klassenvariablen
    fuzzy = Tolerances.KERNEL_FUZZY

    # Oder via Convenience-Funktionen
    from config.tolerances import kernel_tolerance
    fuzzy = kernel_tolerance()
"""


class Tolerances:
    """
    Zentrale Toleranz-Konstanten für MashCad.

    Kategorien:
    - KERNEL_*: CAD-Kernel Operationen (Boolean, Fillet, etc.)
    - TESSELLATION_*: Mesh-Generierung für Visualisierung
    - MESH_*: Mesh-Operationen (Import, Export, Cleaning)
    - SKETCH_*: 2D-Sketcher Operationen
    - GEOMETRY_*: Geometrie-Erkennung und Analyse
    """

    # =========================================================================
    # CAD-Kernel (Boolean, Fillet, Chamfer, etc.)
    # =========================================================================

    # Fuzzy-Toleranz für Boolean-Operationen
    # CAD nutzt ähnliche Werte (~0.1mm)
    # Zu klein (1e-7) = Operationen schlagen fehl
    # Zu groß (1e-2) = Ungenauigkeiten
    KERNEL_FUZZY = 1e-4  # 0.1mm - Produktions-Standard

    # Interne Kernel-Präzision (für sehr genaue Berechnungen)
    KERNEL_PRECISION = 1e-6  # 0.001mm

    # Minimale Volumenänderung für erfolgreiche Boolean-Operation
    # Verhindert "False Positives" bei Operationen ohne Effekt
    KERNEL_MIN_VOLUME_CHANGE = 1e-6  # 0.000001 mm³

    # =========================================================================
    # Tessellation (Mesh-Generierung für Visualisierung)
    # =========================================================================

    # Lineare Abweichung (Chord Height)
    # Kleinere Werte = mehr Dreiecke, bessere Qualität
    TESSELLATION_QUALITY = 0.01  # 10µm

    # Winkel-Abweichung in Radians
    # Kontrolliert Kurven-Approximation
    TESSELLATION_ANGULAR = 0.2  # ~11.5°

    # Edge-Deflection für B-Rep Kanten-Extraktion
    TESSELLATION_EDGE_DEFLECTION = 0.1  # 0.1mm

    # Preview-Qualität (gröber für schnellere Vorschau)
    TESSELLATION_PREVIEW = 0.05  # 50µm - schnelle Vorschau

    # Fallback-Qualität (noch gröber für direkte Methoden)
    TESSELLATION_COARSE = 0.1  # 100µm - schnellste Option

    # =========================================================================
    # Mesh-Operationen (Import, Export, Cleaning)
    # =========================================================================

    # Merge-Toleranz für Mesh-Cleaning
    # WICHTIG: 1e-6 ist zu streng für 3D-Druck-Modelle!
    MESH_CLEAN = 1e-4  # 0.1mm

    # STL/STEP Export Toleranz
    MESH_EXPORT = 1e-3  # 1mm (gröber für kleinere Dateien)

    # Import-Toleranz für externe Meshes
    MESH_IMPORT = 1e-4  # 0.1mm

    # =========================================================================
    # Sketch/2D Operationen
    # =========================================================================

    # Snap-Distanz für Punkt-Snapping (mathematisch)
    SKETCH_SNAP = 1e-5  # 1µm

    # Snap-Radius für UI in Pixel (visueller Fangbereich)
    # Größere Werte = leichteres Snapping, aber weniger Präzision
    SKETCH_SNAP_RADIUS_PX = 15  # Pixel

    # Coincident-Constraint Toleranz
    SKETCH_COINCIDENT = 1e-5  # 1µm

    # Parallel/Perpendicular Winkel-Toleranz (Radians)
    SKETCH_ANGULAR = 1e-4  # ~0.006°

    # Circle-Fitting Toleranz (für Auto-Erkennung)
    SKETCH_CIRCLE_FIT = 0.02  # 2% Radius-Varianz

    # =========================================================================
    # Geometrie-Erkennung und Analyse
    # =========================================================================

    # Planare Flächen-Erkennung
    GEOMETRY_PLANAR = 1e-4  # 0.1mm

    # Lineare Kanten-Erkennung
    GEOMETRY_LINEAR = 1e-4  # 0.1mm

    # Zylindrische Flächen-Erkennung
    GEOMETRY_CYLINDRICAL = 1e-4  # 0.1mm

    # =========================================================================
    # UI/Picker-Toleranzen
    # =========================================================================

    # VTK Picker Toleranz (für Raycasting/Picking)
    PICKER_TOLERANCE = 0.005  # 5mm Picking-Radius

    # Grober Picker (für weniger präzise Auswahl)
    PICKER_TOLERANCE_COARSE = 0.01  # 10mm

    # =========================================================================
    # Mathematische Epsilon-Werte (Numerische Stabilität)
    # =========================================================================

    # Vermeidet Division durch Null
    EPSILON_MATH = 1e-9

    # Normal-Vektor Validierung
    EPSILON_NORMAL = 1e-6

    # =========================================================================
    # Vergleichs-Toleranzen
    # =========================================================================

    # Punkt-Vergleich (sind zwei Punkte "gleich"?)
    COMPARE_POINT = 1e-6  # 1µm

    # Winkel-Vergleich (sind zwei Winkel "gleich"?)
    COMPARE_ANGLE = 1e-6  # Radians

    # Längen-Vergleich (sind zwei Längen "gleich"?)
    COMPARE_LENGTH = 1e-6  # mm


# =============================================================================
# Convenience-Funktionen
# =============================================================================

def kernel_tolerance() -> float:
    """Gibt die Standard-Kernel-Toleranz zurück."""
    return Tolerances.KERNEL_FUZZY


def mesh_tolerance() -> float:
    """Gibt die Standard-Mesh-Toleranz zurück."""
    return Tolerances.MESH_CLEAN


def sketch_tolerance() -> float:
    """Gibt die Standard-Sketch-Toleranz zurück."""
    return Tolerances.SKETCH_SNAP


def tessellation_quality() -> float:
    """Gibt die Standard-Tessellations-Qualität zurück."""
    return Tolerances.TESSELLATION_QUALITY


# =============================================================================
# Toleranz-Validierung (für Debugging)
# =============================================================================

def validate_tolerances():
    """
    Validiert dass alle Toleranzen sinnvolle Werte haben.
    Nützlich für Tests und Debugging.
    """
    issues = []

    # Kernel-Toleranz sollte zwischen 1e-6 und 1e-2 liegen
    if not (1e-6 <= Tolerances.KERNEL_FUZZY <= 1e-2):
        issues.append(f"KERNEL_FUZZY außerhalb sinnvoller Grenzen: {Tolerances.KERNEL_FUZZY}")

    # Mesh-Clean sollte nicht strenger als Kernel sein
    if Tolerances.MESH_CLEAN < Tolerances.KERNEL_FUZZY:
        issues.append(f"MESH_CLEAN ({Tolerances.MESH_CLEAN}) strenger als KERNEL_FUZZY ({Tolerances.KERNEL_FUZZY})")

    # Tessellation-Quality sollte zwischen 0.001 und 0.1 liegen
    if not (0.001 <= Tolerances.TESSELLATION_QUALITY <= 0.1):
        issues.append(f"TESSELLATION_QUALITY außerhalb sinnvoller Grenzen: {Tolerances.TESSELLATION_QUALITY}")

    return issues


# Automatische Validierung beim Import (nur Warnung, kein Fehler)
_validation_issues = validate_tolerances()
if _validation_issues:
    from loguru import logger
    for issue in _validation_issues:
        logger.warning(f"Toleranz-Validierung: {issue}")
