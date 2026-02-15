import sys
import unittest
from unittest.mock import MagicMock, patch

# Add C:\LiteCad to sys.path
sys.path.append(r"C:\LiteCad")

# Mock modules that might not be available or heavy
sys.modules['loguru'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['config.tolerances'] = MagicMock()
sys.modules['config.feature_flags'] = MagicMock()
sys.modules['gui.design_tokens'] = MagicMock()
sys.modules['gui.sketch_snapper'] = MagicMock()
sys.modules['gui.quadtree'] = MagicMock()
sys.modules['gui.sketch_feedback'] = MagicMock()

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

# Initialize QApplication (needed for QWidget)
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

# Import SketchEditor after mocks
from gui.sketch_editor import SketchEditor
from sketcher.geometry import BezierSpline, SplineControlPoint, Point2D

class TestSplineFix(unittest.TestCase):
    def setUp(self):
        # Patch __init__ to avoid heavy GUI setup
        with patch.object(SketchEditor, '__init__', return_value=None):
            self.editor = SketchEditor()
            
        # Mock attributes needed by _drag_spline_element
        self.editor.mouse_world = QPointF(10, 10)
        self.editor.spline_drag_cp_index = 0
        
        # Create a mock spline
        spline = BezierSpline()
        spline.add_point(0, 0) # Index 0
        spline.add_point(20, 0)
        
        self.editor.selected_splines = [spline]
        self.editor.spline_drag_spline = spline
        self.editor.spline_drag_type = 'point' # FIX: Missing attribute
        self.editor.snap_radius = 10.0
        self.editor.view_scale = 1.0
        
        # Mock methods
        self.editor.snap_point = MagicMock(return_value=(QPointF(10, 10), "snap_type", "snap_entity"))
        self.editor.request_update = MagicMock()
        self.editor.sketched_changed = MagicMock()
        self.editor.sketched_changed.emit = MagicMock()
        self.editor._find_closed_profiles = MagicMock()
        self.editor.status_message = MagicMock()
        self.editor.status_message.emit = MagicMock()
        
    def test_drag_spline_element_no_crash(self):
        """Test that _drag_spline_element handles 3 return values from snap_point without crashing."""
        try:
            self.editor._drag_spline_element(shift_pressed=False)
        except ValueError as e:
            self.fail(f"_drag_spline_element raised ValueError: {e}")
        except Exception as e:
            self.fail(f"_drag_spline_element raised unexpected exception: {e}")
            
        # Verify the point moved
        spline = self.editor.selected_splines[0]
        self.assertEqual(spline.control_points[0].point.x, 10)
        self.assertEqual(spline.control_points[0].point.y, 10)
        
    def test_snap_point_called(self):
        self.editor._drag_spline_element(shift_pressed=False)
        self.editor.snap_point.assert_called_with(self.editor.mouse_world)

if __name__ == '__main__':
    unittest.main()
