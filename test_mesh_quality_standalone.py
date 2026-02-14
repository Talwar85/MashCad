"""
Standalone Test für Mesh Quality Checker.
Ohne komplexe Import-Abhängigkeiten.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Teste nur die Datenklassen und Logik ohne PyVista
from dataclasses import dataclass, field
from typing import List, Tuple, Any

@dataclass
class MeshQualityReport:
    """Kopie für Standalone-Test."""
    mesh_path: str = ""
    is_watertight: bool = False
    face_count: int = 0
    vertex_count: int = 0
    edge_count: int = 0
    bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = field(
        default_factory=lambda: ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    )
    has_degenerate_faces: bool = False
    has_duplicate_vertices: bool = False
    has_nan_vertices: bool = False
    recommended_action: str = "proceed"
    warnings: List[str] = field(default_factory=list)
    repair_performed: bool = False
    repair_log: List[str] = field(default_factory=list)
    decimation_performed: bool = False
    original_face_count: int = 0

    @property
    def is_valid(self) -> bool:
        return (
            self.face_count > 0 and
            self.vertex_count > 0 and
            not self.has_nan_vertices and
            self.recommended_action != "reject"
        )
    
    @property
    def bounding_box_size(self) -> Tuple[float, float, float]:
        min_pt, max_pt = self.bounds
        return (
            max_pt[0] - min_pt[0],
            max_pt[1] - min_pt[1],
            max_pt[2] - min_pt[2]
        )


def test_report_basic():
    """Test basic report functionality."""
    report = MeshQualityReport()
    report.face_count = 100
    report.vertex_count = 50
    report.is_watertight = True
    
    assert report.is_valid
    assert report.recommended_action == "proceed"
    print("[OK] Basic report test passed")


def test_report_invalid():
    """Test invalid report detection."""
    report = MeshQualityReport()
    report.has_nan_vertices = True
    report.recommended_action = "reject"
    
    assert not report.is_valid
    print("[OK] Invalid report test passed")


def test_report_bounds():
    """Test bounding box calculation."""
    report = MeshQualityReport()
    report.bounds = ((0, 0, 0), (10, 20, 30))
    
    size = report.bounding_box_size
    assert size == (10, 20, 30)
    print("[OK] Bounds test passed")


def test_report_warnings():
    """Test warnings list."""
    report = MeshQualityReport()
    report.warnings.append("Test warning")
    report.warnings.append("Another warning")
    
    assert len(report.warnings) == 2
    print("[OK] Warnings test passed")


if __name__ == "__main__":
    print("Running Mesh Quality Report Tests...")
    print("-" * 40)
    
    try:
        test_report_basic()
        test_report_invalid()
        test_report_bounds()
        test_report_warnings()
        
        print("-" * 40)
        print("All tests passed!")
        
    except AssertionError as e:
        print(f"[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)
