"""
Phase 5: OCP-First Shell/Hollow Integration Tests

Tests für die OCP-First Helper (OCPShellHelper, OCPHollowHelper)
mit TNP Integration.

Author: Claude (OCP-First Migration Phase 5)
Date: 2026-02-10
"""

import pytest
from loguru import logger

from build123d import Solid, Face, Vector, Box
from modeling import Document
from modeling.ocp_helpers import (
    OCPShellHelper,
    OCPHollowHelper,
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
def box_solid(document_with_tnp):
    """Erstellt eine Box als Test-Solid."""
    box = Box(10, 10, 10)
    return box


# ============================================================================
# SHELL HELPER TESTS
# ============================================================================

class TestOCPShellHelper:
    """Tests für OCPShellHelper."""

    def test_shell_with_one_face(self, document_with_tnp, box_solid):
        """Test Shell mit einem entfernten Face (Top Face)."""
        feature_id = "shell_one_face"

        # Top Face entfernen
        faces = list(box_solid.faces())
        top_face = max(faces, key=lambda f: f.center().Z)

        result = OCPShellHelper.shell(
            solid=box_solid,
            faces_to_remove=[top_face],
            thickness=1.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)
        # Shell sollte weniger Volumen haben als Original
        assert result.volume < box_solid.volume
        # Aber immer noch Volumen haben (nicht leer)
        assert result.volume > 0

    def test_shell_with_multiple_faces(self, document_with_tnp, box_solid):
        """Test Shell mit mehreren entfernten Faces."""
        feature_id = "shell_multi_face"

        # Top und Front Face entfernen
        faces = list(box_solid.faces())
        top_face = max(faces, key=lambda f: f.center().Z)
        front_face = max(faces, key=lambda f: f.center().Y)

        result = OCPShellHelper.shell(
            solid=box_solid,
            faces_to_remove=[top_face, front_face],
            thickness=1.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)

    def test_shell_without_tnp_service(self, box_solid):
        """Test dass Shell ohne TNP Service fehlschlägt."""
        faces = list(box_solid.faces())
        top_face = max(faces, key=lambda f: f.center().Z)

        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPShellHelper.shell(
                solid=box_solid,
                faces_to_remove=[top_face],
                thickness=1.0,
                naming_service=None,
                feature_id="shell_no_tnp"
            )

    def test_shell_without_feature_id(self, document_with_tnp, box_solid):
        """Test dass Shell ohne feature_id fehlschlägt."""
        faces = list(box_solid.faces())
        top_face = max(faces, key=lambda f: f.center().Z)

        with pytest.raises(ValueError, match="feature_id ist Pflicht"):
            OCPShellHelper.shell(
                solid=box_solid,
                faces_to_remove=[top_face],
                thickness=1.0,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id=None
            )

    def test_shell_without_faces_error(self, document_with_tnp, box_solid):
        """Test dass Shell ohne leere Face-Liste fehlschlägt."""
        with pytest.raises(ValueError, match="mindestens 1 Face"):
            OCPShellHelper.shell(
                solid=box_solid,
                faces_to_remove=[],
                thickness=1.0,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id="shell_no_faces"
            )


# ============================================================================
# HOLLOW HELPER TESTS
# ============================================================================

class TestOCPHollowHelper:
    """Tests für OCPHollowHelper."""

    def test_hollow_creates_cavity(self, document_with_tnp, box_solid):
        """Test dass Hollow eine Cavität erstellt (Volumen reduziert)."""
        feature_id = "hollow_box"

        result = OCPHollowHelper.hollow(
            solid=box_solid,
            thickness=1.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        assert result is not None
        assert isinstance(result, Solid)
        # Hollow sollte weniger Volumen haben als Original
        assert result.volume < box_solid.volume
        # Aber immer noch Volumen haben (nicht leer)
        assert result.volume > 0

    def test_hollow_with_different_thickness(self, document_with_tnp, box_solid):
        """Test Hollow mit verschiedenen Wandstärken."""
        for thickness in [0.5, 1.0, 2.0]:
            feature_id = f"hollow_thickness_{thickness}"

            result = OCPHollowHelper.hollow(
                solid=box_solid,
                thickness=thickness,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id=feature_id
            )

            assert result is not None
            assert isinstance(result, Solid)
            # Dickere Wand = weniger Innenraum = weniger Volumen
            assert result.volume > 0

    def test_hollow_without_tnp_service(self, box_solid):
        """Test dass Hollow ohne TNP Service fehlschlägt."""
        with pytest.raises(ValueError, match="naming_service ist Pflicht"):
            OCPHollowHelper.hollow(
                solid=box_solid,
                thickness=1.0,
                naming_service=None,
                feature_id="hollow_no_tnp"
            )

    def test_hollow_without_feature_id(self, document_with_tnp, box_solid):
        """Test dass Hollow ohne feature_id fehlschlägt."""
        with pytest.raises(ValueError, match="feature_id ist Pflicht"):
            OCPHollowHelper.hollow(
                solid=box_solid,
                thickness=1.0,
                naming_service=document_with_tnp._shape_naming_service,
                feature_id=None
            )


# ============================================================================
# TNP REGISTRATION TESTS
# ============================================================================

class TestTNPRegistrationShellHollow:
    """Tests für TNP Registration bei Shell/Hollow."""

    def test_shell_tnp_registration(self, document_with_tnp, box_solid):
        """Test dass Shell Faces/Edges im TNP Service registriert."""
        feature_id = "shell_tnp"

        faces = list(box_solid.faces())
        top_face = max(faces, key=lambda f: f.center().Z)

        initial_stats = document_with_tnp._shape_naming_service.get_stats()

        OCPShellHelper.shell(
            solid=box_solid,
            faces_to_remove=[top_face],
            thickness=1.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id=feature_id
        )

        final_stats = document_with_tnp._shape_naming_service.get_stats()

        # Es sollten neue Faces und Edges registriert worden sein
        assert final_stats['faces'] > initial_stats['faces']
        assert final_stats['edges'] > initial_stats['edges']

    def test_hollow_tnp_registration(self, document_with_tnp, box_solid):
        """Test dass Hollow Faces/Edges im TNP Service registriert."""
        feature_id = "hollow_tnp"

        initial_stats = document_with_tnp._shape_naming_service.get_stats()

        OCPHollowHelper.hollow(
            solid=box_solid,
            thickness=1.0,
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

    def test_ocp_first_shell_flag(self):
        """Test dass ocp_first_shell Flag auf True ist."""
        assert is_enabled("ocp_first_shell") is True

    def test_ocp_first_hollow_flag(self):
        """Test dass ocp_first_hollow Flag auf True ist."""
        assert is_enabled("ocp_first_hollow") is True


# ============================================================================
# VOLUME VALIDATION TESTS
# ============================================================================

class TestVolumeValidation:
    """Tests für Volumen-Validierung bei Shell/Hollow."""

    def test_shell_reduces_volume_reasonably(self, document_with_tnp, box_solid):
        """Test dass Shell das Volumen vernünftig reduziert."""
        faces = list(box_solid.faces())
        top_face = max(faces, key=lambda f: f.center().Z)

        original_volume = box_solid.volume

        result = OCPShellHelper.shell(
            solid=box_solid,
            faces_to_remove=[top_face],
            thickness=1.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id="shell_volume_test"
        )

        # Shell sollte Volumen reduzieren, aber nicht auf 0
        assert result.volume < original_volume
        assert result.volume > original_volume * 0.3  # Mindestens 30% übrig

    def test_hollow_reduces_volume_reasonably(self, document_with_tnp, box_solid):
        """Test dass Hollow das Volumen vernünftig reduziert."""
        original_volume = box_solid.volume

        result = OCPHollowHelper.hollow(
            solid=box_solid,
            thickness=1.0,
            naming_service=document_with_tnp._shape_naming_service,
            feature_id="hollow_volume_test"
        )

        # Hollow sollte Volumen reduzieren, aber nicht auf 0
        assert result.volume < original_volume
        assert result.volume > original_volume * 0.3  # Mindestens 30% übrig


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
