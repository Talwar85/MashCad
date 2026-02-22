"""
Phase 9: BREP Persistenz Integration Tests

Tests für native BREP Persistenz mit TNP v4.1 ShapeID Persistenz.

Author: Claude (OCP-First Migration Phase 9)
Date: 2026-02-10
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from loguru import logger

from build123d import Box, Solid
from modeling.brep_persistence import BREPPersistence, BREPMetadata, get_global_persistence, HAS_OCP


# ============================================================================
# SKIP CONDITIONAL
# ============================================================================

# Test markers for pytest selection (combined with skipif)
pytestmark = [
    pytest.mark.skipif(not HAS_OCP, reason="OpenCASCADE (OCP) nicht verfügbar - Tests überspringen"),
    pytest.mark.kernel,
    pytest.mark.ocp,
    pytest.mark.fast,
]


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_brep_dir():
    """Temporäres Verzeichnis für BREP Tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def brep_persistence(temp_brep_dir):
    """BREPPersistence mit temporärem Verzeichnis."""
    return BREPPersistence(base_path=temp_brep_dir)


@pytest.fixture
def sample_solid():
    """Einfache Box als Test-Solid."""
    return Box(10, 10, 10)


@pytest.fixture
def sample_metadata():
    """Beispiel Metadaten."""
    return BREPMetadata(
        shape_id="test_shape_123",
        feature_id="extrude_feature_1",
        operation_type="extrude",
        shape_type="Solid",
        parameters={"distance": 10.0, "sketch_id": "sketch_1"}
    )


# ============================================================================
# METADATA TESTS
# ============================================================================

class TestBREPMetadata:
    """Tests für BREPMetadata."""

    def test_metadata_creation(self):
        """Test Metadaten Erstellung."""
        metadata = BREPMetadata(
            shape_id="test_id",
            feature_id="feature_1",
            operation_type="extrude",
            shape_type="Solid"
        )

        assert metadata.shape_id == "test_id"
        assert metadata.feature_id == "feature_1"
        assert metadata.operation_type == "extrude"
        assert metadata.shape_type == "Solid"
        assert metadata.version == "1.0"

    def test_metadata_to_dict(self):
        """Test Metadaten zu Dict Konvertierung."""
        metadata = BREPMetadata(
            shape_id="test_id",
            feature_id="feature_1",
            operation_type="fillet",
            shape_type="Solid",
            parameters={"radius": 5.0}
        )

        data = metadata.to_dict()

        assert data["shape_id"] == "test_id"
        assert data["feature_id"] == "feature_1"
        assert data["operation_type"] == "fillet"
        assert data["parameters"]["radius"] == 5.0

    def test_metadata_from_dict(self):
        """Test Metadaten aus Dict."""
        data = {
            "shape_id": "test_id",
            "feature_id": "feature_1",
            "operation_type": "shell",
            "shape_type": "Solid",
            "version": "1.0",
            "timestamp": "2026-02-10T12:00:00",
            "parameters": {"thickness": 2.0}
        }

        metadata = BREPMetadata.from_dict(data)

        assert metadata.shape_id == "test_id"
        assert metadata.parameters["thickness"] == 2.0


# ============================================================================
# SAVE SHAPE TESTS
# ============================================================================

class TestSaveShape:
    """Tests für Speichern von Shapes."""

    def test_save_shape_creates_files(self, brep_persistence, sample_solid, sample_metadata):
        """Test dass Speichern .brep und .meta.json Dateien erstellt."""
        brep_persistence.save_shape(sample_solid, sample_metadata)

        # Prüfe dass beide Dateien existieren
        assert brep_persistence._get_brep_path(sample_metadata.shape_id).exists()
        assert brep_persistence._get_meta_path(sample_metadata.shape_id).exists()

    def test_save_shape_metadata_content(self, brep_persistence, sample_solid, sample_metadata):
        """Test dass Metadaten korrekt gespeichert werden."""
        brep_persistence.save_shape(sample_solid, sample_metadata)

        loaded_metadata = brep_persistence.load_metadata(sample_metadata.shape_id)

        assert loaded_metadata.shape_id == sample_metadata.shape_id
        assert loaded_metadata.feature_id == sample_metadata.feature_id
        assert loaded_metadata.operation_type == sample_metadata.operation_type
        assert loaded_metadata.parameters == sample_metadata.parameters

    def test_save_shape_overwrites(self, brep_persistence, sample_solid, sample_metadata):
        """Test dass überschreiben funktioniert."""
        # Erster Save
        sample_metadata.parameters = {"distance": 5.0}
        brep_persistence.save_shape(sample_solid, sample_metadata)

        # Zweiter Save mit anderen Parametern
        sample_metadata.parameters = {"distance": 10.0}
        brep_persistence.save_shape(sample_solid, sample_metadata)

        loaded_metadata = brep_persistence.load_metadata(sample_metadata.shape_id)
        assert loaded_metadata.parameters["distance"] == 10.0


# ============================================================================
# LOAD SHAPE TESTS
# ============================================================================

class TestLoadShape:
    """Tests für Laden von Shapes."""

    def test_load_shape_after_save(self, brep_persistence, sample_solid, sample_metadata):
        """Test dass gespeichertes Shape korrekt geladen wird."""
        brep_persistence.save_shape(sample_solid, sample_metadata)

        loaded_shape = brep_persistence.load_shape(sample_metadata.shape_id)

        assert loaded_shape is not None
        # Shape wird zurückgegeben (kann Solid sein)
        assert hasattr(loaded_shape, 'wrapped')

    def test_load_shape_volume_preserved(self, brep_persistence, sample_solid, sample_metadata):
        """Test dass Volumen nach Speichern/Laden gleich bleibt."""
        original_volume = sample_solid.volume

        brep_persistence.save_shape(sample_solid, sample_metadata)
        loaded_shape = brep_persistence.load_shape(sample_metadata.shape_id)

        assert loaded_shape is not None
        # Für Volumen Zugriff casten wir zu Solid wenn nötig
        if hasattr(loaded_shape, 'volume'):
            loaded_volume = loaded_shape.volume
        else:
            from build123d import Solid
            loaded_volume = Solid(loaded_shape.wrapped).volume

        assert abs(loaded_volume - original_volume) < 0.01

    def test_load_nonexistent_shape(self, brep_persistence):
        """Test dass Laden nicht existierender Shape None zurückgibt."""
        result = brep_persistence.load_shape("nonexistent_shape")
        assert result is None

    def test_load_metadata_nonexistent(self, brep_persistence):
        """Test dass Laden nicht existierender Metadaten None zurückgibt."""
        result = brep_persistence.load_metadata("nonexistent_shape")
        assert result is None


# ============================================================================
# DELETE SHAPE TESTS
# ============================================================================

class TestDeleteShape:
    """Tests für Löschen von Shapes."""

    def test_delete_shape_removes_files(self, brep_persistence, sample_solid, sample_metadata):
        """Test dass Löschen beide Dateien entfernt."""
        brep_persistence.save_shape(sample_solid, sample_metadata)

        assert brep_persistence._get_brep_path(sample_metadata.shape_id).exists()
        assert brep_persistence._get_meta_path(sample_metadata.shape_id).exists()

        brep_persistence.delete_shape(sample_metadata.shape_id)

        assert not brep_persistence._get_brep_path(sample_metadata.shape_id).exists()
        assert not brep_persistence._get_meta_path(sample_metadata.shape_id).exists()

    def test_delete_nonexistent_shape(self, brep_persistence):
        """Test dass Löschen nicht existierender Shape keinen Fehler wirft."""
        # Sollte keinen Fehler werfen
        brep_persistence.delete_shape("nonexistent_shape")


# ============================================================================
# LIST SHAPES TESTS
# ============================================================================

class TestListShapes:
    """Tests für Auflisten von Shapes."""

    def test_list_empty(self, brep_persistence):
        """Test dass leere Liste zurückgegeben wird wenn keine Shapes existieren."""
        shapes = brep_persistence.list_shapes()
        assert shapes == {}

    def test_list_single_shape(self, brep_persistence, sample_solid, sample_metadata):
        """Test Auflisten eines einzelnen Shapes."""
        brep_persistence.save_shape(sample_solid, sample_metadata)

        shapes = brep_persistence.list_shapes()

        assert len(shapes) == 1
        assert sample_metadata.shape_id in shapes
        assert shapes[sample_metadata.shape_id].operation_type == "extrude"

    def test_list_multiple_shapes(self, brep_persistence, sample_solid):
        """Test Auflisten mehrerer Shapes."""
        # Mehrere Shapes speichern
        for i in range(3):
            metadata = BREPMetadata(
                shape_id=f"shape_{i}",
                feature_id=f"feature_{i}",
                operation_type="extrude",
                shape_type="Solid"
            )
            brep_persistence.save_shape(sample_solid, metadata)

        shapes = brep_persistence.list_shapes()

        assert len(shapes) == 3
        assert "shape_0" in shapes
        assert "shape_1" in shapes
        assert "shape_2" in shapes


# ============================================================================
# STATS TESTS
# ============================================================================

class TestStats:
    """Tests für Statistiken."""

    def test_stats_empty(self, brep_persistence):
        """Test Stats für leere Persistenz."""
        stats = brep_persistence.get_stats()

        assert stats["count"] == 0
        assert stats["size_bytes"] == 0
        assert stats["operation_types"] == {}

    def test_stats_single_shape(self, brep_persistence, sample_solid, sample_metadata):
        """Test Stats nach Speichern eines Shapes."""
        brep_persistence.save_shape(sample_solid, sample_metadata)

        stats = brep_persistence.get_stats()

        assert stats["count"] == 1
        assert stats["size_bytes"] > 0
        assert "extrude" in stats["operation_types"]
        assert stats["operation_types"]["extrude"] == 1

    def test_stats_multiple_operations(self, brep_persistence, sample_solid):
        """Test Stats mit verschiedenen Operationstypen."""
        operations = ["extrude", "fillet", "shell", "hollow"]

        for op in operations:
            metadata = BREPMetadata(
                shape_id=f"shape_{op}",
                feature_id=f"feature_{op}",
                operation_type=op,
                shape_type="Solid"
            )
            brep_persistence.save_shape(sample_solid, metadata)

        stats = brep_persistence.get_stats()

        assert stats["count"] == 4
        for op in operations:
            assert stats["operation_types"][op] == 1


# ============================================================================
# CLEANUP TESTS
# ============================================================================

class TestCleanup:
    """Tests für Cleanup alter Dateien."""

    def test_cleanup_removes_expired(self, brep_persistence, sample_solid):
        """Test dass expired Shapes gelöscht werden."""
        # Shape mit alter Timestamp
        metadata = BREPMetadata(
            shape_id="old_shape",
            feature_id="feature_1",
            operation_type="extrude",
            shape_type="Solid",
            timestamp="2026-01-01T00:00:00"  # Sehr alt
        )
        brep_persistence.save_shape(sample_solid, metadata)

        # Die JSON-Metadaten direkt manipulieren um eine alte Timestamp zu setzen
        import json
        meta_path = brep_persistence._get_meta_path("old_shape")
        with open(meta_path, 'r') as f:
            data = json.load(f)
        data["timestamp"] = "2026-01-01T00:00:00"
        with open(meta_path, 'w') as f:
            json.dump(data, f)

        # Cleanup mit TTL = 1 Stunde (sollte den alten Shape löschen)
        deleted = brep_persistence.cleanup_expired(ttl_hours=1)

        assert deleted == 1
        assert brep_persistence.load_shape("old_shape") is None

    def test_cleanup_keeps_recent(self, brep_persistence, sample_solid):
        """Test dass aktuelle Shapes nicht gelöscht werden."""
        # Shape mit aktueller Timestamp
        metadata = BREPMetadata(
            shape_id="recent_shape",
            feature_id="feature_1",
            operation_type="extrude",
            shape_type="Solid"
        )
        brep_persistence.save_shape(sample_solid, metadata)

        # Cleanup mit TTL = 24 Stunden (sollte nichts löschen)
        deleted = brep_persistence.cleanup_expired(ttl_hours=24)

        assert deleted == 0
        assert brep_persistence.load_shape("recent_shape") is not None


# ============================================================================
# EXPORT TESTS
# ============================================================================

class TestExport:
    """Tests für Export Funktionen."""

    def test_export_json(self, brep_persistence, sample_solid, temp_brep_dir):
        """Test JSON Export."""
        metadata = BREPMetadata(
            shape_id="export_test",
            feature_id="feature_1",
            operation_type="extrude",
            shape_type="Solid"
        )
        brep_persistence.save_shape(sample_solid, metadata)

        output_path = temp_brep_dir / "export.json"
        brep_persistence.export_shapes(output_path, format="json")

        assert output_path.exists()

        # Inhalt prüfen
        import json
        with open(output_path, 'r') as f:
            data = json.load(f)

        assert data["count"] == 1
        assert "export_test" in data["shapes"]


# ============================================================================
# GLOBAL PERSISTENCE TESTS
# ============================================================================

class TestGlobalPersistence:
    """Tests für globale Persistence Instance."""

    def test_get_global_persistence_singleton(self, temp_brep_dir):
        """Test dass get_global_persistence() Singleton zurückgibt."""
        from modeling.brep_persistence import set_global_persistence

        # Custom persistence setzen
        custom = BREPPersistence(base_path=temp_brep_dir)
        set_global_persistence(custom)

        result = get_global_persistence()

        assert result is custom

    def test_get_global_persistence_default(self):
        """Test dass Default Instance erstellt wird."""
        from modeling.brep_persistence import set_global_persistence, _global_persistence

        # Reset global
        import modeling.brep_persistence
        modeling.brep_persistence._global_persistence = None

        result = get_global_persistence()

        assert result is not None
        assert isinstance(result, BREPPersistence)


# ============================================================================
# FEATURE FLAG TESTS
# ============================================================================

class TestFeatureFlags:
    """Tests für Feature Flags."""

    def test_ocp_brep_persistence_flag_exists(self):
        """Test dass ocp_brep_persistence Flag existiert."""
        from config.feature_flags import is_enabled

        # Flag sollte existieren
        result = is_enabled("ocp_brep_persistence")
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
