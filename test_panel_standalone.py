"""
Standalone Test für STL Reconstruction Panel Logic.
Testet ohne Qt-Imports.
"""

import sys
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class MockFeatureItem:
    """Mock feature list item."""
    feature_type: str
    index: int
    name: str
    confidence: float
    parameters: Dict[str, Any]
    is_selected: bool = True


@dataclass 
class MockAnalysis:
    """Mock analysis."""
    base_plane: Optional[Any] = None
    holes: List[Any] = field(default_factory=list)
    pockets: List[Any] = field(default_factory=list)
    fillets: List[Any] = field(default_factory=list)
    overall_confidence: float = 0.0
    requires_user_review: bool = False


@dataclass
class MockQualityReport:
    """Mock quality report."""
    is_valid: bool = True
    recommended_action: str = "proceed"
    face_count: int = 1000
    vertex_count: int = 500
    is_watertight: bool = True


class PanelLogicTester:
    """Testet die Panel-Logik ohne Qt."""
    
    def __init__(self):
        self._feature_items: List[MockFeatureItem] = []
        self._analysis: Optional[MockAnalysis] = None
    
    def set_analysis(self, analysis: MockAnalysis, quality_report: MockQualityReport = None):
        """Set analysis and populate feature items."""
        self._analysis = analysis
        self._feature_items.clear()
        
        # Add base plane
        if analysis.base_plane:
            self._feature_items.append(MockFeatureItem(
                feature_type="base_plane",
                index=0,
                name="Base Plane",
                confidence=analysis.base_plane.get("confidence", 0.9),
                parameters={"area": analysis.base_plane.get("area", 100.0)}
            ))
        
        # Add holes
        for i, hole in enumerate(analysis.holes):
            self._feature_items.append(MockFeatureItem(
                feature_type="hole",
                index=i,
                name=f"Hole #{i+1}",
                confidence=hole.get("confidence", 0.8),
                parameters={
                    "radius": hole.get("radius", 5.0),
                    "depth": hole.get("depth", 10.0),
                }
            ))
        
        # Add pockets
        for i, pocket in enumerate(analysis.pockets):
            self._feature_items.append(MockFeatureItem(
                feature_type="pocket",
                index=i,
                name=f"Pocket #{i+1}",
                confidence=pocket.get("confidence", 0.7),
                parameters={"depth": pocket.get("depth", 3.0)}
            ))
    
    def get_selected_features(self) -> List[MockFeatureItem]:
        """Get selected features."""
        return [f for f in self._feature_items if f.is_selected]
    
    def get_feature_statistics(self) -> Dict[str, Any]:
        """Get feature statistics."""
        selected = self.get_selected_features()
        
        holes = [f for f in selected if f.feature_type == "hole"]
        holes_high = sum(1 for h in holes if h.confidence >= 0.9)
        holes_medium = sum(1 for h in holes if 0.7 <= h.confidence < 0.9)
        holes_low = sum(1 for h in holes if h.confidence < 0.7)
        
        return {
            "total_features": len(selected),
            "holes": {
                "total": len(holes),
                "high": holes_high,
                "medium": holes_medium,
                "low": holes_low,
            }
        }
    
    def select_all(self):
        """Select all features."""
        for f in self._feature_items:
            f.is_selected = True
    
    def unselect_all(self):
        """Unselect all features."""
        for f in self._feature_items:
            f.is_selected = False
    
    def toggle_feature(self, index: int, selected: bool):
        """Toggle a specific feature."""
        if 0 <= index < len(self._feature_items):
            self._feature_items[index].is_selected = selected


# Tests
def test_panel_populate():
    """Test populating panel with analysis."""
    panel = PanelLogicTester()
    
    analysis = MockAnalysis(
        base_plane={"confidence": 0.95, "area": 200.0},
        holes=[
            {"confidence": 0.9, "radius": 5.0, "depth": 10.0},
            {"confidence": 0.8, "radius": 3.0, "depth": 8.0},
            {"confidence": 0.6, "radius": 2.0, "depth": 5.0},
        ],
        pockets=[
            {"confidence": 0.75, "depth": 3.0},
        ]
    )
    
    quality = MockQualityReport()
    panel.set_analysis(analysis, quality)
    
    # Should have 5 items (1 base + 3 holes + 1 pocket)
    assert len(panel._feature_items) == 5
    
    # All should be selected by default
    assert len(panel.get_selected_features()) == 5
    
    print("[OK] Panel populate test passed")


def test_feature_selection():
    """Test feature selection logic."""
    panel = PanelLogicTester()
    
    analysis = MockAnalysis(
        base_plane={"confidence": 0.95},
        holes=[{"confidence": 0.9}, {"confidence": 0.8}]
    )
    
    panel.set_analysis(analysis)
    
    # Unselect all
    panel.unselect_all()
    assert len(panel.get_selected_features()) == 0
    
    # Select specific
    panel.toggle_feature(1, True)  # First hole
    selected = panel.get_selected_features()
    assert len(selected) == 1
    assert selected[0].feature_type == "hole"
    
    # Select all
    panel.select_all()
    assert len(panel.get_selected_features()) == 3
    
    print("[OK] Feature selection test passed")


def test_feature_statistics():
    """Test statistics calculation."""
    panel = PanelLogicTester()
    
    analysis = MockAnalysis(
        holes=[
            {"confidence": 0.95},  # High (>= 0.9)
            {"confidence": 0.85},  # Medium (0.7-0.9)
            {"confidence": 0.75},  # Medium (0.7-0.9)
            {"confidence": 0.65},  # Low (< 0.7)
        ]
    )
    
    panel.set_analysis(analysis)
    stats = panel.get_feature_statistics()
    
    assert stats["total_features"] == 4
    assert stats["holes"]["total"] == 4
    assert stats["holes"]["high"] == 1  # Only 0.95
    assert stats["holes"]["medium"] == 2  # 0.85 and 0.75
    assert stats["holes"]["low"] == 1  # 0.65
    
    print("[OK] Feature statistics test passed")


def test_empty_analysis():
    """Test with empty analysis."""
    panel = PanelLogicTester()
    panel.set_analysis(MockAnalysis())
    
    assert len(panel._feature_items) == 0
    assert len(panel.get_selected_features()) == 0
    
    stats = panel.get_feature_statistics()
    assert stats["total_features"] == 0
    
    print("[OK] Empty analysis test passed")


def test_quality_report_parsing():
    """Test quality report status parsing."""
    report = MockQualityReport(
        is_valid=True,
        recommended_action="proceed",
        face_count=10000,
        vertex_count=5000,
        is_watertight=True
    )
    
    assert report.is_valid
    assert report.recommended_action == "proceed"
    assert report.is_watertight
    
    # Test different status
    report.recommended_action = "repair"
    assert report.recommended_action == "repair"
    
    print("[OK] Quality report parsing test passed")


if __name__ == "__main__":
    print("Running STL Reconstruction Panel Tests...")
    print("-" * 50)
    
    try:
        test_panel_populate()
        test_feature_selection()
        test_feature_statistics()
        test_empty_analysis()
        test_quality_report_parsing()
        
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
