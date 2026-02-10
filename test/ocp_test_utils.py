"""
OCP Test Utilities - Hilfsfunktionen für OCP-First Tests

WICHTIG: Alle Tests MÜSSEN mit TNP-Integration arbeiten!
Keine Tests ohne naming_service!

Author: Claude (OCP-First Migration Phase 1)
Date: 2026-02-10
"""

import pytest
from typing import List, Optional, Any
from loguru import logger

from build123d import (
    Solid, Face, Edge, Wire, Vector
    # Plane, Sketch, Rectangle werden nicht mehr verwendet
)
from modeling.tnp_system import ShapeNamingService, ShapeType
from config.feature_flags import set_flag, is_enabled


class OCPTestContext:
    """
    Test-Kontext für OCP-First Tests.

    Stellt einen vollständigen Kontext mit:
    - ShapeNamingService
    - Test-Dokument (optional)
    """

    def __init__(self):
        """Initialisiert den Test-Kontext."""
        self.naming_service = ShapeNamingService()
        self.feature_counter = 0
        self.created_solids: List[Solid] = []
        self.created_features: dict = {}

    def create_feature_id(self, feature_type: str = "test") -> str:
        """
        Erstellt eine eindeutige Feature-ID für Tests.

        Args:
            feature_type: Typ des Features (z.B. "extrude", "fillet")

        Returns:
            Feature-ID String
        """
        self.feature_counter += 1
        feature_id = f"{feature_type}_{self.feature_counter}"
        self.created_features[feature_id] = {
            "type": feature_type,
            "index": self.feature_counter
        }
        return feature_id
    
    def register_solid(self, solid: Solid, feature_id: str) -> None:
        """
        Registriert einen Solid im Test-Kontext.
        
        Args:
            solid: Zu registrierender Solid
            feature_id: Feature-ID
        """
        self.created_solids.append(solid)
        self.naming_service.register_solid(solid, feature_id)
        
    def get_stats(self) -> dict:
        """
        Gibt Statistiken über den Test-Kontext zurück.
        
        Returns:
            Dict mit Stats (faces, edges, vertices, solids, features)
        """
        stats = {
            "solids": len(self.created_solids),
            "features": len(self.created_features)
        }
        
        if self.naming_service:
            tnp_stats = self.naming_service.get_stats()
            stats.update(tnp_stats)
        
        return stats
    
    def cleanup(self) -> None:
        """
        Bereinigt den Test-Kontext.
        """
        self.naming_service = ShapeNamingService()
        self.created_solids.clear()
        self.created_features.clear()
        self.feature_counter = 0


def create_test_box(
    size: tuple = (10.0, 10.0, 10.0),
    centered: bool = False
) -> Solid:
    """
    Erstellt einen Test-Box-Solid.
    
    Args:
        size: (width, height, depth)
        centered: Ob Box zentriert sein soll
        
    Returns:
        Build123d Box Solid
    """
    if centered:
        # Zentriert erstellen
        offset_x = -size[0] / 2
        offset_y = -size[1] / 2
        offset_z = -size[2] / 2
        box = Solid.make_box(*size)
        box.move(Vector(offset_x, offset_y, offset_z))
    else:
        box = Solid.make_box(*size)
    
    return box


def create_test_cylinder(
    radius: float = 5.0,
    height: float = 10.0,
    centered: bool = False
) -> Solid:
    """
    Erstellt einen Test-Cylinder-Solid.
    
    Args:
        radius: Zylinder-Radius
        height: Zylinder-Höhe
        centered: Ob Zylinder zentriert sein soll
        
    Returns:
        Build123d Cylinder Solid
    """
    if centered:
        # Zentriert erstellen
        offset_z = -height / 2
        cylinder = Solid.make_cylinder(radius, height)
        cylinder.move(Vector(0, 0, offset_z))
    else:
        cylinder = Solid.make_cylinder(radius, height)
    
    return cylinder


def create_test_sketch_face(
    width: float = 10.0,
    height: float = 10.0
) -> Face:
    """
    Erstellt eine Test-Sketch-Face (Rechteck auf XY-Plane).

    Args:
        width: Rechteck-Breite
        height: Rechteck-Höhe

    Returns:
        Build123d Face
    """
    # Direkt über Build123d erstellen
    from build123d import make_face, Wire

    # Rechteck als Wire erstellen
    pts = [
        Vector(0, 0, 0),
        Vector(width, 0, 0),
        Vector(width, height, 0),
        Vector(0, height, 0)
    ]
    wire = Wire.make_polygon(pts)
    face = make_face(wire)
    return face


def get_face_edges_count(solid: Solid) -> int:
    """
    Zählt die Edges in einem Solid.
    
    Args:
        solid: Build123d Solid
        
    Returns:
        Anzahl der Edges
    """
    edges = list(solid.edges())
    return len(edges)


def get_faces_count(solid: Solid) -> int:
    """
    Zählt die Faces in einem Solid.
    
    Args:
        solid: Build123d Solid
        
    Returns:
        Anzahl der Faces
    """
    faces = list(solid.faces())
    return len(faces)


def assert_solid_valid(solid: Solid) -> None:
    """
    Assert dass ein Solid valide ist.
    
    Args:
        solid: Build123d Solid
        
    Raises:
        AssertionError: Wenn Solid nicht valide
    """
    # Basic validity checks
    assert solid is not None, "Solid is None"
    assert solid.volume > 0, "Solid has zero or negative volume"
    assert solid.area > 0, "Solid has zero or negative area"
    
    # Check for faces
    faces = list(solid.faces())
    assert len(faces) > 0, "Solid has no faces"
    
    # Check for edges
    edges = list(solid.edges())
    assert len(edges) > 0, "Solid has no edges"


def assert_tnp_registered(
    naming_service: ShapeNamingService,
    expected_faces: int,
    expected_edges: Optional[int] = None
) -> None:
    """
    Assert dass TNP korrekt registriert wurde.
    
    Args:
        naming_service: ShapeNamingService
        expected_faces: Erwartete Anzahl Faces
        expected_edges: Optional erwartete Anzahl Edges
        
    Raises:
        AssertionError: Wenn TNP nicht korrekt registriert
    """
    stats = naming_service.get_stats()
    
    assert stats["faces"] >= expected_faces, (
        f"Expected at least {expected_faces} faces, "
        f"got {stats['faces']}"
    )
    
    if expected_edges is not None:
        assert stats["edges"] >= expected_edges, (
            f"Expected at least {expected_edges} edges, "
            f"got {stats['edges']}"
        )


def enable_tnp_debug_logging() -> None:
    """
    Aktiviert TNP Debug-Logging für Tests.
    """
    set_flag("tnp_debug_logging", True)


def disable_tnp_debug_logging() -> None:
    """
    Deaktiviert TNP Debug-Logging nach Tests.
    """
    set_flag("tnp_debug_logging", False)


class TNPMockService:
    """
    Mock TNP Service für Tests ohne vollständige TNP-Integration.
    
    WICHTIG: Nur für Unit-Tests verwenden!
    Integration-Tests MÜSSEN echten ShapeNamingService verwenden!
    """
    
    def __init__(self):
        self.faces: dict = {}
        self.edges: dict = {}
        self.face_counter = 0
        self.edge_counter = 0
    
    def register_shape(
        self,
        ocp_shape,
        shape_type: ShapeType,
        feature_id: str,
        local_index: int = 0
    ) -> str:
        """
        Registriert ein Shape (Mock).
        """
        if shape_type == ShapeType.FACE:
            shape_id = f"face_{self.face_counter}"
            self.faces[shape_id] = {
                "feature_id": feature_id,
                "local_index": local_index
            }
            self.face_counter += 1
            return shape_id
        
        return "mock_shape_id"
    
    def register_solid_edges(self, solid: Solid, feature_id: str) -> None:
        """
        Registriert Solid-Edges (Mock).
        """
        for edge in solid.edges():
            edge_id = f"edge_{self.edge_counter}"
            self.edges[edge_id] = {
                "feature_id": feature_id
            }
            self.edge_counter += 1
    
    def get_stats(self) -> dict:
        """
        Gibt Mock-Stats zurück.
        """
        return {
            "faces": len(self.faces),
            "edges": len(self.edges)
        }


@pytest.fixture
def ocp_test_context():
    """
    Pytest Fixture für OCP Test-Kontext.
    
    Wird automatisch für Tests verwendet:
    ```python
    def test_my_ocp_operation(ocp_test_context):
        ctx = ocp_test_context
        feature_id = ctx.create_feature_id("extrude")
        ...
    ```
    """
    ctx = OCPTestContext()
    yield ctx
    ctx.cleanup()


@pytest.fixture
def tnp_mock_service():
    """
    Pytest Fixture für Mock TNP Service.
    
    Nur für Unit-Tests verwenden!
    """
    service = TNPMockService()
    yield service