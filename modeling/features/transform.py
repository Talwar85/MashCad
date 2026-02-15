
from dataclasses import dataclass, field
from .base import Feature, FeatureType

@dataclass
class TransformFeature(Feature):
    """
    Parametric transform stored in feature history.

    Enables:
    - Undo/Redo support
    - Parametric editing
    - Feature tree visibility
    - Body rebuild consistency
    """
    mode: str = "move"  # "move", "rotate", "scale", "mirror"
    data: dict = field(default_factory=dict)
    # data examples:
    # Move: {"translation": [10.0, 0.0, 5.0]}
    # Rotate: {"axis": "Z", "angle": 45.0, "center": [0.0, 0.0, 0.0]}
    # Scale: {"factor": 1.5, "center": [0.0, 0.0, 0.0]}
    # Mirror: {"plane": "XY"}

    def __post_init__(self):
        self.type = FeatureType.TRANSFORM
        if not self.name or self.name == "Feature":
            self.name = f"Transform: {self.mode.capitalize()}"
