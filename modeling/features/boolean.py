
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from .base import Feature, FeatureType

@dataclass
class BooleanFeature(Feature):
    """
    Boolean-Feature für professionelle CAD-Operationen.

    Unterützt Union (Join), Cut und Common (Intersect) mit:
    - BooleanEngineV4 Integration (Transaction Safety, Fail-Fast)
    - TNP v4.0 Shape-Tracking für verlässliche Referenzen
    - Tool-Body Referenz (für parametrische Updates)
    - Konfigurierbare Toleranzen

    Beispiel:
        feat = BooleanFeature(
            operation="Cut",
            tool_body_id=cutter_body.id,
            fuzzy_tolerance=0.0001
        )
    """
    # Boolean-Operation-Typ
    operation: str = "Cut"  # "Join" (Union), "Cut" (Subtract), "Common" (Intersect)

    # Tool-Referenz (Body oder direkter Solid)
    tool_body_id: Optional[str] = None  # ID des Tool-Body (für parametrische Updates)
    tool_solid_data: Optional[str] = None  # Serialisierter OCP Solid als Fallback

    # TNP v4.0: Shape-Referenzen für modifizierte Faces/Edges
    modified_shape_ids: List = None  # List[ShapeID] - vom Boolean veränderte Shapes

    # Boolean-Einstellungen
    fuzzy_tolerance: Optional[float] = None  # Custom Toleranz (None = Default)

    # Geometrie-Info für Validation
    expected_volume_change: Optional[float] = None  # Erwartete Volumenänderung

    # TNP v5.0: Input Shape UUIDs (shapes before boolean operation)
    tnp_v5_input_face_ids: list = field(default_factory=list)
    tnp_v5_input_edge_ids: list = field(default_factory=list)

    # TNP v5.0: Output Shape UUIDs (shapes after boolean operation)
    tnp_v5_output_face_ids: list = field(default_factory=list)
    tnp_v5_output_edge_ids: list = field(default_factory=list)

    # TNP v5.0: OCCT History data (when available)
    tnp_v5_occt_history: dict = None  # Serialized OCCT BRepTools_History

    # TNP v5.0: Shape transformation map (input -> output mappings)
    # Maps input shape UUIDs to their post-operation UUIDs
    tnp_v5_transformation_map: dict = field(default_factory=dict)

    def __post_init__(self):
        self.type = FeatureType.BOOLEAN
        if not self.name or self.name == "Feature":
            self.name = f"Boolean: {self.operation}"
        if self.modified_shape_ids is None:
            self.modified_shape_ids = []

    def get_operation_type(self) -> str:
        """Gibt den standardisierten Operation-Typ zurück."""
        op_map = {
            "Union": "Join",
            "Fuse": "Join",
            "Add": "Join",
            "Subtract": "Cut",
            "Difference": "Cut",
            "Intersect": "Common",
            "Common": "Common",
            "Intersection": "Common",
        }
        return op_map.get(self.operation, self.operation)

    def validate(self) -> Tuple[bool, str]:
        """
        Validiert das Boolean-Feature vor Ausführung.

        Returns:
            (is_valid, error_message)
        """
        if self.operation not in ["Join", "Cut", "Common"]:
            return False, f"Unknown operation: {self.operation}"

        if self.tool_body_id is None and self.tool_solid_data is None:
            return False, "BooleanFeature needs tool_body_id or tool_solid_data"

        return True, ""
