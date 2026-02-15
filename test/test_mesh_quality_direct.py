"""
Direkte Tests für Mesh Quality Checker.
Ohne Import durch sketching/__init__.py
"""

import sys
import os
import unittest
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

# Import directly from file to avoid sketching/__init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mesh_quality_checker",
    os.path.join(os.path.dirname(__file__), "../sketching/analysis/mesh_quality_checker.py")
)
mesh_quality_module = importlib.util.module_from_spec(spec)
sys.modules["mesh_quality_checker"] = mesh_quality_module
spec.loader.exec_module(mesh_quality_module)

MeshQualityChecker = mesh_quality_module.MeshQualityChecker
MeshQualityReport = mesh_quality_module.MeshQualityReport
check_mesh_quality = mesh_quality_module.check_mesh_quality

# Check PyVista
try:
    import pyvista as pv
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False


@unittest.skipUnless(PYVISTA_AVAILABLE, "PyVista nicht verfügbar")
class TestMeshQualityChecker(unittest.TestCase):
    """Tests für MeshQualityChecker."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.checker = MeshQualityChecker()
    
    def test_create_simple_cube(self):
        """Erstellt ein einfaches Test-Cube."""
        mesh = pv.Cube()
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            self.assertTrue(report.is_valid)
            self.assertEqual(report.recommended_action, "proceed")
            self.assertTrue(report.is_watertight)
            self.assertGreater(report.face_count, 0)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_watertight_detection(self):
        """Test watertight detection."""
        mesh = pv.Cube()
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            self.assertTrue(report.is_watertight)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_bounding_box(self):
        """Test bounding box calculation."""
        mesh = pv.Cube(x_length=10, y_length=20, z_length=30)
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            bbox = report.bounding_box_size
            self.assertAlmostEqual(bbox[0], 10.0, delta=0.1)
            self.assertAlmostEqual(bbox[1], 20.0, delta=0.1)
            self.assertAlmostEqual(bbox[2], 30.0, delta=0.1)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_v1_stl_if_available(self):
        """Test mit V1.stl wenn verfügbar."""
        v1_path = os.path.join(os.path.dirname(__file__), "../stl/V1.stl")
        
        if not os.path.exists(v1_path):
            self.skipTest("V1.stl nicht gefunden")
        
        report = self.checker.check(v1_path)
        
        self.assertTrue(report.is_valid)
        self.assertIn(report.recommended_action, ["proceed", "repair", "decimate"])
        self.assertGreater(report.face_count, 0)
        
        print(f"\nV1.stl Analysis:")
        print(f"  Faces: {report.face_count}")
        print(f"  Watertight: {report.is_watertight}")
        print(f"  Action: {report.recommended_action}")
        print(f"  Warnings: {report.warnings}")


class TestMeshQualityReport(unittest.TestCase):
    """Tests für MeshQualityReport Dataclass."""
    
    def test_basic_report(self):
        """Test basic report creation."""
        report = MeshQualityReport()
        report.face_count = 100
        report.vertex_count = 50
        report.is_watertight = True
        
        self.assertTrue(report.is_valid)
    
    def test_invalid_report(self):
        """Test invalid report detection."""
        report = MeshQualityReport()
        report.has_nan_vertices = True
        report.recommended_action = "reject"
        
        self.assertFalse(report.is_valid)
    
    def test_bounding_box_calculation(self):
        """Test bounding box size calculation."""
        report = MeshQualityReport()
        report.bounds = ((0, 0, 0), (10, 20, 30))
        
        size = report.bounding_box_size
        self.assertEqual(size, (10, 20, 30))


if __name__ == "__main__":
    unittest.main(verbosity=2)
