
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from .base import Feature, FeatureType

@dataclass
class PatternFeature(Feature):
    """
    Pattern Feature - Lineare, zirkulare und Spiegel-Muster.

    Pattern ermöglicht das mehrfache Wiederholen von Features:
    - Linear Pattern: Reihen in X/Y-Richtung mit Abständen
    - Circular Pattern: Rotation um einen Achsen-Punkt
    - Mirror Pattern: Spiegelung an einer Ebene

    Beispiel:
        # Linear Pattern: 3 Reihen à 5 Elemente, 20mm Abstand
        feat = PatternFeature(
            pattern_type="Linear",
            feature_id="base_feature_123",
            count=5,
            spacing=20.0,
            direction_1=(1, 0, 0),
            direction_2=(0, 1, 0),
            count_2=3
        )
    """
    # Pattern-Typ
    pattern_type: str = "Linear"  # "Linear", "Circular", "Mirror"

    # Feature-Referenz (welches Feature wird wiederholt?)
    feature_id: Optional[str] = None  # ID des zu wiederholenden Features
    feature_indices: List = field(default_factory=list)  # Legacy: Feature-Indizes

    # Linear Pattern Parameter
    count: int = 2                      # Anzahl der Kopien
    spacing: float = 10.0              # Abstand zwischen Kopien
    direction_1: Tuple[float, float, float] = (1, 0, 0)  # Primäre Richtung
    direction_2: Tuple[float, float, float] = (0, 1, 0)  # Sekundäre Richtung (für 2D)
    count_2: Optional[int] = None        # Anzahl in sekundärer Richtung

    # Circular Pattern Parameter
    axis_origin: Tuple[float, float, float] = (0, 0, 0)  # Drehpunkt (für Circular)
    axis_direction: Tuple[float, float, float] = (0, 0, 1)  # Achsenrichtung
    angle: float = 360.0               # Gesamtwinkel (für Circular)

    # Mirror Pattern Parameter
    mirror_plane: Optional[str] = None  # "XY", "XZ", "YZ" oder benutzerdefinierte Ebene
    mirror_origin: Tuple[float, float, float] = (0, 0, 0)
    mirror_normal: Tuple[float, float, float] = (0, 0, 1)

    def __post_init__(self):
        self.type = FeatureType.PATTERN
        if not self.name or self.name == "Feature":
            self.name = f"Pattern: {self.pattern_type}"
        if self.feature_indices is None:
            self.feature_indices = []

    def get_total_instances(self) -> int:
        """Gibt die Gesamtzahl der Instanzen zurück."""
        if self.pattern_type == "Linear":
            if self.count_2:
                return self.count * self.count_2
            return self.count
        elif self.pattern_type == "Circular":
            return self.count
        elif self.pattern_type == "Mirror":
            return 2  # Original + gespiegelt
        return 1

    def validate(self) -> Tuple[bool, str]:
        """
        Validiert das Pattern-Feature vor Ausführung.

        Returns:
            (is_valid, error_message)
        """
        if self.pattern_type not in ["Linear", "Circular", "Mirror"]:
            return False, f"Unknown pattern_type: {self.pattern_type}"

        if self.pattern_type == "Linear":
            if self.count < 2:
                return False, "Linear pattern count must be at least 2"
            if self.spacing <= 0:
                return False, "Pattern spacing must be positive"

        elif self.pattern_type == "Circular":
            if self.count < 2:
                return False, "Circular pattern count must be at least 2"

        elif self.pattern_type == "Mirror":
            if not self.mirror_plane:
                return False, "Mirror pattern requires mirror_plane"

        return True, ""
