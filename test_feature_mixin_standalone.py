"""
Standalone Test für STL Feature Mixin.
Testet Logik ohne PyVista-Rendering.
"""

import sys
import os

# Dataclass-Definitionen kopieren
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np


@dataclass
class FeatureColorScheme:
    """Color scheme for feature visualization."""
    base_plane_high: Tuple[int, int, int] = (0, 255, 0)
    base_plane_medium: Tuple[int, int, int] = (100, 255, 100)
    hole_high: Tuple[int, int, int] = (0, 100, 255)
    hole_medium: Tuple[int, int, int] = (100, 150, 255)
    hole_low: Tuple[int, int, int] = (150, 200, 255)
    pocket_high: Tuple[int, int, int] = (255, 255, 0)
    pocket_medium: Tuple[int, int, int] = (255, 200, 100)
    fillet_high: Tuple[int, int, int] = (255, 105, 180)
    uncertain: Tuple[int, int, int] = (255, 165, 0)
    
    opacity_high: float = 1.0
    opacity_medium: float = 0.8
    opacity_low: float = 0.6


@dataclass
class MockPlane:
    feature_type: str = "base_plane"
    face_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class MockHole:
    feature_type: str = "hole"
    face_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = 5.0


@dataclass
class MockPocket:
    feature_type: str = "pocket"
    boundary_face_indices: List[int] = field(default_factory=list)
    bottom_face_indices: List[int] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class MockAnalysis:
    base_plane: Optional[MockPlane] = None
    holes: List[MockHole] = field(default_factory=list)
    pockets: List[MockPocket] = field(default_factory=list)
    overall_confidence: float = 0.0
    requires_user_review: bool = False


class STLFeatureMixinLogic:
    """Logik-Test-Version des Mixins."""
    
    HIGH_CONFIDENCE = 0.9
    MEDIUM_CONFIDENCE = 0.7
    LOW_CONFIDENCE = 0.5
    
    def __init__(self):
        self._color_scheme = FeatureColorScheme()
        self._visible_feature_types = {
            "base_plane": True,
            "hole": True,
            "pocket": True,
            "fillet": True,
        }
    
    def _get_color_for_base_plane(self, confidence: float) -> Tuple[int, int, int]:
        """Get color for base plane based on confidence."""
        if confidence >= self.HIGH_CONFIDENCE:
            return self._color_scheme.base_plane_high
        else:
            return self._color_scheme.base_plane_medium
    
    def _get_color_for_hole(self, confidence: float) -> Tuple[int, int, int]:
        """Get color for hole based on confidence."""
        if confidence >= self.HIGH_CONFIDENCE:
            return self._color_scheme.hole_high
        elif confidence >= self.MEDIUM_CONFIDENCE:
            return self._color_scheme.hole_medium
        elif confidence >= self.LOW_CONFIDENCE:
            return self._color_scheme.hole_low
        else:
            return self._color_scheme.uncertain
    
    def get_legend_info(self) -> List[Dict]:
        """Get legend information."""
        scheme = self._color_scheme
        
        return [
            {
                "color": scheme.base_plane_high,
                "label": "Base Plane (>90% confidence)",
                "type": "base_plane"
            },
            {
                "color": scheme.hole_high,
                "label": "Hole (>90% confidence)",
                "type": "hole"
            },
            {
                "color": scheme.hole_medium,
                "label": "Hole (70-90% confidence)",
                "type": "hole"
            },
            {
                "color": scheme.uncertain,
                "label": "Uncertain (<70% confidence)",
                "type": "uncertain"
            },
        ]
    
    def get_feature_statistics(self, analysis: MockAnalysis) -> Dict[str, Any]:
        """Get statistics about detected features."""
        holes_high = sum(1 for h in analysis.holes 
                        if h.confidence >= self.HIGH_CONFIDENCE)
        holes_medium = sum(1 for h in analysis.holes 
                          if self.MEDIUM_CONFIDENCE <= h.confidence < self.HIGH_CONFIDENCE)
        holes_low = sum(1 for h in analysis.holes 
                       if h.confidence < self.MEDIUM_CONFIDENCE)
        
        return {
            "total_features": (
                (1 if analysis.base_plane else 0) +
                len(analysis.holes) +
                len(analysis.pockets)
            ),
            "base_plane": {
                "detected": analysis.base_plane is not None,
                "confidence": analysis.base_plane.confidence if analysis.base_plane else 0
            },
            "holes": {
                "total": len(analysis.holes),
                "high_confidence": holes_high,
                "medium_confidence": holes_medium,
                "low_confidence": holes_low,
            },
            "overall_confidence": analysis.overall_confidence,
            "requires_review": analysis.requires_user_review,
        }


# Tests
def test_color_selection():
    """Test color selection based on confidence."""
    mixin = STLFeatureMixinLogic()
    
    # High confidence base plane
    color = mixin._get_color_for_base_plane(0.95)
    assert color == (0, 255, 0)  # Green
    
    # Medium confidence base plane
    color = mixin._get_color_for_base_plane(0.8)
    assert color == (100, 255, 100)  # Light green
    
    # High confidence hole
    color = mixin._get_color_for_hole(0.95)
    assert color == (0, 100, 255)  # Blue
    
    # Medium confidence hole
    color = mixin._get_color_for_hole(0.8)
    assert color == (100, 150, 255)  # Light blue
    
    # Low confidence hole
    color = mixin._get_color_for_hole(0.6)
    assert color == (150, 200, 255)  # Lighter blue
    
    # Uncertain hole
    color = mixin._get_color_for_hole(0.4)
    assert color == (255, 165, 0)  # Orange
    
    print("[OK] Color selection test passed")


def test_legend_info():
    """Test legend info generation."""
    mixin = STLFeatureMixinLogic()
    legend = mixin.get_legend_info()
    
    assert len(legend) >= 4
    assert any(item["type"] == "base_plane" for item in legend)
    assert any(item["type"] == "hole" for item in legend)
    assert any(item["type"] == "uncertain" for item in legend)
    
    print("[OK] Legend info test passed")


def test_feature_statistics():
    """Test feature statistics calculation."""
    mixin = STLFeatureMixinLogic()
    
    analysis = MockAnalysis(
        base_plane=MockPlane(confidence=0.95),
        holes=[
            MockHole(confidence=0.95),
            MockHole(confidence=0.85),
            MockHole(confidence=0.6),
            MockHole(confidence=0.4),
        ],
        pockets=[MockPocket(confidence=0.8)],
        overall_confidence=0.8,
        requires_user_review=True
    )
    
    stats = mixin.get_feature_statistics(analysis)
    
    assert stats["total_features"] == 6  # 1 base + 4 holes + 1 pocket
    assert stats["base_plane"]["detected"] == True
    assert stats["base_plane"]["confidence"] == 0.95
    assert stats["holes"]["total"] == 4
    assert stats["holes"]["high_confidence"] == 1
    assert stats["holes"]["medium_confidence"] == 1
    assert stats["holes"]["low_confidence"] == 2
    assert stats["overall_confidence"] == 0.8
    assert stats["requires_review"] == True
    
    print("[OK] Feature statistics test passed")


def test_empty_analysis():
    """Test with empty analysis."""
    mixin = STLFeatureMixinLogic()
    
    analysis = MockAnalysis()
    stats = mixin.get_feature_statistics(analysis)
    
    assert stats["total_features"] == 0
    assert stats["base_plane"]["detected"] == False
    assert stats["holes"]["total"] == 0
    
    print("[OK] Empty analysis test passed")


if __name__ == "__main__":
    print("Running STL Feature Mixin Tests...")
    print("-" * 50)
    
    try:
        test_color_selection()
        test_legend_info()
        test_feature_statistics()
        test_empty_analysis()
        
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
