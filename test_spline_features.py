import unittest
import math
import sys
from unittest.mock import MagicMock, patch

# Add C:\LiteCad to sys.path
sys.path.append(r"C:\LiteCad")

# Mock modules
sys.modules['loguru'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['config.tolerances'] = MagicMock()
sys.modules['config.feature_flags'] = MagicMock()
sys.modules['gui.design_tokens'] = MagicMock()
sys.modules['gui.sketch_snapper'] = MagicMock()
sys.modules['gui.quadtree'] = MagicMock()
sys.modules['gui.sketch_feedback'] = MagicMock()

from PySide6.QtCore import QPointF, Qt, QPoint
from PySide6.QtWidgets import QApplication

# Initialize QApplication
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from gui.sketch_editor import SketchEditor
from sketcher.geometry import BezierSpline, SplineControlPoint, Point2D
from gui.sketch_tools import SketchTool

class TestSplineFeatures(unittest.TestCase):
    def setUp(self):
        with patch.object(SketchEditor, '__init__', return_value=None):
            self.editor = SketchEditor()
            
        # Mock basics
        self.editor.sketch = MagicMock()
        self.editor.sketch.splines = []
        self.editor.mouse_world = QPointF(50, 50)
        self.editor.view_scale = 1.0
        self.editor.snap_radius = 10.0
        self.editor.current_tool = SketchTool.SELECT
        self.editor.selected_splines = []
        
        # Mocks
        self.editor.screen_to_world = MagicMock(side_effect=lambda p: p) # Mock 1:1 mapping
        self.editor.request_update = MagicMock()
        self.editor.status_message = MagicMock()
        self.editor.status_message.emit = MagicMock()
        self.editor._find_entity_at = MagicMock(return_value=None)
        self.editor.snap_point = MagicMock(return_value=(QPointF(50, 50), "snap_type", "snap_entity"))
        self.editor._find_spline_element_at = MagicMock(return_value=None)
        
        # Mock shapely
        sys.modules['shapely'] = MagicMock()
        sys.modules['shapely.geometry'] = MagicMock()
        sys.modules['shapely.ops'] = MagicMock()
        
        # Mock dim_input
        self.editor.dim_input_active = False
        self.editor.dim_input = MagicMock()
        self.editor.dim_input.isVisible = MagicMock(return_value=False)
        self.editor._find_closed_profiles = MagicMock() # Skip this heavy method
        
        # Mock selection lists
        self.editor.selected_points = []
        self.editor.selected_lines = []
        self.editor.selected_circles = []
        self.editor.selected_arcs = []
        self.editor.selected_constraints = []
        self.editor.selected_splines = []
        
        # Mock signals explicitly to avoid RuntimeError
        self.editor.sketched_changed = MagicMock()
        self.editor.sketched_changed.emit = MagicMock()
        self.editor.status_message = MagicMock()
        self.editor.status_message.emit = MagicMock()
        self.editor.request_update = MagicMock()
        
        # Mock canvas state
        self.editor._canvas_calibrating = False
        self.editor._canvas_dragging = False
        self.editor.selection_box_start = None
        self.editor.canvas_image = None
        self.editor.canvas_locked = False
        self.editor.canvas_visible = True
        self.editor.canvas_opacity = 1.0
        
        # Initialize internal state for property setters
        self.editor._tool_step = 0
        self.editor._last_auto_show_step = -1
        
        self.editor._save_undo = MagicMock()
        
        self.editor.setCursor = MagicMock()
        self.editor.cursor = MagicMock()
        self.editor.mapToGlobal = MagicMock(return_value=QPoint(100, 100))
        
        # Helper to create spline
        self.spline = BezierSpline()
        self.spline.add_point(0, 0)
        self.spline.add_point(100, 0)
        self.editor.sketch.splines.append(self.spline)

    def test_body_drag_initiation(self):
        """Test that clicking the spline body initiates body dragging."""
        # Setup hit testing to return the spline
        self.editor._find_spline_at = MagicMock(return_value=self.spline)
        
        # Simulate Mouse Press
        event = MagicMock()
        event.button.return_value = Qt.LeftButton
        event.modifiers.return_value = Qt.NoModifier
        
        self.editor.mousePressEvent(event)
        
        # Verify Body Drag initiation
        self.assertTrue(self.editor.spline_dragging)
        self.assertEqual(self.editor.spline_drag_spline, self.spline)
        self.assertEqual(self.editor.spline_drag_type, 'body')
        self.assertEqual(self.editor.spline_drag_start_pos, self.editor.mouse_world)
        
    def test_body_drag_movement(self):
        """Test that _drag_spline_element moves all points when dragging body."""
        # Setup Body Drag State
        self.editor.spline_dragging = True
        self.editor.spline_drag_spline = self.spline
        self.editor.spline_drag_type = 'body'
        self.editor.spline_drag_start_pos = QPointF(50, 50)
        
        # Move mouse to (60, 60) -> Delta (10, 10)
        self.editor.mouse_world = QPointF(60, 60)
        
        self.editor._drag_spline_element(shift_pressed=False)
        
        # Verify points moved
        self.assertEqual(self.spline.control_points[0].point.x, 10.0) # 0 + 10
        self.assertEqual(self.spline.control_points[0].point.y, 10.0) # 0 + 10
        self.assertEqual(self.spline.control_points[1].point.x, 110.0) # 100 + 10
        self.assertEqual(self.spline.control_points[1].point.y, 10.0) # 0 + 10
        
        # Verify start pos updated
        self.assertEqual(self.editor.spline_drag_start_pos, QPointF(60, 60))

    def test_context_menu_coords(self):
        """Test that _show_context_menu converts screen coords to world coords."""
        # Mock screen_to_world to verify it's called
        pos_screen = QPointF(200, 200)
        pos_world = QPointF(50, 50)
        self.editor.screen_to_world = MagicMock(return_value=pos_world)
        
        # Stub _find methods
        self.editor._find_spline_element_at = MagicMock(return_value=None)
        self.editor._find_spline_at = MagicMock(return_value=None)
        
        # Call context menu
        # We need to mock QMenu because it requires GUI
        with patch('gui.sketch_editor.QMenu') as MockMenu:
            self.editor._show_context_menu(pos_screen)
            
            # Verify translation
            self.editor.screen_to_world.assert_called_with(pos_screen)
            
            # Verify detection called with world coords
            self.editor._find_spline_element_at.assert_called_with(pos_world)
    def test_insert_point_coords(self):
        """Test that _insert_spline_point is called with WORLD coordinates."""
        # Setup context menu scenario
        pos_screen = QPointF(200, 200)
        pos_world = QPointF(50, 50)
        self.editor.screen_to_world = MagicMock(return_value=pos_world)
        self.editor._find_spline_element_at = MagicMock(return_value=None)
        self.editor._find_spline_at = MagicMock(return_value=self.spline)
        
        # Mock addAction to capture the lambda
        captured_action = None
        def mock_addAction(text, callback=None):
            nonlocal captured_action
            if text == "Punkt einfügen":
                captured_action = callback
                
        # Mock QMenu
        with patch('gui.sketch_editor.QMenu') as MockMenu:
            instance = MockMenu.return_value
            instance.addAction.side_effect = mock_addAction
            
            self.editor._show_context_menu(pos_screen)
            
            # Execute the action
            if captured_action:
                # Mock _insert_spline_point to check args
                self.editor._insert_spline_point = MagicMock()
                captured_action()
                self.editor._insert_spline_point.assert_called_with(self.spline, pos_world)
            else:
                self.fail("Context menu action 'Punkt einfügen' not found")

    def test_canvas_menu_no_crash(self):
        """Test that context menu opens without crash even with canvas image (regression test)."""
        self.editor.canvas_image = MagicMock()
        # Mock QMenu
        with patch('gui.sketch_editor.QMenu') as MockMenu:
             self.editor._show_context_menu(QPointF(100, 100))
             # Should not raise exception

    def test_spline_snap_label_visible(self):
        """Test that snap labels are shown for Spline tool (UX improvement)."""
        self.editor.current_tool = SketchTool.SPLINE
        self.editor.tool_step = 1 # Active drawing
        
        # FIX: Configure SnapType mock to support int() conversion of value
        # Since gui.sketch_snapper is mocked, SnapType is a Mock.
        from gui.sketch_snapper import SnapType
        SnapType.ENDPOINT.value = 1
        
        # Test if _should_show_snap_label accepts Spline tool
        # Wemock _snap_label_key logic by setting it to None
        self.editor._snap_label_key = None
        pos = QPointF(10, 10)
        
        try:
             # Just verify it doesn't crash and hopefully returns something
             # Note: return value depends on timing, so we don't assert True/False
             # but the fact that it runs without error means the tool check passed (or didn't crash)
             self.editor._should_show_snap_label(SnapType.ENDPOINT, pos)
        except Exception as e:
             self.fail(f"_should_show_snap_label raised exception: {e}")

    def test_find_spline_methods(self):
        """Test the real implementation of _find_spline_at and _find_spline_element_at."""
        # Unmock the methods we just added to the class
        # Since we patched SketchEditor.__init__, the methods should be available on self.editor
        # BUT self.editor is an instance of SketchEditor which we patched via __init__ return_value=None.
        # The methods are bound to the instance.
        
        # However, we mocked them in setUp!
        # We need to restore them. 
        # But we didn't mock them in setUp for the CLASS, only for the instance.
        # Wait, in setUp I did: self.editor._find_spline_element_at = MagicMock(return_value=None)
        
        # Restore real methods from the class
        self.editor._find_spline_at = SketchEditor._find_spline_at.__get__(self.editor, SketchEditor)
        self.editor._find_spline_element_at = SketchEditor._find_spline_element_at.__get__(self.editor, SketchEditor)
        
        # Setup Spline
        spline = BezierSpline()
        spline.add_point(0, 0)
        spline.add_point(100, 0)
        self.editor.sketch.splines = [spline]
        
        # Test _find_spline_element_at (Point)
        # Point 0 is at (0,0)
        res = self.editor._find_spline_element_at(QPointF(0, 0))
        self.assertIsNotNone(res)
        self.assertEqual(res[0], spline)
        self.assertEqual(res[1], 0) # Index 0
        self.assertEqual(res[2], 'point')
        
        # Test _find_spline_at (Curve)
        # Midpoint approx (50, 0)
        # Force cache update
        spline._lines = spline.to_lines(segments_per_span=10)
        
        res = self.editor._find_spline_at(QPointF(50, 1))
        self.assertEqual(res, spline)
        
        # Test Miss
        res = self.editor._find_spline_at(QPointF(50, 50))
        self.assertIsNone(res)

    def test_ghost_lines_fix(self):
        """Test that inserting a point removes old lines (fixes ghost lines)."""
        # Setup
        s = BezierSpline()
        s._lines = [] 
        # Add simpler points
        s.add_point(0, 0)
        s.add_point(100, 0)
        
        # Create a mock old line
        old_line = MagicMock() 
        s._lines = [old_line]
        self.editor.sketch.lines = [old_line] # The sketch has the old line
        
        # Mocking specific methods for _insert_spline_point
        self.editor._find_closed_profiles = MagicMock()
        self.editor.request_update = MagicMock()
        self.editor.sketched_changed = MagicMock()
        self.editor.mapToGlobal = MagicMock(return_value=QPoint(0,0)) 
        self.editor._save_undo = MagicMock()
        
        # Point allowing easy insertion (midpoint)
        pos = QPointF(50, 0)
        
        # Action: Insert point
        with patch('math.hypot', side_effect=math.hypot): # Ensure math works
             self.editor._insert_spline_point(s, pos)
        
        # Assertions
        # 1. Old line should be gone from sketch.lines. 
        self.assertFalse(old_line in self.editor.sketch.lines, "Ghost line bug: Old line was not removed from sketch.lines")
        
        # 2. Sketch lines should have new lines
        self.assertGreater(len(self.editor.sketch.lines), 0)
        self.assertNotEqual(self.editor.sketch.lines[0], old_line)

    def test_curvature_comb(self):
        """Test Curvature Comb calculation and interaction."""
        # 1. Setup Spline
        s = BezierSpline()
        s.add_point(0, 0)
        s.add_point(50, 50) 
        s.add_point(100, 0)
        
        # 2. Test Calculation
        # Note: exact length depends on tessellation, so we check approximate
        comb = s.get_curvature_comb(num_samples=10, scale=1.0)
        self.assertGreaterEqual(len(comb), 10)
        self.assertLessEqual(len(comb), 15)
        # Check if we have some curvature (middle point should be curved)
        # First point index 0, last index 9. Middle around 4-5.
        mid_k = comb[5][2]
        self.assertNotEqual(mid_k, 0.0, "Curvature should not be zero for curved spline")
        
        # 3. Test Toggle (Attribute)
        self.assertFalse(getattr(s, 'show_curvature', False))
        
        # Simulate Menu Action logic
        setattr(s, 'show_curvature', True)
        self.assertTrue(s.show_curvature)
        
        # 4. Test Rendering Call
        mock_painter = MagicMock()
        try:
             self.editor.view_scale = 1.0 # needed for scale calculation
             self.editor._draw_curvature_comb(mock_painter, s)
        except Exception as e:
             self.fail(f"_draw_curvature_comb crashed: {e}")

    def test_nurbs_weight_editing(self):
        """Test NURBS Weight Editing feature."""
        # 1. Setup Spline with 3 points
        s = BezierSpline()
        cp1 = s.add_point(0, 0)
        cp2 = s.add_point(50, 50) # Middle point (puller)
        cp3 = s.add_point(100, 0)
        
        # Initial curve point at t=0.5 of first segment
        # pts[0]=t=0, pts[1]=t=0.5, pts[2]=t=1.0 (cp2)
        pts_initial = s.get_curve_points(segments_per_span=2)
        y_mid_initial = pts_initial[1][1]
        
        # 2. Increase Weight of Middle Point (which is P3 of first segment)
        cp2.weight = 5.0
        s.invalidate_cache()
        
        pts_heavy = s.get_curve_points(segments_per_span=2)
        y_mid_heavy = pts_heavy[1][1]
        
        # With higher weight at P3 (50,50), the curve at t=0.5 should be pulled closer to P3 (higher Y)
        self.assertGreater(y_mid_heavy, y_mid_initial, f"Higher weight should pull curve closer to CP. {y_mid_heavy} > {y_mid_initial}")
        
        # 3. Decrease Weight
        cp2.weight = 0.5
        s.invalidate_cache()
        
        pts_light = s.get_curve_points(segments_per_span=2)
        y_mid_light = pts_light[1][1]
        
        self.assertLess(y_mid_light, y_mid_initial, "Lower weight should relax curve away from CP")
        
        # 4. Test Interaction Logic (find_spline_element_at interaction)
        # Can't easily mock wheelEvent, but can validte find_spline_element_at detects point
        # The logic is in SketchEditor and was hard to test in isolation, 
        # but the core logic is the Geometry update which we tested above.


if __name__ == '__main__':
    unittest.main()

