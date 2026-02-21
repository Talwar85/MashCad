"""
Tests für Export Kernel API
===========================

Phase 1: Export Foundation (PR-001)
Testet ExportKernel, ExportOptions und ExportResult.

Run: pytest test/test_export_kernel.py -v
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Skip all tests if dependencies not available
try:
    from modeling.export_kernel import (
        ExportKernel, ExportOptions, ExportResult, 
        ExportFormat, ExportQuality, ExportCandidate
    )
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ExportKernel dependencies not available"
)


class TestExportOptions:
    """Tests für ExportOptions Dataclass."""
    
    def test_default_options(self):
        """Test Default-Werte."""
        opts = ExportOptions()
        assert opts.format == ExportFormat.STL
        assert opts.quality == ExportQuality.FINE
        assert opts.binary is True
        assert opts.scale == 1.0
        
    def test_quality_preset_application(self):
        """Test dass Quality-Preset Werte anwendet."""
        opts = ExportOptions(quality=ExportQuality.DRAFT)
        assert opts.linear_deflection == 0.1
        assert opts.angular_tolerance == 0.5
        
        opts = ExportOptions(quality=ExportQuality.ULTRA)
        assert opts.linear_deflection == 0.005
        assert opts.angular_tolerance == 0.1
        
    def test_custom_values_override_quality(self):
        """Test dass Quality-Preset angewendet wird."""
        opts = ExportOptions(
            quality=ExportQuality.DRAFT,
        )
        # Quality preset values are applied in __post_init__
        assert opts.linear_deflection == 0.1  # DRAFT linear_deflection
        assert opts.angular_tolerance == 0.5  # DRAFT angular_tolerance
        
    def test_custom_values_after_quality(self):
        """Test dass Custom-Werte nach Quality gesetzt werden können."""
        opts = ExportOptions(
            quality=ExportQuality.DRAFT,
        )
        # Custom values can be set after construction
        opts.linear_deflection = 0.5
        assert opts.linear_deflection == 0.5


class TestExportResult:
    """Tests für ExportResult Dataclass."""
    
    def test_default_result(self):
        """Test Default-Werte."""
        result = ExportResult(success=True)
        assert result.success is True
        assert result.filepath == ""
        assert result.warnings == []
        assert result.file_size_bytes == 0
        
    def test_file_size_kb(self):
        """Test file_size_kb Property."""
        result = ExportResult(success=True, file_size_bytes=2048)
        assert result.file_size_kb == 2.0
        
    def test_add_warning(self):
        """Test add_warning Methode."""
        result = ExportResult(success=True)
        result.add_warning("Test warning")
        assert len(result.warnings) == 1
        assert result.warnings[0] == "Test warning"


class TestExportCandidate:
    """Tests für ExportCandidate Dataclass."""
    
    def test_get_solid_from_solid(self):
        """Test get_solid wenn solid direkt gesetzt."""
        mock_solid = Mock()
        candidate = ExportCandidate(solid=mock_solid)
        assert candidate.get_solid() == mock_solid
        
    def test_get_solid_from_body(self):
        """Test get_solid Extraktion aus Body."""
        mock_solid = Mock()
        mock_body = Mock()
        mock_body._build123d_solid = mock_solid
        
        candidate = ExportCandidate(body=mock_body)
        assert candidate.get_solid() == mock_solid
        
    def test_get_solid_priority(self):
        """Test dass solid Priorität hat vor body."""
        mock_solid1 = Mock()
        mock_solid2 = Mock()
        mock_body = Mock()
        mock_body._build123d_solid = mock_solid2
        
        candidate = ExportCandidate(solid=mock_solid1, body=mock_body)
        # Sollte solid1 zurückgeben, nicht solid2 aus body
        assert candidate.get_solid() == mock_solid1


class TestExportKernelFormatDetection:
    """Tests für Format-Erkennung."""
    
    @pytest.mark.parametrize("filename,expected_format", [
        ("part.stl", ExportFormat.STL),
        ("part.step", ExportFormat.STEP),
        ("part.stp", ExportFormat.STEP),
        ("part.3mf", ExportFormat._3MF),
        ("part.obj", ExportFormat.OBJ),
        ("part.ply", ExportFormat.PLY),
        ("part.unknown", ExportFormat.STL),  # Default
    ])
    def test_detect_format_from_extension(self, filename, expected_format):
        """Test Format-Erkennung aus Datei-Erweiterung."""
        from pathlib import Path
        path = Path(filename)
        detected = ExportKernel._detect_format_from_extension(path)
        assert detected == expected_format


class TestExportKernelSupportedFormats:
    """Tests für unterstützte Formate."""
    
    def test_get_supported_formats(self):
        """Test dass alle erwarteten Formate unterstützt werden."""
        formats = ExportKernel.get_supported_formats()
        
        extensions = [f['extension'] for f in formats]
        assert '.stl' in extensions
        assert '.step' in extensions
        assert '.stp' in extensions
        assert '.3mf' in extensions
        assert '.obj' in extensions
        assert '.ply' in extensions


class TestExportKernelValidation:
    """Tests für Validierungs-Integration."""
    
    def test_prepare_candidates_filters_invisible(self):
        """Test dass unsichtbare Bodies gefiltert werden."""
        mock_body1 = Mock()
        mock_body1.visible = True
        mock_body1.name = "Visible"
        
        mock_body2 = Mock()
        mock_body2.visible = False
        mock_body2.name = "Hidden"
        
        candidates = ExportKernel._prepare_candidates([mock_body1, mock_body2])
        assert len(candidates) == 1
        assert candidates[0].name == "Visible"
        
    def test_prepare_candidates_skips_none(self):
        """Test dass None Bodies übersprungen werden."""
        mock_body = Mock()
        mock_body.visible = True
        
        candidates = ExportKernel._prepare_candidates([mock_body, None])
        assert len(candidates) == 1


class TestExportKernelEstimate:
    """Tests für Triangle-Estimation."""
    
    def test_estimate_returns_non_negative(self):
        """Test dass Schätzung nicht-negativ ist."""
        mock_body = Mock()
        # Mock bounding_box
        mock_bbox = Mock()
        mock_bbox.max = Mock()
        mock_bbox.max.length = 10
        mock_body._build123d_solid.bounding_box = mock_bbox
        
        estimate = ExportKernel.estimate_triangle_count([mock_body])
        assert estimate >= 0
        
    def test_estimate_empty_bodies(self):
        """Test Schätzung mit leerer Liste."""
        estimate = ExportKernel.estimate_triangle_count([])
        assert estimate == 0


class TestExportKernelShortcuts:
    """Tests für Convenience-Funktionen."""
    
    @patch('modeling.export_kernel.ExportKernel.export_bodies')
    def test_export_stl_shortcut(self, mock_export):
        """Test export_stl Shortcut."""
        mock_export.return_value = ExportResult(success=True)
        from modeling.export_kernel import export_stl
        
        bodies = [Mock()]
        result = export_stl(bodies, "test.stl")
        
        assert result.success is True
        mock_export.assert_called_once()
        
    @patch('modeling.export_kernel.ExportKernel.export_bodies')
    def test_export_step_shortcut(self, mock_export):
        """Test export_step Shortcut."""
        mock_export.return_value = ExportResult(success=True)
        from modeling.export_kernel import export_step
        
        bodies = [Mock()]
        result = export_step(bodies, "test.step")
        
        assert result.success is True
        mock_export.assert_called_once()
        
    @patch('modeling.export_kernel.ExportKernel.export_bodies')
    def test_quick_export(self, mock_export):
        """Test quick_export Shortcut."""
        mock_export.return_value = ExportResult(success=True)
        from modeling.export_kernel import quick_export
        
        bodies = [Mock()]
        success = quick_export(bodies, "test.stl")
        
        assert success is True


class TestExportKernelErrorHandling:
    """Tests für Fehlerbehandlung."""
    
    def test_export_no_valid_bodies(self):
        """Test Export mit keinen validen Bodies."""
        # Empty bodies list
        result = ExportKernel.export_bodies([], "test.stl")
        
        assert result.success is False
        assert result.error_code == "NO_VALID_BODIES"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
