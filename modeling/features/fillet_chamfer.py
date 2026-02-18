from dataclasses import dataclass, field
from typing import Optional, List
from .base import Feature, FeatureType
from modeling.tnp_system import ShapeID


def _canonicalize_indices(indices):
    """
    Normalisiert Topologie-Indizes fuer Determinismus (EPIC X2).

    Stellt sicher dass edge_indices, face_indices etc. immer
    sortiert und entdupliziert sind. Dies ist kritisch fuer:
    - Rebuild-Idempotenz
    - Save/Load Konsistenz
    - TNP Reference Stability

    Args:
        indices: Liste von Indizes (int, float, oder andere)

    Returns:
        Sorted list of unique non-negative integers
    """
    if not indices:
        return []

    canonical = set()
    for idx in indices:
        try:
            i = int(idx)
            if i >= 0:
                canonical.add(i)
        except (ValueError, TypeError):
            continue

    return sorted(canonical)


@dataclass
class FilletFeature(Feature):
    """
    Fillet-Feature mit professionellem TNP (Topological Naming Problem) Handling.

    TNP v4.0 Architektur:
    1. edge_shape_ids: Persistent ShapeIDs für History-Tracking
    2. edge_indices: Stabile Topologie-Indizes (solid.edges()[idx])
    2. geometric_selectors: Geometrische Fingerabdrücke (Fallback)

    Das Feature speichert ShapeIDs beim Erstellen und löst diese
    via TNPResolver zum Zeitpunkt der Ausführung auf.
    """
    radius: float = 2.0
    radius_formula: Optional[str] = None

    # TNP v4.0: Persistent ShapeIDs (Primary)
    edge_shape_ids: List = None  # List[ShapeID] - persistente IDs
    edge_indices: List = None    # List[int] - stabile Kantenindizes

    # Fallback: Geometric Selectors
    geometric_selectors: List = None  # GeometricEdgeSelector Objekte

    ocp_edge_shapes: List = None  # OCP TopoDS_Edge Shapes

    # TNP Phase 2: Abhängigkeit zu vorherigem Boolean-Feature
    depends_on_feature_id: Optional[str] = None

    def __post_init__(self):
        self.type = FeatureType.FILLET
        if not self.name or self.name == "Feature":
            self.name = "Fillet"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        # EPIC X2: Canonicalize edge_indices for determinism
        if self.edge_indices is None:
            self.edge_indices = []
        else:
            self.edge_indices = _canonicalize_indices(self.edge_indices)
        if self.geometric_selectors is None:
            self.geometric_selectors = []
        if self.ocp_edge_shapes is None:
            self.ocp_edge_shapes = []


@dataclass
class ChamferFeature(Feature):
    """
    Chamfer-Feature mit professionellem TNP (Topological Naming Problem) Handling.

    TNP v4.0 Architektur:
    1. edge_shape_ids: Persistent ShapeIDs für History-Tracking
    2. edge_indices: Stabile Topologie-Indizes (solid.edges()[idx])
    2. geometric_selectors: Geometrische Fingerabdrücke (Fallback)

    Das Feature speichert ShapeIDs beim Erstellen und löst diese
    via TNPResolver zum Zeitpunkt der Ausführung auf.
    """
    distance: float = 2.0
    distance_formula: Optional[str] = None

    # TNP v4.0: Persistent ShapeIDs (Primary)
    edge_shape_ids: List = None  # List[ShapeID] - persistente IDs
    edge_indices: List = None    # List[int] - stabile Kantenindizes

    # Fallback: Geometric Selectors
    geometric_selectors: List = None  # GeometricEdgeSelector Objekte

    ocp_edge_shapes: List = None  # OCP TopoDS_Edge Shapes

    # TNP Phase 2: Abhängigkeit zu vorherigem Boolean-Feature
    depends_on_feature_id: Optional[str] = None

    def __post_init__(self):
        self.type = FeatureType.CHAMFER
        if not self.name or self.name == "Feature":
            self.name = "Chamfer"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        # EPIC X2: Canonicalize edge_indices for determinism
        if self.edge_indices is None:
            self.edge_indices = []
        else:
            self.edge_indices = _canonicalize_indices(self.edge_indices)
        if self.geometric_selectors is None:
            self.geometric_selectors = []
        if self.ocp_edge_shapes is None:
            self.ocp_edge_shapes = []
