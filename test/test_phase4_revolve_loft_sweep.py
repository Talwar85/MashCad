"""
Phase 4: OCP-First Revolve/Loft/Sweep Integration Tests

Tests für die OCP-First Helper (OCPRevolveHelper, OCPLoftHelper, OCPSweepHelper)
mit TNP Integration.

Author: Claude (OCP-First Migration Phase 4)
Date: 2026-02-10
"""

import pytest
from loguru import logger
import math

from build123d import Solid, Face, Edge, Vector, Box, Wire
from modeling import Body, Document
from modeling.ocp_helpers import (
    OCPRevolveHelper,
    OCPLoftHelper,
    OCPSweepHelper,
    HAS_OCP
)

# Import test utilities direkt
import sys
from pathlib import Path
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

from config.feature_flags import is_enabled, set_flag


# ============================================================================
# SKIP CONDITIONAL
# ============================================================================

pytestmark = pytest.mark.skipif(
    not HAS_OCP,
    reason="OpenCASCADE (OCP) nicht verfügbar - Tests überspringen"
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def document_with_tnp():
    """Document mit TNP Service."""
    doc = Document("TestDoc")
    return doc


@pytest.fixture
def test_face(document_with_tnp):
    """Erstellt ein Test-Face (Rechteck)."""
    from build123d import make_face, Wire
    from shapely.geometry import Polygon

    # Rechteck-Polygon
    poly = Polygon([(0, 0), (10, 0), (10, 5), (0, 5)])

    # In 3D-Punkte konvertieren (XY Plane)
    outer_coords = list(poly.exterior.coords)[:-1]
    outer_pts = [Vector(p[0], p[1], 0) for p in outer_coords]
    face = make_face(Wire.make_polygon(outer_pts))

    return face


@pytest.fixture
def test_circular_face(document_with_tnp):
    """Erstellt ein kreisförmiges Test-Face."""
    from build123d import make_face

    # Kreis mit Radius 5
    circle = make_circle(5.0)
    face = make_face(circle)

    return face


# ============================================================================
# REVOLVE HELPER TESTS
# ============================================================================

class TestOCPRevolveHelper:
    """Tests für OCPRevolveHelper."""

    def test_revolve_180_degrees(self, document_with_tnp, test_face):
        """Test Revolve um 180 Grad."""
        feature_id = "revolve_180"

        result = OCPRevolveHelper.revolve(
            face=test_face,
            axis_origin=Vector(0, 0, 0),
            axis_direction=Vector(0, 1, 0),  # Y-Achse
            angle_deg=180.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)
        # Halbkreis sollte Volumen haben
        assert result.volume > 0

    def test_revolve_360_degrees(self, document_with_tnp, test_face):
        """Test Revolve um 360 Grad (vollständiger Rotation)."""
        feature_id = "revolve_360"

        result = OCPRevolveHelper.revolve(
            face=test_face,
            axis_origin=Vector(0, 0, 0),
            axis_direction=Vector(0, 1, 0),
            angle_deg=360.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)

    def test_revolve_without_tnp_service(self, test_face):
        """Test dass Revolve ohne TNP Service fehlschlägt."""
        feature_id = "revolve_no_tnp"

        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPRevolveHelper.revolve(
                face=test_face,
                axis_origin=Vector(0, 0, 0),
                axis_direction=Vector(0, 1, 0),
                angle_deg=180.0,
                naming_service=None,
                feature_id=feature_id
            )

    def test_revolve_without_feature_id(self, document_with_tnp, test_face):
        """Test dass Revolve ohne feature_id fehlschlägt."""
        with pytest.raises(ValueError, match="feature_id ist Pflicht"):
            OCPRevolveHelper.revolve(
                face=test_face,
                axis_origin=Vector(0, 0, 0),
                axis_direction=Vector(0, 1, 0),
                angle_deg=180.0,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id=None
            )


# ============================================================================
# LOFT HELPER TESTS
# ============================================================================

class TestOCPLoftHelper:
    """Tests für OCPLoftHelper."""

    def test_loft_two_faces(self, document_with_tnp, test_face):
        """Test Loft zwischen zwei Faces."""
        from build123d import Plane, Vector

        feature_id = "loft_two"

        # Zwei parallele Faces erstellen (unterschiedliche Z-Höhen)
        poly1 = [(0, 0), (10, 0), (10, 10), (0, 10)]
        poly2 = [(0, 0), (8, 0), (8, 8), (0, 8)]

        face1 = test_face  # 10x5 Rechteck

        # Zweites Face in anderem Plane
        plane = Plane(origin=Vector(0, 0, 10), z_dir=Vector(0, 0, 1))
        outer_pts2 = [Vector(p[0], p[1], 10) for p in poly2]
        from build123d import Wire, make_face
        face2 = make_face(Wire.make_polygon(outer_pts2))

        result = OCPLoftHelper.loft(
            faces=[face1, face2],
            ruled=False,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)
        assert result.volume > 0

    def test_loft_ruled_surface(self, document_with_tnp, test_face):
        """Test Loft mit ruled surface (gerade Linien)."""
        from build123d import Plane, Vector, Wire, make_face

        feature_id = "loft_ruled"

        # Zwei Faces
        outer_pts2 = [Vector(p[0], p[1], 10) for p in [(0, 0), (8, 0), (8, 8), (0, 8)]]
        face2 = make_face(Wire.make_polygon(outer_pts2))

        result = OCPLoftHelper.loft(
            faces=[test_face, face2],
            ruled=True,  # Gerade Linien
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)

    def test_loft_without_tnp_service(self, test_face):
        """Test dass Loft ohne TNP Service fehlschlägt."""
        from build123d import Plane, Vector, Wire, make_face

        outer_pts2 = [Vector(p[0], p[1], 10) for p in [(0, 0), (8, 0), (8, 8), (0, 8)]]
        face2 = make_face(Wire.make_polygon(outer_pts2))

        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPLoftHelper.loft(
                faces=[test_face, face2],
                ruled=False,
                naming_service=None,
                feature_id="loft_no_tnp"
            )

    def test_loft_with_single_face_error(self, document_with_tnp, test_face):
        """Test dass Loft mit nur einem Face fehlschlägt."""
        with pytest.raises(ValueError, match="mindestens 2 Faces"):
            OCPLoftHelper.loft(
                faces=[test_face],
                ruled=False,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id="loft_single"
            )


# ============================================================================
# SWEEP HELPER TESTS
# ============================================================================

class TestOCPSweepHelper:
    """Tests für OCPSweepHelper."""

    def test_sweep_along_edge(self, document_with_tnp, test_face):
        """Test Sweep entlang eines geraden Edges."""
        from build123d import Edge, Vector

        feature_id = "sweep_line"

        # Gerader Edge als Pfad
        path_edge = Edge.make_line(Vector(0, 0, 0), Vector(0, 0, 20))

        result = OCPSweepHelper.sweep(
            profile=test_face,
            path=path_edge,
            is_frenet=False,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)
        assert result.volume > 0

    def test_sweep_without_tnp_service(self, test_face):
        """Test dass Sweep ohne TNP Service fehlschlägt."""
        from build123d import Edge, Vector

        path_edge = Edge.make_line(Vector(0, 0, 0), Vector(0, 0, 20))

        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPSweepHelper.sweep(
                profile=test_face,
                path=path_edge,
                is_frenet=False,
                naming_service=None,
                feature_id="sweep_no_tnp"
            )

    def test_sweep_without_feature_id(self, document_with_tnp, test_face):
        """Test dass Sweep ohne feature_id fehlschlägt."""
        from build123d import Edge, Vector

        path_edge = Edge.make_line(Vector(0, 0, 0), Vector(0, 0, 20))

        with pytest.raises(ValueError, match="feature_id ist Pflicht"):
            OCPSweepHelper.sweep(
                profile=test_face,
                path=path_edge,
                is_frenet=False,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id=None
            )


# ============================================================================
# TNP REGISTRATION TESTS
# ============================================================================

class TestTNPRegistration:
    """Tests für TNP Registration bei Revolve/Loft/Sweep."""

    def test_revolve_tnp_registration(self, document_with_tnp, test_face):
        """Test dass Revolve Faces/Edges im TNP Service registriert."""
        feature_id = "revolve_tnp"

        initial_stats = document_with_tnp._shape_naming_service.get_stats()

        OCPRevolveHelper.revolve(
            face=test_face,
            axis_origin=Vector(0, 0, 0),
            axis_direction=Vector(0, 1, 0),
            angle_deg=180.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        final_stats = document_with_tnp._shape_naming_service.get_stats()

        # Es sollten neue Faces und Edges registriert worden sein
        assert final_stats['faces'] > initial_stats['faces']
        assert final_stats['edges'] > initial_stats['edges']

    def test_loft_tnp_registration(self, document_with_tnp, test_face):
        """Test dass Loft Faces/Edges im TNP Service registriert."""
        from build123d import Vector, Wire, make_face

        feature_id = "loft_tnp"

        outer_pts2 = [Vector(p[0], p[1], 10) for p in [(0, 0), (8, 0), (8, 8), (0, 8)]]
        face2 = make_face(Wire.make_polygon(outer_pts2))

        initial_stats = document_with_tnp._shape_naming_service.get_stats()

        OCPLoftHelper.loft(
            faces=[test_face, face2],
            ruled=False,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        final_stats = document_with_tnp._shape_naming_service.get_stats()

        # Es sollten neue Faces und Edges registriert worden sein
        assert final_stats['faces'] > initial_stats['faces']
        assert final_stats['edges'] > initial_stats['edges']

    def test_sweep_tnp_registration(self, document_with_tnp, test_face):
        """Test dass Sweep Faces/Edges im TNP Service registriert."""
        from build123d import Edge, Vector

        feature_id = "sweep_tnp"
        path_edge = Edge.make_line(Vector(0, 0, 0), Vector(0, 0, 20))

        initial_stats = document_with_tnp._shape_naming_service.get_stats()

        OCPSweepHelper.sweep(
            profile=test_face,
            path=path_edge,
            is_frenet=False,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        final_stats = document_with_tnp._shape_naming_service.get_stats()

        # Es sollten neue Faces und Edges registriert worden sein
        assert final_stats['faces'] > initial_stats['faces']
        assert final_stats['edges'] > initial_stats['edges']


# ============================================================================
# FEATURE FLAG TESTS
# ============================================================================

class TestFeatureFlags:
    """Tests für Feature Flags."""

    def test_ocp_first_revolve_flag(self):
        """Test dass ocp_first_revolve Flag auf True ist."""
        assert is_enabled("ocp_first_revolve") is True

    def test_ocp_first_loft_flag(self):
        """Test dass ocp_first_loft Flag auf True ist."""
        assert is_enabled("ocp_first_loft") is True

    def test_ocp_first_sweep_flag(self):
        """Test dass ocp_first_sweep Flag auf True ist."""
        assert is_enabled("ocp_first_sweep") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
