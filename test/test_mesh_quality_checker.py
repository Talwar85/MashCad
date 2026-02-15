"""
Tests für Mesh Quality Checker.

Testet ohne GUI, nur Mesh-Validierung.
"""

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

# Skip tests if PyVista not available
try:
    import pyvista as pv
    PYVISTA_AVAILABLE = True
except ImportError:
    PYVISTA_AVAILABLE = False

from sketching.analysis.mesh_quality_checker import (
    MeshQualityChecker, MeshQualityReport, check_mesh_quality
)


@unittest.skipUnless(PYVISTA_AVAILABLE, "PyVista nicht verfügbar")
class TestMeshQualityChecker(unittest.TestCase):
    """Tests für MeshQualityChecker."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.checker = MeshQualityChecker()
        self.test_dir = Path(__file__).parent.parent / "stl"
    
    def test_pyvista_available(self):
        """Test dass PyVista erkannt wird."""
        self.assertTrue(self.checker.pyvista_available)
    
    def test_create_simple_cube_stl(self):
        """Erstellt ein einfaches Test-Cube STL."""
        # Create a simple cube mesh
        mesh = pv.Cube()
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            
            # Check it
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            self.assertTrue(report.is_valid)
            self.assertEqual(report.recommended_action, "proceed")
            self.assertTrue(report.is_watertight)
            self.assertGreater(report.face_count, 0)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_watertight_cube(self):
        """Test watertight detection on cube."""
        mesh = pv.Cube()
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            self.assertTrue(report.is_watertight)
            self.assertNotIn("nicht watertight", " ".join(report.warnings))
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_non_watertight_mesh(self):
        """Test detection of non-watertight mesh."""
        # Create an open surface (plane with some thickness)
        mesh = pv.Plane(i_resolution=5, j_resolution=5)
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            # Should detect as not watertight
            self.assertFalse(report.is_watertight)
            self.assertEqual(report.recommended_action, "repair")
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_degenerate_faces_detection(self):
        """Test detection of degenerate faces."""
        # Create a mesh with very small triangles
        points = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1e-15],  # Very close to first point - degenerate
        ])
        
        faces = np.array([
            3, 0, 1, 2,  # Normal triangle
            3, 0, 1, 3,  # Degenerate (points 0 and 3 are almost same)
        ])
        
        mesh = pv.PolyData(points, faces)
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = self.checker.check(temp_path, auto_repair=False, auto_decimate=False)
            
            # Should detect degenerate faces
            self.assertTrue(report.has_degenerate_faces or report.recommended_action == "repair")
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_auto_repair(self):
        """Test auto-repair functionality."""
        # Create mesh with duplicate points
        points = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 0],  # Duplicate
        ])
        
        faces = np.array([
            3, 0, 1, 2,
            3, 3, 1, 2,  # Uses duplicate point
        ])
        
        mesh = pv.PolyData(points, faces)
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            
            # Check without repair
            report_no_repair = self.checker.check(temp_path, auto_repair=False)
            
            # Check with repair
            report_with_repair = self.checker.check(temp_path, auto_repair=True)
            
            self.assertTrue(report_with_repair.repair_performed)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_decimation(self):
        """Test decimation for large meshes."""
        # Create a high-res sphere
        mesh = pv.Sphere(theta_resolution=100, phi_resolution=100)
        
        original_faces = mesh.n_faces
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            
            # Check with auto_decimate
            report = self.checker.check(temp_path, auto_decimate=True)
            
            # Should have decimated
            if original_faces > MeshQualityChecker.MAX_FACES_FOR_QUICK_ANALYSIS:
                self.assertTrue(report.decimation_performed)
                self.assertLess(report.face_count, original_faces)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_v1_stl_if_available(self):
        """Test mit V1.stl wenn verfügbar."""
        v1_path = self.test_dir / "V1.stl"
        
        if not v1_path.exists():
            self.skipTest("V1.stl nicht gefunden")
        
        report = self.checker.check(str(v1_path))
        
        # V1 sollte grundsätzlich valide sein
        self.assertTrue(report.is_valid)
        self.assertIn(report.recommended_action, ["proceed", "repair", "decimate"])
        self.assertGreater(report.face_count, 0)
        
        print(f"\nV1.stl Analysis:")
        print(f"  Faces: {report.face_count}")
        print(f"  Watertight: {report.is_watertight}")
        print(f"  Action: {report.recommended_action}")
        print(f"  Warnings: {report.warnings}")
    
    def test_tensionmeter_stl_if_available(self):
        """Test mit TensionMeter.stl wenn verfügbar."""
        tm_path = self.test_dir / "TensionMeter.stl"
        
        if not tm_path.exists():
            self.skipTest("TensionMeter.stl nicht gefunden")
        
        report = self.checker.check(str(tm_path))
        
        # Sollte valide sein (ggf. mit decimate)
        self.assertTrue(report.is_valid)
        
        print(f"\nTensionMeter.stl Analysis:")
        print(f"  Faces: {report.face_count}")
        print(f"  Watertight: {report.is_watertight}")
        print(f"  Action: {report.recommended_action}")
    
    def test_invalid_file(self):
        """Test mit nicht-existentem File."""
        report = self.checker.check("/nonexistent/file.stl")
        
        self.assertEqual(report.recommended_action, "reject")
        self.assertFalse(report.is_valid)
    
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
    
    def test_get_mesh_info_quick(self):
        """Test quick mesh info function."""
        mesh = pv.Cube()
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            info = self.checker.get_mesh_info(temp_path)
            
            self.assertTrue(info["loaded"])
            self.assertGreater(info["face_count"], 0)
            self.assertIsNotNone(info["bounds"])
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


@unittest.skipUnless(PYVISTA_AVAILABLE, "PyVista nicht verfügbar")
class TestConvenienceFunction(unittest.TestCase):
    """Test convenience function."""
    
    def test_check_mesh_quality(self):
        """Test convenience function."""
        mesh = pv.Cube()
        
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            mesh.save(temp_path)
            report = check_mesh_quality(temp_path)
            
            self.assertIsInstance(report, MeshQualityReport)
            self.assertTrue(report.is_valid)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
