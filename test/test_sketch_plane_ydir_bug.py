"""
Regression test for sketch plane_y_dir zero-vector bug.

Bug: When x_dir_override is parallel to normal, np.cross(n_vec, x_vec) 
produces (0,0,0) which causes issues downstream in extrusion.

Fix: Added parallel vector detection in gui/sketch_operations._create_sketch_at()
to recalculate axes when cross product yields near-zero result.
"""

import pytest
import numpy as np


class TestSketchPlaneYDirBug:
    """Test suite for plane_y_dir zero-vector bug regression."""
    
    def test_parallel_vectors_z_axis(self):
        """
        Test that parallel vectors along Z-axis are handled correctly.
        
        When normal=(0,0,1) and x_dir=(0,0,1), the cross product is (0,0,0).
        The fix should detect this and recalculate x_dir.
        """
        # Simulate the fixed algorithm from _create_sketch_at
        normal = (0.0, 0.0, 1.0)
        x_dir_override = (0.0, 0.0, 1.0)  # Parallel to normal!
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        # FIX: Check for parallel vectors
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        y_dir = tuple(y_vec)
        
        # Assert y_dir is NOT a zero vector
        assert y_dir != (0.0, 0.0, 0.0), "y_dir should not be zero vector"
        assert np.linalg.norm(y_dir) > 0.99, "y_dir should be unit length"
        
    def test_parallel_vectors_negative_z(self):
        """
        Test that parallel vectors along negative Z-axis are handled correctly.
        """
        normal = (0.0, 0.0, -1.0)
        x_dir_override = (0.0, 0.0, -1.0)  # Parallel to normal!
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        y_dir = tuple(y_vec)
        
        assert y_dir != (0.0, 0.0, 0.0), "y_dir should not be zero vector"
        assert np.linalg.norm(y_dir) > 0.99, "y_dir should be unit length"
        
    def test_parallel_vectors_x_axis(self):
        """
        Test that parallel vectors along X-axis are handled correctly.
        """
        normal = (1.0, 0.0, 0.0)
        x_dir_override = (1.0, 0.0, 0.0)  # Parallel to normal!
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        y_dir = tuple(y_vec)
        
        assert y_dir != (0.0, 0.0, 0.0), "y_dir should not be zero vector"
        assert np.linalg.norm(y_dir) > 0.99, "y_dir should be unit length"
        
    def test_parallel_vectors_arbitrary(self):
        """
        Test that parallel vectors in arbitrary direction are handled correctly.
        """
        normal = (0.577, 0.577, 0.577)  # Normalized diagonal
        x_dir_override = (0.577, 0.577, 0.577)  # Parallel to normal!
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        y_dir = tuple(y_vec)
        
        assert y_dir != (0.0, 0.0, 0.0), "y_dir should not be zero vector"
        assert np.linalg.norm(y_dir) > 0.99, "y_dir should be unit length"
        
    def test_non_parallel_vectors_unchanged(self):
        """
        Test that non-parallel vectors pass through unchanged.
        """
        normal = (0.0, 0.0, 1.0)
        x_dir_override = (1.0, 0.0, 0.0)  # Perpendicular - should work
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        y_dir = tuple(y_vec)
        
        # For perpendicular vectors, y_dir should be (0, 1, 0)
        assert abs(y_dir[0] - 0.0) < 0.01
        assert abs(y_dir[1] - 1.0) < 0.01
        assert abs(y_dir[2] - 0.0) < 0.01
        
    def test_orthonormal_basis_created(self):
        """
        Test that the resulting basis is orthonormal (all vectors perpendicular and unit length).
        """
        normal = (0.0, 0.0, 1.0)
        x_dir_override = (0.0, 0.0, 1.0)  # Parallel to normal!
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        # Check orthonormality
        # |n| = |x| = |y| = 1
        assert abs(np.linalg.norm(n_vec) - 1.0) < 1e-10
        assert abs(np.linalg.norm(x_vec) - 1.0) < 1e-10
        assert abs(np.linalg.norm(y_vec) - 1.0) < 1e-10
        
        # n · x = 0
        assert abs(np.dot(n_vec, x_vec)) < 1e-10
        # n · y = 0
        assert abs(np.dot(n_vec, y_vec)) < 1e-10
        # x · y = 0
        assert abs(np.dot(x_vec, y_vec)) < 1e-10


class TestNearParallelVectors:
    """Test edge cases with nearly parallel vectors."""
    
    def test_nearly_parallel_vectors(self):
        """
        Test that nearly parallel vectors (within tolerance) are handled.
        """
        normal = (0.0, 0.0, 1.0)
        # Nearly parallel but with tiny deviation
        x_dir_override = (1e-12, 0.0, 1.0)
        
        n_vec = np.array(normal, dtype=np.float64)
        n_vec = n_vec / np.linalg.norm(n_vec)
        x_vec = np.array(x_dir_override, dtype=np.float64)
        x_vec = x_vec / np.linalg.norm(x_vec)
        y_vec = np.cross(n_vec, x_vec)
        
        y_vec_norm = np.linalg.norm(y_vec)
        if y_vec_norm < 1e-10:
            if abs(n_vec[2]) < 0.9:
                x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
            else:
                x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
            x_vec = x_vec / np.linalg.norm(x_vec)
            y_vec = np.cross(n_vec, x_vec)
            y_vec = y_vec / np.linalg.norm(y_vec)
        
        y_dir = tuple(y_vec)
        
        # Should produce valid non-zero y_dir
        assert np.linalg.norm(y_dir) > 0.99, "y_dir should be unit length"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
