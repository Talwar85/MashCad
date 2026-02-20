"""
Tests für 3MF Export Implementation
====================================

PR-001: 3MF Export Implementation
Testet die 3MF Export-Funktionalität des ExportKernels.

Run: pytest test/test_export_3mf.py -v
"""

import pytest
import tempfile
import zipfile
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from xml.etree import ElementTree as ET

# Skip all tests if dependencies not available
try:
    from modeling.export_kernel import (
        ExportKernel, ExportOptions, ExportResult,
        ExportFormat, ExportQuality, ExportCandidate,
        export_3mf
    )
    from config.feature_flags import is_enabled
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ExportKernel dependencies not available"
)


class Test3MFFeatureFlag:
    """Tests für 3MF Feature Flag."""
    
    def test_3mf_feature_flag_enabled(self):
        """Test dass export_3mf Feature Flag aktiviert ist."""
        assert is_enabled("export_3mf"), "export_3mf feature flag should be enabled"


class Test3MFFileStructure:
    """Tests für 3MF Datei-Struktur."""
    
    def test_3mf_is_valid_zip(self):
        """Test dass 3MF Datei ein gültiges ZIP-Archiv ist."""
        # Mock solid mit einfacher Geometrie
        mock_solid = Mock()
        
        # Mock CADTessellator - patch where it's imported (in cad_tessellator module)
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],  # vertices
                [(0, 1, 2)]  # triangles
            )
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "test.3mf"
                options = ExportOptions(format=ExportFormat._3MF)
                
                result = ExportKernel.export_bodies([mock_body], filepath, options)
                
                assert result.success, f"Export failed: {result.error_message}"
                assert filepath.exists()
                
                # Prüfe ob es ein gültiges ZIP ist
                assert zipfile.is_zipfile(filepath)
    
    def test_3mf_contains_required_files(self):
        """Test dass 3MF alle erforderlichen Dateien enthält."""
        mock_solid = Mock()
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
                [(0, 1, 2), (0, 2, 3)]
            )
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "test.3mf"
                options = ExportOptions(format=ExportFormat._3MF)
                
                result = ExportKernel.export_bodies([mock_body], filepath, options)
                assert result.success
                
                with zipfile.ZipFile(filepath, 'r') as zf:
                    names = zf.namelist()
                    
                    # Erforderliche Dateien laut 3MF Spec
                    assert '[Content_Types].xml' in names
                    assert '_rels/.rels' in names
                    assert '3D/3dmodel.model' in names
    
    def test_3mf_content_types_xml(self):
        """Test [Content_Types].xml Struktur."""
        mock_solid = Mock()
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                [(0, 1, 2)]
            )
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "test.3mf"
                result = ExportKernel.export_bodies([mock_body], filepath, ExportOptions(format=ExportFormat._3MF))
                assert result.success
                
                with zipfile.ZipFile(filepath, 'r') as zf:
                    content = zf.read('[Content_Types].xml')
                    root = ET.fromstring(content)
                    
                    # Prüfe Required Content Types
                    types = {t.get('Extension'): t.get('ContentType') for t in root.findall('{http://schemas.openxmlformats.org/package/2006/content-types}Default')}
                    
                    assert 'rels' in types
                    assert 'model' in types
    
    def test_3mf_model_xml_structure(self):
        """Test 3D/3dmodel.model XML Struktur."""
        mock_solid = Mock()
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (
                [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)],
                [(0, 1, 2)]
            )
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "test.3mf"
                result = ExportKernel.export_bodies([mock_body], filepath, ExportOptions(format=ExportFormat._3MF))
                assert result.success
                
                with zipfile.ZipFile(filepath, 'r') as zf:
                    content = zf.read('3D/3dmodel.model')
                    root = ET.fromstring(content)
                    
                    # Prüfe root element (mit Namespace)
                    ns = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
                    assert root.tag == ns + 'model' or root.tag == 'model'
                    assert root.get('unit') == 'millimeter'
                    
                    # Prüfe resources/object/mesh Struktur
                    resources = root.find(ns + 'resources') or root.find('resources')
                    assert resources is not None
                    
                    obj = resources.find(ns + 'object') or resources.find('object')
                    assert obj is not None
                    assert obj.get('type') == 'model'
                    
                    mesh = obj.find(ns + 'mesh') or obj.find('mesh')
                    assert mesh is not None
                    
                    vertices = mesh.find(ns + 'vertices') or mesh.find('vertices')
                    assert vertices is not None
                    vertex_list = vertices.findall(ns + 'vertex') or vertices.findall('vertex')
                    assert len(vertex_list) == 3
                    
                    triangles = mesh.find(ns + 'triangles') or mesh.find('triangles')
                    assert triangles is not None
                    triangle_list = triangles.findall(ns + 'triangle') or triangles.findall('triangle')
                    assert len(triangle_list) == 1
                    
                    # Prüfe build/item
                    build = root.find(ns + 'build') or root.find('build')
                    assert build is not None
                    
                    # Item search with namespace
                    item = build.find(ns + 'item')
                    if item is None:
                        # Try without namespace (direct child)
                        for child in build:
                            if child.tag.endswith('item') or child.tag == 'item':
                                item = child
                                break
                    assert item is not None, f"item not found in build. Build children: {[c.tag for c in build]}"
                    assert item.get('objectid') == '1'


class Test3MFExportWithGeometry:
    """Tests für 3MF Export mit verschiedener Geometrie."""
    
    def test_export_simple_box(self):
        """Test 3MF Export eines einfachen Quaders."""
        mock_solid = Mock()
        
        # Einfacher Quader (8 Vertices, 12 Triangles)
        vertices = [
            (0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),  # bottom
            (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)  # top
        ]
        triangles = [
            (0, 1, 2), (0, 2, 3),  # bottom
            (4, 6, 5), (4, 7, 6),  # top
            (0, 4, 5), (0, 5, 1),  # front
            (2, 6, 7), (2, 7, 3),  # back
            (0, 3, 7), (0, 7, 4),  # left
            (1, 5, 6), (1, 6, 2)   # right
        ]
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (vertices, triangles)
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "box.3mf"
                options = ExportOptions(format=ExportFormat._3MF)
                
                result = ExportKernel.export_bodies([mock_body], filepath, options)
                
                assert result.success
                assert result.triangle_count == 12
                assert result.body_count == 1
                assert filepath.exists()
    
    def test_export_multiple_bodies(self):
        """Test 3MF Export mehrerer Bodies."""
        vertices1 = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        triangles1 = [(0, 1, 2)]
        
        vertices2 = [(5, 0, 0), (6, 0, 0), (5, 1, 0)]
        triangles2 = [(0, 1, 2)]
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.side_effect = [
                (vertices1, triangles1),
                (vertices2, triangles2)
            ]
            
            bodies = []
            for i in range(2):
                mock_solid = Mock()
                mock_body = Mock()
                mock_body._build123d_solid = mock_solid
                mock_body.visible = True
                bodies.append(mock_body)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "multi.3mf"
                options = ExportOptions(format=ExportFormat._3MF)
                
                result = ExportKernel.export_bodies(bodies, filepath, options)
                
                assert result.success
                assert result.triangle_count == 2
                assert result.body_count == 2
    
    def test_export_with_scale(self):
        """Test 3MF Export mit Skalierung."""
        mock_solid = Mock()
        
        vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        triangles = [(0, 1, 2)]
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (vertices, triangles)
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "scaled.3mf"
                options = ExportOptions(format=ExportFormat._3MF, scale=2.0)
                
                result = ExportKernel.export_bodies([mock_body], filepath, options)
                
                assert result.success
                
                # Prüfe skalierte Vertices
                with zipfile.ZipFile(filepath, 'r') as zf:
                    content = zf.read('3D/3dmodel.model')
                    root = ET.fromstring(content)
                    
                    # Namespace-aware search
                    ns = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
                    vertices_elem = root.find('.//' + ns + 'vertices') or root.find('.//vertices')
                    assert vertices_elem is not None, "vertices element not found"
                    
                    vertex_list = vertices_elem.findall(ns + 'vertex') or vertices_elem.findall('vertex')
                    assert len(vertex_list) >= 2, "Expected at least 2 vertices"
                    
                    # Erster Vertex sollte (0, 0, 0) bleiben
                    assert float(vertex_list[0].get('x')) == 0.0
                    
                    # Zweiter Vertex sollte (2, 0, 0) sein (skaliert von 1)
                    assert float(vertex_list[1].get('x')) == 2.0


class Test3MFExportErrors:
    """Tests für 3MF Export Fehlerbehandlung."""
    
    def test_export_empty_bodies_list(self):
        """Test Export mit leerer Body-Liste."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty.3mf"
            options = ExportOptions(format=ExportFormat._3MF)
            
            result = ExportKernel.export_bodies([], filepath, options)
            
            assert not result.success
            assert result.error_code == "NO_VALID_BODIES"
    
    def test_export_no_valid_solids(self):
        """Test Export wenn keine gültigen Solids vorhanden (Body ohne solid)."""
        mock_body = Mock()
        mock_body._build123d_solid = None
        mock_body.visible = True
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "no_solid.3mf"
            options = ExportOptions(format=ExportFormat._3MF)
            
            result = ExportKernel.export_bodies([mock_body], filepath, options)
            
            # Wenn body visible ist aber kein solid hat, wird es gefiltert
            assert not result.success
            assert result.error_code in ["NO_VALID_BODIES", "NO_MESH_DATA"]
    
    def test_export_tessellation_failure(self):
        """Test Export wenn Tessellation fehlschlägt."""
        mock_solid = Mock()
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.side_effect = Exception("Tessellation error")
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "tess_fail.3mf"
                options = ExportOptions(format=ExportFormat._3MF)
                
                result = ExportKernel.export_bodies([mock_body], filepath, options)
                
                # Sollte fehlschlagen da keine Mesh-Daten
                assert not result.success
                assert result.error_code == "NO_MESH_DATA"


class Test3MFShortcutFunction:
    """Tests für export_3mf Shortcut Funktion."""
    
    def test_export_3mf_shortcut(self):
        """Test export_3mf() Convenience Funktion."""
        mock_solid = Mock()
        
        with patch('modeling.cad_tessellator.CADTessellator') as MockTessellator:
            MockTessellator.tessellate_for_export.return_value = (
                [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                [(0, 1, 2)]
            )
            
            mock_body = Mock()
            mock_body._build123d_solid = mock_solid
            mock_body.visible = True
            
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / "shortcut.3mf"
                
                result = export_3mf([mock_body], str(filepath))
                
                assert result.success
                assert result.format == ExportFormat._3MF


class Test3MFWithRealGeometry:
    """Integration Tests mit echter OCP Geometrie (falls verfügbar)."""
    
    @pytest.mark.skip(reason="Requires full build123d Shape with .wrapped attribute - tested in integration tests")
    def test_export_real_box(self):
        """Test 3MF Export mit echtem OCP Box-Solid."""
        # This test requires a real build123d Shape object with proper .wrapped attribute
        # Integration testing should be done with the full application
        pass


class Test3MFRoundTrip:
    """Tests für 3MF Round-Trip (Export + Import)."""
    
    @pytest.mark.skip(reason="3MF Import not yet implemented")
    def test_3mf_roundtrip(self):
        """Test Export und anschließender Import."""
        # TODO: Implementieren wenn 3MF Import verfügbar
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
