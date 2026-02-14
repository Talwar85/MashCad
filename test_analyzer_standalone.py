"""
Standalone Test für STL Feature Analyzer.
Testet nur Datenstrukturen ohne komplexe Imports.
"""

import sys
import os

# Kopiere die Dataclass-Definitionen hierher für isolierte Tests
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np


@dataclass
class PlaneInfo:
    """Detected base plane."""
    feature_type: str = "base_plane"
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    area: float = 0.0
    face_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0
    detection_method: str = "unknown"
    
    @property
    def is_valid(self) -> bool:
        return (
            self.area > 0 and
            np.linalg.norm(self.normal) > 0.99 and
            0.0 <= self.confidence <= 1.0
        )


@dataclass
class HoleInfo:
    """Detected hole with confidence."""
    feature_type: str = "hole"
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 0.0
    depth: float = 0.0
    axis: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    face_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0
    detection_method: str = "unknown"
    fallback_hints: Dict[str, Any] = field(default_factory=dict)
    validation_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def diameter(self) -> float:
        return self.radius * 2
    
    @property
    def is_valid(self) -> bool:
        return (
            self.radius > 0.01 and
            self.depth > 0.01 and
            0.5 < np.linalg.norm(self.axis) < 1.5 and
            0.0 <= self.confidence <= 1.0
        )


@dataclass
class PocketInfo:
    """Detected pocket with confidence."""
    feature_type: str = "pocket"
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    depth: float = 0.0
    boundary_face_indices: List[int] = field(default_factory=list)
    bottom_face_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0
    detection_method: str = "unknown"
    fallback_hints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FilletInfo:
    """Detected fillet with confidence."""
    feature_type: str = "fillet"
    edge_indices: List[int] = field(default_factory=list)
    radius: float = 0.0
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 0.0
    detection_method: str = "unknown"


@dataclass
class STLFeatureAnalysis:
    """Complete feature analysis result."""
    mesh_path: str = ""
    base_plane: Optional[PlaneInfo] = None
    holes: List[HoleInfo] = field(default_factory=list)
    pockets: List[PocketInfo] = field(default_factory=list)
    fillets: List[FilletInfo] = field(default_factory=list)
    overall_confidence: float = 0.0
    requires_user_review: bool = False
    duration_ms: float = 0.0
    
    def get_features_by_confidence(self, min_confidence: float = 0.7) -> Dict[str, List[Any]]:
        return {
            "holes": [h for h in self.holes if h.confidence >= min_confidence],
            "pockets": [p for p in self.pockets if p.confidence >= min_confidence],
            "fillets": [f for f in self.fillets if f.confidence >= min_confidence],
        }
    
    def get_low_confidence_features(self, threshold: float = 0.7) -> List[Tuple[str, Any]]:
        low_conf = []
        for hole in self.holes:
            if hole.confidence < threshold:
                low_conf.append(("hole", hole))
        for pocket in self.pockets:
            if pocket.confidence < threshold:
                low_conf.append(("pocket", pocket))
        for fillet in self.fillets:
            if fillet.confidence < threshold:
                low_conf.append(("fillet", fillet))
        return low_conf


# Tests
def test_plane_info():
    """Test PlaneInfo dataclass."""
    plane = PlaneInfo(
        origin=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        area=100.0,
        confidence=0.95,
        detection_method="largest_planar"
    )
    
    assert plane.is_valid
    assert plane.confidence == 0.95
    assert plane.feature_type == "base_plane"
    print("[OK] PlaneInfo test passed")


def test_hole_info():
    """Test HoleInfo dataclass."""
    hole = HoleInfo(
        center=(10.0, 20.0, 0.0),
        radius=5.0,
        depth=10.0,
        axis=(0.0, 0.0, 1.0),
        confidence=0.85,
        detection_method="cylinder_fit"
    )
    
    assert hole.is_valid
    assert hole.diameter == 10.0
    assert hole.confidence == 0.85
    print("[OK] HoleInfo test passed")


def test_hole_invalid():
    """Test invalid hole detection."""
    hole = HoleInfo(
        center=(0.0, 0.0, 0.0),
        radius=0.001,  # Too small
        depth=0.001,   # Too small
        confidence=0.3
    )
    
    assert not hole.is_valid
    print("[OK] Hole invalid test passed")


def test_analysis_summary():
    """Test STLFeatureAnalysis summary."""
    analysis = STLFeatureAnalysis(
        mesh_path="test.stl",
        base_plane=PlaneInfo(confidence=0.9),
        holes=[
            HoleInfo(confidence=0.85),
            HoleInfo(confidence=0.75),
            HoleInfo(confidence=0.95),
        ],
        overall_confidence=0.85
    )
    
    # Test get_features_by_confidence
    high_conf = analysis.get_features_by_confidence(0.8)
    assert len(high_conf["holes"]) == 2  # 0.85 and 0.95
    
    # Test get_low_confidence_features
    low_conf = analysis.get_low_confidence_features(0.8)
    assert len(low_conf) == 1  # Only 0.75
    
    print("[OK] Analysis summary test passed")


def test_analysis_needs_review():
    """Test requires_user_review flag."""
    analysis = STLFeatureAnalysis(
        mesh_path="test.stl",
        overall_confidence=0.6,  # Low confidence
        holes=[
            HoleInfo(confidence=0.5),  # Low confidence hole
        ]
    )
    
    # Manually set requires_review
    analysis.requires_user_review = (
        len(analysis.get_low_confidence_features(0.7)) > 0 or
        analysis.overall_confidence < 0.7
    )
    
    assert analysis.requires_user_review
    print("[OK] Analysis needs review test passed")


def test_pocket_info():
    """Test PocketInfo dataclass."""
    pocket = PocketInfo(
        center=(5.0, 5.0, 0.0),
        depth=3.0,
        confidence=0.7,
        detection_method="depression_detection"
    )
    
    assert pocket.feature_type == "pocket"
    assert pocket.confidence == 0.7
    print("[OK] PocketInfo test passed")


def test_fillet_info():
    """Test FilletInfo dataclass."""
    fillet = FilletInfo(
        edge_indices=[1, 2, 3],
        radius=2.0,
        confidence=0.8,
        detection_method="edge_curvature"
    )
    
    assert fillet.feature_type == "fillet"
    assert len(fillet.edge_indices) == 3
    print("[OK] FilletInfo test passed")


if __name__ == "__main__":
    print("Running STL Feature Analyzer Tests...")
    print("-" * 50)
    
    try:
        test_plane_info()
        test_hole_info()
        test_hole_invalid()
        test_analysis_summary()
        test_analysis_needs_review()
        test_pocket_info()
        test_fillet_info()
        
        print("-" * 50)
        print("All tests passed!")
        
    except AssertionError as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
