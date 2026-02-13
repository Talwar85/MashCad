from dataclasses import dataclass, field
from typing import Optional, Tuple, Any
from .base import Feature, FeatureType
import sketcher
from sketcher import Sketch
from modeling.tnp_system import ShapeID

@dataclass
class RevolveFeature(Feature):
    """
    Revolve Feature - CAD Kernel First Architektur.

    Profile werden IMMER aus dem Sketch abgeleitet (wenn sketch vorhanden).
    profile_selector identifiziert welche Profile gewählt wurden (via Centroid).

    TNP v4.0: Face-Referenz für Push/Pull auf 3D-Faces (konsistent zu ExtrudeFeature).
    """
    sketch: Sketch = None
    angle: float = 360.0
    angle_formula: Optional[str] = None
    axis: Tuple[float, float, float] = (0, 1, 0)
    axis_origin: Tuple[float, float, float] = (0, 0, 0)
    operation: str = "New Body"
    # CAD Kernel First: Profile-Selektor (Centroids der gewählten Profile)
    profile_selector: list = field(default_factory=list)  # [(cx, cy), ...] Centroids
    # Legacy: Nur für sketchlose Operationen
    precalculated_polys: list = None

    # TNP v4.0: Face-Referenz für Revolve-Push/Pull (konsistent zu ExtrudeFeature)
    # Ermöglicht Rebuild-Tracking von Faces nach Boolean-Operationen
    face_shape_id: Any = None
    face_index: Optional[int] = None
    face_selector: dict = None  # GeometricFaceSelector als Legacy-Recovery

    def __post_init__(self):
        self.type = FeatureType.REVOLVE
        if not self.name or self.name == "Feature": self.name = "Revolve"
