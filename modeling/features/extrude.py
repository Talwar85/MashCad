from dataclasses import dataclass, field
from typing import Optional, Any
from .base import Feature, FeatureType
import sketcher
from sketcher import Sketch
from modeling.tnp_system import ShapeID

@dataclass
class ExtrudeFeature(Feature):
    """
    Extrude Feature - CAD Kernel First Architektur.

    Profile werden IMMER aus dem Sketch abgeleitet (wenn sketch vorhanden).
    profile_selector identifiziert welche Profile gewählt wurden (via Centroid).
    precalculated_polys ist NUR für sketchlose Operationen (Push/Pull).
    """
    sketch: Sketch = None
    distance: float = 10.0
    distance_formula: Optional[str] = None
    direction: int = 1
    operation: str = "New Body"
    selector: list = None
    # CAD Kernel First: Profile-Selektor (Centroids der gewählten Profile)
    # Bei Rebuild werden Profile aus Sketch berechnet und per Centroid-Match gefiltert
    profile_selector: list = field(default_factory=list)  # [(cx, cy), ...] Centroids
    # Legacy: Nur für sketchlose Operationen (Push/Pull auf 3D-Face)
    precalculated_polys: list = field(default_factory=list)
    # Plane-Info für Rebuild (wenn sketch=None)
    plane_origin: tuple = field(default_factory=lambda: (0, 0, 0))
    plane_normal: tuple = field(default_factory=lambda: (0, 0, 1))
    plane_x_dir: tuple = None
    plane_y_dir: tuple = None
    # Push/Pull auf nicht-planaren Flächen: OCP Face als BREP-String speichern
    face_brep: Optional[str] = None  # Serialisierte OCP TopoDS_Face
    face_type: Optional[str] = None  # "plane", "cylinder", "cone", etc.
    # TNP v4.0: Push/Pull Face-Referenz (ShapeID primary, Index secondary, Selector fallback)
    face_shape_id: Any = None
    face_index: Optional[int] = None
    face_selector: dict = None  # GeometricFaceSelector als Legacy-Recovery

    # TNP v4.1: Sketch-Edge-Mapping nach Extrusion
    # Mapping von Sketch-Element-IDs zu den generierten 3D-Edge-ShapeIDs
    # Format: {sketch_element_id: edge_shape_uuid, ...}
    # Dies ermöglicht die Rückverfolgung von Sketch-Kanten zu 3D-Edges
    sketch_edge_mappings: dict = field(default_factory=dict)

    def __post_init__(self):
        self.type = FeatureType.EXTRUDE
        if not self.name or self.name == "Feature": self.name = "Extrude"
        if self.face_index is not None:
            try:
                self.face_index = int(self.face_index)
            except Exception:
                self.face_index = None

@dataclass
class PushPullFeature(Feature):
    """
    PushPull Feature - Interaktive Extrusion von existierenden Body-Faces.

    PushPull ermöglicht:
    - "Pull" (+distance): Material zur Face hinzufügen (Extrusion)
    - "Push" (-distance): Material von der Face entfernen (Cut)

    Arbeitet direkt auf Body-Faces ohne Sketch:
    - Face wird über face_shape_id, face_index oder face_selector referenziert
    - Face-Geometrie wird als Extrusions-Profil verwendet
    - Unterstützt planare und gekrümmte Faces (Zylinder, Kegel, etc.)

    Beispiel:
        feat = PushPullFeature(
            face_index=0,        # Obere Fläche einer Box
            distance=5.0,        # 5mm nach oben ziehen (Pull)
            direction=1          # Normalenrichtung der Face
        )
    """
    # Face-Referenz (welche Face wird extrudiert?)
    face_shape_id: Any = None           # TNP v4.0: Primäre Face-Referenz
    face_index: Optional[int] = None    # Fallback: Face-Index im Solid
    face_selector: dict = None          # GeometricFaceSelector als Legacy-Fallback

    # Extrusions-Parameter
    distance: float = 10.0              # Extrusions-Distanz (+ = Pull, - = Push)
    distance_formula: Optional[str] = None  # Formel für parametrische Distanz
    direction: int = 1                  # 1 = entlang Normal, -1 = entgegen Normal

    # Operation-Typ
    operation: str = "Join"             # "Join" (Pull/Add) oder "Cut" (Push/Remove)

    # Face-Geometrie für Rebuild (wenn Face nach Boolean nicht mehr auffindbar)
    face_brep: Optional[str] = None     # Serialisierte OCP TopoDS_Face
    face_type: Optional[str] = None     # "plane", "cylinder", "cone", etc.

    # Plane-Info für gekrümmte Faces (für Rekonstruktion der Extrusionsrichtung)
    plane_origin: tuple = field(default_factory=lambda: (0, 0, 0))
    plane_normal: tuple = field(default_factory=lambda: (0, 0, 1))
    plane_x_dir: tuple = None
    plane_y_dir: tuple = None

    # Profile als Fallback (wenn Face-BREP nicht verfügbar)
    precalculated_polys: list = field(default_factory=list)

    def __post_init__(self):
        self.type = FeatureType.PUSHPULL
        if not self.name or self.name == "Feature":
            op_name = "Pull" if self.distance >= 0 else "Push"
            self.name = f"PushPull: {op_name}"
        if self.face_index is not None:
            try:
                self.face_index = int(self.face_index)
            except Exception:
                self.face_index = None

    def get_effective_distance(self) -> float:
        """Gibt die effektive Distanz mit Richtung zurück."""
        return self.distance * self.direction

    def is_push(self) -> bool:
        """True wenn Push-Operation (Material entfernen)."""
        return self.get_effective_distance() < 0

    def is_pull(self) -> bool:
        """True wenn Pull-Operation (Material hinzufügen)."""
        return self.get_effective_distance() > 0

    def validate(self) -> tuple[bool, str]:
        """
        Validiert das PushPull-Feature vor Ausführung.

        Returns:
            (is_valid, error_message)
        """
        has_face_ref = (
            self.face_shape_id is not None or
            self.face_index is not None or
            self.face_selector is not None
        )

        if not has_face_ref:
            return False, "PushPullFeature needs face_shape_id, face_index, or face_selector"

        if self.distance == 0:
            return False, "PushPull distance cannot be zero"

        return True, ""
