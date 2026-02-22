"""
Phase 2: OCP-First ExtrudeFeature Integration Tests

Tests für die Feature-Flag-basierte Umschaltung zwischen
OCP-First (OCPExtrudeHelper) und Legacy Pfad.

Author: Claude (OCP-First Migration Phase 2)
Date: 2026-02-10
"""

import pytest
from loguru import logger
from shapely.geometry import Polygon

from build123d import Solid, Face, Vector, Part
from modeling import Body, ExtrudeFeature, Sketch
from modeling.ocp_helpers import OCPExtrudeHelper, HAS_OCP

# Import test utilities direkt
import sys
from pathlib import Path
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

from ocp_test_utils import (
    OCPTestContext,
    create_test_box,
    create_test_sketch_face,
    assert_solid_valid,
    assert_tnp_registered,
)
from config.feature_flags import is_enabled, set_flag, get_all_flags

# Test markers for pytest selection
pytestmark = [pytest.mark.kernel, pytest.mark.ocp, pytest.mark.fast]


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


@pytest.fixture
def document_with_tnp(test_context):
    """Document mit TNP Service."""
    from modeling import Document
    doc = Document("TestDoc")
    # TNP Service sollte bereits in Document initialisiert sein
    return doc


# ============================================================================
# FLAG INTEGRATION TESTS
# ============================================================================

class TestExtrudeFlagIntegration:
    """Tests für Feature-Flag-Integration in ExtrudeFeature."""

    def test_legacy_path_with_flag_false(self, document_with_tnp):
        """Test: Legacy Pfad wird verwendet wenn ocp_first_extrude=False."""
        # Arrange
        set_flag("ocp_first_extrude", False)
        body = Body("TestBody", document=document_with_tnp)

        # Face direkt erstellen (vereinfachter Test ohne Sketch-Solver)
        face = create_test_sketch_face(width=10.0, height=10.0)

        # Plane-Info setzen (für Push/Pull ohne Sketch)
        feature = ExtrudeFeature(
            distance=5.0,
            direction=1,
            operation="New Body"
        )
        feature.face_brep = None  # Kein BREP, nutzen precalculated_polys
        # Polygon für Extrude vorbereiten
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)

        body.add_feature(feature, rebuild=False)

        # Act
        result = body._compute_extrude_part(feature)

        # Assert
        assert result is not None, "Legacy Pfad sollte ein Ergebnis liefern"
        assert isinstance(result, (Solid, Part)), "Ergebnis sollte ein Solid oder Part sein"

    def test_ocp_first_path_with_flag_true(self, document_with_tnp):
        """Test: OCP-First Pfad wird verwendet wenn ocp_first_extrude=True."""
        # Arrange
        set_flag("ocp_first_extrude", True)
        body = Body("TestBody", document=document_with_tnp)

        # Face direkt erstellen
        face = create_test_sketch_face(width=10.0, height=10.0)

        # Plane-Info setzen
        feature = ExtrudeFeature(
            distance=5.0,
            direction=1,
            operation="New Body"
        )
        feature.face_brep = None
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)

        body.add_feature(feature, rebuild=False)

        # Act
        result = body._compute_extrude_part(feature)

        # Assert
        assert result is not None, "OCP-First Pfad sollte ein Ergebnis liefern"
        assert isinstance(result, (Solid, Part)), "Ergebnis sollte ein Solid oder Part sein"

        # TNP Registration prüfen
        naming_service = document_with_tnp._shape_naming_service
        assert naming_service is not None, "TNP Service sollte verfügbar sein"
        # Prüfen dass Shapes registriert wurden
        stats = naming_service.get_stats()
        assert stats['faces'] > 0, "TNP: Faces sollten registriert sein"

    def test_feature_id_generation(self, document_with_tnp):
        """Test: Feature-ID wird automatisch generiert wenn nicht vorhanden."""
        # Arrange
        set_flag("ocp_first_extrude", True)
        body = Body("TestBody", document=document_with_tnp)

        face = create_test_sketch_face(width=10.0, height=10.0)

        feature = ExtrudeFeature(
            distance=5.0,
        )
        feature.face_brep = None
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        # Keine ID gesetzt
        feature.id = None

        # Act
        body._compute_extrude_part(feature)

        # Assert
        assert feature.id is not None, "Feature-ID sollte generiert worden sein"
        assert len(feature.id) > 0, "Feature-ID sollte nicht leer sein"

    def test_error_without_tnp_service(self):
        """Test: OCP-First Pfad wirft Fehler ohne TNP Service."""
        # Arrange
        set_flag("ocp_first_extrude", True)
        body = Body("TestBody", document=None)  # Kein Document = Kein TNP Service

        feature = ExtrudeFeature(
            distance=5.0,
        )
        feature.face_brep = None
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)
        feature.id = "test_feature"

        # Act & Assert
        with pytest.raises(ValueError, match="TNP ShapeNamingService nicht verfügbar"):
            body._compute_extrude_part(feature)


# ============================================================================
# FULL WORKFLOW TESTS
# ============================================================================

class TestExtrudeWorkflow:
    """Tests für vollständige Extrude Workflows."""

    def test_full_extrude_workflow_legacy(self, document_with_tnp):
        """Test: Vollständiger Extrude Workflow mit Legacy Pfad."""
        # Arrange
        set_flag("ocp_first_extrude", False)
        body = Body("Box", document=document_with_tnp)

        feature = ExtrudeFeature(
            distance=10.0,
            direction=1,
            operation="New Body"
        )
        feature.face_brep = None
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)

        body.add_feature(feature, rebuild=False)

        # Act
        result = body._compute_extrude_part(feature)

        # Assert
        assert result is not None
        assert result.volume > 0, "Extrudierter Body sollte Volumen haben"

    def test_full_extrude_workflow_ocp_first(self, document_with_tnp):
        """Test: Vollständiger Extrude Workflow mit OCP-First Pfad."""
        # Arrange
        set_flag("ocp_first_extrude", True)
        body = Body("Box", document=document_with_tnp)

        feature = ExtrudeFeature(
            distance=10.0,
            direction=1,
            operation="New Body"
        )
        feature.face_brep = None
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)

        body.add_feature(feature, rebuild=False)

        # Act
        result = body._compute_extrude_part(feature)

        # Assert
        assert result is not None
        assert result.volume > 0, "Extrudierter Body sollte Volumen haben"

        # TNP Registration
        naming_service = document_with_tnp._shape_naming_service
        stats = naming_service.get_stats()
        assert stats['faces'] > 0, "TNP: Faces sollten registriert sein"


# ============================================================================
# PARAMETERIZED TESTS
# ============================================================================

class TestExtrudeParameters:
    """Tests für verschiedene Extrude-Parameter."""

    @pytest.mark.parametrize("distance,expected_volume", [
        (5.0, 500.0),   # 10x10x5 = 500
        (10.0, 1000.0), # 10x10x10 = 1000
        (20.0, 2000.0), # 10x10x20 = 2000
    ])
    def test_different_distances(self, document_with_tnp, distance, expected_volume):
        """Test: Verschiedene Extrusions-Distanzen."""
        # Arrange
        set_flag("ocp_first_extrude", True)
        body = Body("TestBody", document=document_with_tnp)

        feature = ExtrudeFeature(
            distance=distance,
            direction=1
        )
        feature.face_brep = None
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        feature.precalculated_polys = [poly]
        feature.plane_origin = (0, 0, 0)
        feature.plane_normal = (0, 0, 1)

        body.add_feature(feature, rebuild=False)

        # Act
        result = body._compute_extrude_part(feature)

        # Assert
        assert result is not None
        assert abs(result.volume - expected_volume) < 1.0, \
            f"Volumen sollte ~{expected_volume} sein, ist {result.volume}"


# ============================================================================
# COMPARISON TESTS
# ============================================================================

class TestLegacyVsOcpFirst:
    """Vergleichstests zwischen Legacy und OCP-First Pfad."""

    def test_both_paths_produce_similar_results(self, document_with_tnp):
        """Test: Legacy und OCP-First sollten ähnliche Ergebnisse liefern."""
        # Arrange
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])

        # Legacy Pfad
        set_flag("ocp_first_extrude", False)
        body_legacy = Body("LegacyBody", document=document_with_tnp)
        feature_legacy = ExtrudeFeature(distance=10.0)
        feature_legacy.face_brep = None
        feature_legacy.precalculated_polys = [poly]
        feature_legacy.plane_origin = (0, 0, 0)
        feature_legacy.plane_normal = (0, 0, 1)
        body_legacy.add_feature(feature_legacy, rebuild=False)
        result_legacy = body_legacy._compute_extrude_part(feature_legacy)

        # OCP-First Pfad
        set_flag("ocp_first_extrude", True)
        body_ocp = Body("OCPBody", document=document_with_tnp)
        feature_ocp = ExtrudeFeature(distance=10.0)
        feature_ocp.face_brep = None
        feature_ocp.precalculated_polys = [poly]
        feature_ocp.plane_origin = (0, 0, 0)
        feature_ocp.plane_normal = (0, 0, 1)
        body_ocp.add_feature(feature_ocp, rebuild=False)
        result_ocp = body_ocp._compute_extrude_part(feature_ocp)

        # Assert
        assert result_legacy is not None
        assert result_ocp is not None

        # Volumen sollte ähnlich sein (Toleranz für numerische Unterschiede)
        volume_diff = abs(result_legacy.volume - result_ocp.volume)
        assert volume_diff < 1.0, \
            f"Volumen-Differenz zu gross: Legacy={result_legacy.volume}, OCP={result_ocp.volume}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
