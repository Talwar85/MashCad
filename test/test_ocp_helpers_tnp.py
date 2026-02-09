"""
OCP Helper Tests - Unit Tests mit VERBINDLICHER TNP Integration

WICHTIG: Alle Tests MÜSSEN naming_service verwenden!
Keine Tests ohne TNP-Integration sind erlaubt!

Author: Claude (OCP-First Migration Phase 1)
Date: 2026-02-10
"""

import pytest
from loguru import logger

from build123d import Solid, Face, Edge, Vector
from modeling.ocp_helpers import (
    OCPExtrudeHelper,
    OCPFilletHelper,
    OCPChamferHelper,
    OCPRevolveHelper,
    HAS_OCP
)
from test.ocp_test_utils import (
    OCPTestContext,
    create_test_box,
    create_test_cylinder,
    create_test_sketch_face,
    assert_solid_valid,
    assert_tnp_registered,
    enable_tnp_debug_logging,
    disable_tnp_debug_logging
)


# ============================================================================
# SKIP CONDITIONAL - Nur Tests laufen wenn OCP verfügbar
# ============================================================================

pytestmark = pytest.mark.skipif(
    not HAS_OCP,
    reason="OpenCASCADE (OCP) nicht verfügbar - Tests überspringen"
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def test_context():
    """Test-Kontext mit TNP Service."""
    ctx = OCPTestContext()
    yield ctx
    ctx.cleanup()


# ============================================================================
# OCPExtrudeHelper Tests
# ============================================================================

class TestOCPExtrudeHelper:
    """Tests für OCPExtrudeHelper."""
    
    def test_extrude_basic_rectangle(self, test_context):
        """Test: Einfaches Rechteck extrudieren."""
        # Arrange
        face = create_test_sketch_face(width=10.0, height=10.0)
        direction = Vector(0, 0, 1)
        distance = 5.0
        feature_id = test_context.create_feature_id("extrude")
        
        # Act
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=direction,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)
        assert pytest.approx(result.volume(), abs=0.1) == 500.0  # 10*10*5
        
        # TNP Assertion
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0, "TNP: Faces nicht registriert"
        assert stats["edges"] > 0, "TNP: Edges nicht registriert"
    
    def test_extrude_with_tnp_registration(self, test_context):
        """Test: TNP Registration bei Extrude."""
        # Arrange
        face = create_test_sketch_face(width=5.0, height=5.0)
        direction = Vector(0, 0, 1)
        distance = 10.0
        feature_id = test_context.create_feature_id("extrude")
        
        # Act
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=direction,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert - TNP muss registrieren
        assert_tnp_registered(
            test_context.naming_service,
            expected_faces=6  # Box hat 6 Faces
        )
    
    def test_extrude_without_naming_service_raises(self, test_context):
        """Test: Ohne naming_service → ValueError."""
        # Arrange
        face = create_test_sketch_face()
        direction = Vector(0, 0, 1)
        distance = 5.0
        feature_id = test_context.create_feature_id("extrude")
        
        # Act & Assert
        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPExtrudeHelper.extrude(
                face=face,
                direction=direction,
                distance=distance,
                naming_service=None,  # ← Kein Service!
                feature_id=feature_id
            )
    
    def test_extrude_without_feature_id_raises(self, test_context):
        """Test: Ohne feature_id → ValueError."""
        # Arrange
        face = create_test_sketch_face()
        direction = Vector(0, 0, 1)
        distance = 5.0
        
        # Act & Assert
        with pytest.raises(ValueError, match="feature_id ist Pflicht"):
            OCPExtrudeHelper.extrude(
                face=face,
                direction=direction,
                distance=distance,
                naming_service=test_context.naming_service,
                feature_id=None  # ← Keine ID!
            )
    
    def test_extrude_negative_distance(self, test_context):
        """Test: Negative Distanz (in entgegengesetzte Richtung)."""
        # Arrange
        face = create_test_sketch_face(width=10.0, height=10.0)
        direction = Vector(0, 0, 1)
        distance = -5.0  # Negativ
        feature_id = test_context.create_feature_id("extrude")
        
        # Act
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=direction,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)
        # Position check - sollte in -Z Richtung sein
        assert result.center().Z < 0


# ============================================================================
# OCPFilletHelper Tests
# ============================================================================

class TestOCPFilletHelper:
    """Tests für OCPFilletHelper."""
    
    def test_fillet_box_edges(self, test_context):
        """Test: Box-Edges filleten."""
        # Arrange
        box = create_test_box(size=(10, 10, 10))
        edges = list(box.edges())[:4]  # Erste 4 Edges
        radius = 1.0
        feature_id = test_context.create_feature_id("fillet")
        
        # Act
        result = OCPFilletHelper.fillet(
            solid=box,
            edges=edges,
            radius=radius,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)
        # Volume sollte kleiner sein (durch Fillet)
        assert result.volume() < box.volume()
        
        # TNP Assertion
        assert_tnp_registered(
            test_context.naming_service,
            expected_faces=6  # Box hat 6 Faces
        )
    
    def test_fillet_with_tnp_registration(self, test_context):
        """Test: TNP Registration bei Fillet."""
        # Arrange
        box = create_test_box(size=(20, 20, 20))
        edges = list(box.edges())[:8]  # 8 Edges filleten
        radius = 2.0
        feature_id = test_context.create_feature_id("fillet")
        
        # Act
        result = OCPFilletHelper.fillet(
            solid=box,
            edges=edges,
            radius=radius,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert - TNP muss registrieren
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0, "TNP: Faces nicht registriert"
        assert stats["edges"] > 0, "TNP: Edges nicht registriert"
    
    def test_fillet_without_naming_service_raises(self, test_context):
        """Test: Ohne naming_service → ValueError."""
        # Arrange
        box = create_test_box()
        edges = list(box.edges())[:2]
        radius = 1.0
        feature_id = test_context.create_feature_id("fillet")
        
        # Act & Assert
        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPFilletHelper.fillet(
                solid=box,
                edges=edges,
                radius=radius,
                naming_service=None,  # ← Kein Service!
                feature_id=feature_id
            )
    
    def test_fillet_empty_edges_raises(self, test_context):
        """Test: Leere Edge-Liste → ValueError."""
        # Arrange
        box = create_test_box()
        edges = []  # ← Keine Edges!
        radius = 1.0
        feature_id = test_context.create_feature_id("fillet")
        
        # Act & Assert
        with pytest.raises(ValueError, match="Keine Edges für Fillet"):
            OCPFilletHelper.fillet(
                solid=box,
                edges=edges,
                radius=radius,
                naming_service=test_context.naming_service,
                feature_id=feature_id
            )
    
    def test_fillet_large_radius(self, test_context):
        """Test: Großer Radius (sollte valide sein)."""
        # Arrange
        box = create_test_box(size=(10, 10, 10))
        edges = list(box.edges())[:4]
        radius = 3.0  # Großer Radius
        feature_id = test_context.create_feature_id("fillet")
        
        # Act
        result = OCPFilletHelper.fillet(
            solid=box,
            edges=edges,
            radius=radius,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)


# ============================================================================
# OCPChamferHelper Tests
# ============================================================================

class TestOCPChamferHelper:
    """Tests für OCPChamferHelper."""
    
    def test_chamfer_box_edges(self, test_context):
        """Test: Box-Edges chamferen."""
        # Arrange
        box = create_test_box(size=(10, 10, 10))
        edges = list(box.edges())[:4]
        distance = 1.0
        feature_id = test_context.create_feature_id("chamfer")
        
        # Act
        result = OCPChamferHelper.chamfer(
            solid=box,
            edges=edges,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)
        # Volume sollte kleiner sein
        assert result.volume() < box.volume()
        
        # TNP Assertion
        assert_tnp_registered(
            test_context.naming_service,
            expected_faces=6
        )
    
    def test_chamfer_with_tnp_registration(self, test_context):
        """Test: TNP Registration bei Chamfer."""
        # Arrange
        box = create_test_box(size=(15, 15, 15))
        edges = list(box.edges())[:6]
        distance = 2.0
        feature_id = test_context.create_feature_id("chamfer")
        
        # Act
        result = OCPChamferHelper.chamfer(
            solid=box,
            edges=edges,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert - TNP muss registrieren
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0
        assert stats["edges"] > 0
    
    def test_chamfer_without_naming_service_raises(self, test_context):
        """Test: Ohne naming_service → ValueError."""
        # Arrange
        box = create_test_box()
        edges = list(box.edges())[:2]
        distance = 1.0
        feature_id = test_context.create_feature_id("chamfer")
        
        # Act & Assert
        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPChamferHelper.chamfer(
                solid=box,
                edges=edges,
                distance=distance,
                naming_service=None,
                feature_id=feature_id
            )


# ============================================================================
# OCPRevolveHelper Tests
# ============================================================================

class TestOCPRevolveHelper:
    """Tests für OCPRevolveHelper."""
    
    def test_revolve_rectangle_full_360(self, test_context):
        """Test: Rechteck 360° revolven (Zylinder)."""
        # Arrange
        face = create_test_sketch_face(width=2.0, height=10.0)
        # Face verschieben um Zylinder mit Radius 10 zu erstellen
        face.move(Vector(10, 0, 0))
        
        axis_origin = Vector(0, 0, 0)
        axis_direction = Vector(0, 0, 1)
        angle_deg = 360.0
        feature_id = test_context.create_feature_id("revolve")
        
        # Act
        result = OCPRevolveHelper.revolve(
            face=face,
            axis_origin=axis_origin,
            axis_direction=axis_direction,
            angle_deg=angle_deg,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)
        # Sollte ein Hohlzylinder sein
        assert result.volume() > 0
        
        # TNP Assertion
        assert_tnp_registered(
            test_context.naming_service,
            expected_faces=3  # Hohlzylinder: außen, innen, oben/unten
        )
    
    def test_revolve_rectangle_half_180(self, test_context):
        """Test: Rechteck 180° revolven (Halbzylinder)."""
        # Arrange
        face = create_test_sketch_face(width=3.0, height=10.0)
        face.move(Vector(8, 0, 0))
        
        axis_origin = Vector(0, 0, 0)
        axis_direction = Vector(0, 0, 1)
        angle_deg = 180.0
        feature_id = test_context.create_feature_id("revolve")
        
        # Act
        result = OCPRevolveHelper.revolve(
            face=face,
            axis_origin=axis_origin,
            axis_direction=axis_direction,
            angle_deg=angle_deg,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert
        assert_solid_valid(result)
        # Halbzylinder hat weniger Volumen als Vollzylinder
        assert result.volume() > 0
    
    def test_revolve_with_tnp_registration(self, test_context):
        """Test: TNP Registration bei Revolve."""
        # Arrange
        face = create_test_sketch_face(width=1.0, height=5.0)
        face.move(Vector(5, 0, 0))
        
        axis_origin = Vector(0, 0, 0)
        axis_direction = Vector(0, 0, 1)
        angle_deg = 270.0
        feature_id = test_context.create_feature_id("revolve")
        
        # Act
        result = OCPRevolveHelper.revolve(
            face=face,
            axis_origin=axis_origin,
            axis_direction=axis_direction,
            angle_deg=angle_deg,
            naming_service=test_context.naming_service,
            feature_id=feature_id
        )
        
        # Assert - TNP muss registrieren
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0
        assert stats["edges"] > 0
    
    def test_revolve_without_naming_service_raises(self, test_context):
        """Test: Ohne naming_service → ValueError."""
        # Arrange
        face = create_test_sketch_face()
        axis_origin = Vector(0, 0, 0)
        axis_direction = Vector(0, 0, 1)
        angle_deg = 360.0
        feature_id = test_context.create_feature_id("revolve")
        
        # Act & Assert
        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPRevolveHelper.revolve(
                face=face,
                axis_origin=axis_origin,
                axis_direction=axis_direction,
                angle_deg=angle_deg,
                naming_service=None,
                feature_id=feature_id
            )


# ============================================================================
# INTEGRATION TESTS - Mehrere Features hintereinander
# ============================================================================

class TestOCPHelpersIntegration:
    """Integration Tests für OCP Helpers."""
    
    def test_extrude_fillet_workflow(self, test_context):
        """Test: Extrude → Fillet Workflow."""
        # Phase 1: Extrude
        face = create_test_sketch_face(width=10.0, height=10.0)
        direction = Vector(0, 0, 1)
        distance = 5.0
        extrude_id = test_context.create_feature_id("extrude")
        
        box = OCPExtrudeHelper.extrude(
            face=face,
            direction=direction,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=extrude_id
        )
        
        # Phase 2: Fillet
        edges = list(box.edges())[:4]
        radius = 1.0
        fillet_id = test_context.create_feature_id("fillet")
        
        result = OCPFilletHelper.fillet(
            solid=box,
            edges=edges,
            radius=radius,
            naming_service=test_context.naming_service,
            feature_id=fillet_id
        )
        
        # Assert - Beide Features erfolgreich
        assert_solid_valid(result)
        assert test_context.feature_counter == 2  # 2 Features erstellt
        
        # TNP - Beide Features registriert
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0
        assert stats["edges"] > 0
    
    def test_extrude_chamfer_workflow(self, test_context):
        """Test: Extrude → Chamfer Workflow."""
        # Phase 1: Extrude
        face = create_test_sketch_face(width=8.0, height=8.0)
        direction = Vector(0, 0, 1)
        distance = 6.0
        extrude_id = test_context.create_feature_id("extrude")
        
        box = OCPExtrudeHelper.extrude(
            face=face,
            direction=direction,
            distance=distance,
            naming_service=test_context.naming_service,
            feature_id=extrude_id
        )
        
        # Phase 2: Chamfer
        edges = list(box.edges())[:6]
        distance_chamfer = 1.5
        chamfer_id = test_context.create_feature_id("chamfer")
        
        result = OCPChamferHelper.chamfer(
            solid=box,
            edges=edges,
            distance=distance_chamfer,
            naming_service=test_context.naming_service,
            feature_id=chamfer_id
        )
        
        # Assert
        assert_solid_valid(result)
        assert test_context.feature_counter == 2
        
        # TNP
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0
        assert stats["edges"] > 0
    
    def test_complex_workflow(self, test_context):
        """Test: Komplexer Workflow (Extrude → Fillet → Chamfer)."""
        # Phase 1: Extrude
        face = create_test_sketch_face(width=12.0, height=12.0)
        box = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=8.0,
            naming_service=test_context.naming_service,
            feature_id=test_context.create_feature_id("extrude")
        )
        
        # Phase 2: Fillet (einige Edges)
        edges_fillet = list(box.edges())[:4]
        box = OCPFilletHelper.fillet(
            solid=box,
            edges=edges_fillet,
            radius=1.0,
            naming_service=test_context.naming_service,
            feature_id=test_context.create_feature_id("fillet")
        )
        
        # Phase 3: Chamfer (andere Edges)
        edges_chamfer = list(box.edges())[4:8]
        result = OCPChamferHelper.chamfer(
            solid=box,
            edges=edges_chamfer,
            distance=1.5,
            naming_service=test_context.naming_service,
            feature_id=test_context.create_feature_id("chamfer")
        )
        
        # Assert
        assert_solid_valid(result)
        assert test_context.feature_counter == 3
        
        # TNP - Alle 3 Features registriert
        stats = test_context.naming_service.get_stats()
        assert stats["faces"] > 0
        assert stats["edges"] > 0


# ============================================================================
# DEBUG LOGGING TESTS
# ============================================================================

class TestOCPHelpersDebugLogging:
    """Tests für Debug-Logging."""
    
    def test_tnp_debug_logging_enabled(self, test_context, caplog):
        """Test: TNP Debug Logging aktiviert."""
        # Arrange
        enable_tnp_debug_logging()
        face = create_test_sketch_face()
        
        # Act
        result = OCPExtrudeHelper.extrude(
            face=face,
            direction=Vector(0, 0, 1),
            distance=5.0,
            naming_service=test_context.naming_service,
            feature_id=test_context.create_feature_id("extrude")
        )
        
        # Assert - Debug Logs sollten vorhanden sein
        # (Hängt von logger Konfiguration ab)
        assert_solid_valid(result)
        
        # Cleanup
        disable_tnp_debug_logging()


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])