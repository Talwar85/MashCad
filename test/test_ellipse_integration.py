"""
Integration Tests für Native Ellipse2D

Diese Tests prüfen:
1. Handle Selektion (Center, Major, Minor Punkte)
2. Constraint-Propagation (Achsen-Änderungen → Ellipse)
3. Direct Edit (Drag & Drop)
"""

import math
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

# Versuche Imports - handle falls GUI nicht verfügbar
try:
    from sketcher import Sketch
    from sketcher.geometry import Point2D, Line2D, Ellipse2D
    from sketcher.constraints import ConstraintType
    SKETCHER_AVAILABLE = True
except ImportError:
    SKETCHER_AVAILABLE = False

try:
    from gui.sketch_editor import SketchEditor
    from gui.sketch_tools import SketchTool
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapplication():
    """Ensure Qt application exists before creating SketchEditor widgets."""
    if not GUI_AVAILABLE:
        yield None
        return
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.skipif(not SKETCHER_AVAILABLE, reason="Sketcher not available")
class TestEllipseHandleCreation:
    """Testet dass Ellipse-Handles korrekt erstellt werden."""
    
    def test_ellipse_has_handle_attributes(self):
        """Ellipse und ihre Punkte müssen _ellipse_handle Attribute haben."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        assert hasattr(ellipse, '_center_point'), "Ellipse braucht _center_point"
        assert hasattr(ellipse, '_major_axis'), "Ellipse braucht _major_axis"
        assert hasattr(ellipse, '_minor_axis'), "Ellipse braucht _minor_axis"
        assert hasattr(ellipse, '_major_pos'), "Ellipse braucht _major_pos"
        assert hasattr(ellipse, '_major_neg'), "Ellipse braucht _major_neg"
        assert hasattr(ellipse, '_minor_pos'), "Ellipse braucht _minor_pos"
        assert hasattr(ellipse, '_minor_neg'), "Ellipse braucht _minor_neg"
    
    def test_handle_points_marked(self):
        """Alle Handle-Punkte müssen _ellipse_handle Attribut haben."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        center = ellipse._center_point
        major_pos = ellipse._major_pos
        major_neg = ellipse._major_neg
        minor_pos = ellipse._minor_pos
        minor_neg = ellipse._minor_neg
        
        assert getattr(center, '_ellipse_handle', None) == "center", "Center nicht markiert"
        assert getattr(major_pos, '_ellipse_handle', None) == "major_pos", "Major+ nicht markiert"
        assert getattr(major_neg, '_ellipse_handle', None) == "major_neg", "Major- nicht markiert"
        assert getattr(minor_pos, '_ellipse_handle', None) == "minor_pos", "Minor+ nicht markiert"
        assert getattr(minor_neg, '_ellipse_handle', None) == "minor_neg", "Minor- nicht markiert"
    
    def test_handle_points_have_parent_reference(self):
        """Handle-Punkte müssen _parent_ellipse Referenz haben."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        for point in [ellipse._center_point, ellipse._major_pos, ellipse._major_neg, 
                      ellipse._minor_pos, ellipse._minor_neg]:
            assert getattr(point, '_parent_ellipse', None) is ellipse, \
                f"Punkt {point} hat keine _parent_ellipse Referenz"


@pytest.mark.skipif(not SKETCHER_AVAILABLE, reason="Sketcher not available")
class TestEllipseConstraintPropagation:
    """Testet dass Constraint-Änderungen an Achsen die Ellipse aktualisieren."""
    
    def test_axis_length_constraint_updates_ellipse(self):
        """Wenn Major-Achse länger wird, sollte radius_x größer werden."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        initial_rx = ellipse.radius_x
        
        # Simuliere: Major-Achse wurde verlängert (durch Constraint oder Drag)
        # Die Achsen-Endpunkte bewegen sich
        ellipse._major_pos.x = 15  # war 10
        ellipse._major_neg.x = -15  # war -10
        
        # Update Geometry
        sketch._update_ellipse_geometry()
        
        # Ellipse sollte neuen Radius haben
        assert ellipse.radius_x == 15, f"radius_x sollte 15 sein, ist {ellipse.radius_x}"
        assert ellipse.center.x == 0, "Center sollte bei 0 bleiben"
    
    def test_center_move_updates_ellipse(self):
        """Wenn Center-Point verschoben wird, sollte Ellipse-Center folgen."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        # Verschiebe Center-Point
        ellipse._center_point.x = 5
        ellipse._center_point.y = 3
        
        # Update Geometry
        sketch._update_ellipse_geometry()
        
        assert ellipse.center.x == 5, f"center.x sollte 5 sein, ist {ellipse.center.x}"
        assert ellipse.center.y == 3, f"center.y sollte 3 sein, ist {ellipse.center.y}"
    
    def test_minor_axis_updates_radius_y(self):
        """Wenn Minor-Achse verlängert wird, sollte radius_y größer werden."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        # Verlängere Minor-Achse
        ellipse._minor_pos.y = 8  # war 5
        ellipse._minor_neg.y = -8  # war -5
        
        # Update Geometry
        sketch._update_ellipse_geometry()
        
        assert ellipse.radius_y == 8, f"radius_y sollte 8 sein, ist {ellipse.radius_y}"
    
    def test_rotation_updates_angle(self):
        """Wenn Achsen rotieren, sollte Ellipse-Rotation aktualisiert werden."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        # Rotiere Major-Achse um 45°
        import math
        angle_rad = math.radians(45)
        ellipse._major_pos.x = 10 * math.cos(angle_rad)
        ellipse._major_pos.y = 10 * math.sin(angle_rad)
        ellipse._major_neg.x = -10 * math.cos(angle_rad)
        ellipse._major_neg.y = -10 * math.sin(angle_rad)
        
        # Update Geometry
        sketch._update_ellipse_geometry()
        
        # Rotation sollte aktualisiert sein (oder zumindest die native_ocp_data)
        assert ellipse.rotation == 45, f"rotation sollte 45 sein, ist {ellipse.rotation}"


@pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
class TestEllipseHandleSelection:
    """Testet Handle-Selektion im SketchEditor."""
    
    def test_ellipse_axis_lines_not_selectable(self):
        """Ellipsen-Achsen sollten nicht selektierbar sein."""
        from gui.sketch_editor import SketchEditor
        
        editor = SketchEditor()
        sketch = editor.sketch
        
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        major_axis = ellipse._major_axis
        
        # Prüfe dass Achse als Ellipsen-Achse markiert ist
        assert getattr(major_axis, '_ellipse_axis', None) is not None
        
        # Prüfe dass _entity_passes_selection_filter False zurückgibt
        passes = editor._entity_passes_selection_filter(major_axis)
        assert passes is False, "Ellipsen-Achse sollte nicht selektierbar sein"
    
    def test_ellipse_handle_priority(self):
        """Ellipse-Handles sollten höhere Priorität haben als Linien."""
        from gui.sketch_editor import SketchEditor
        
        editor = SketchEditor()
        sketch = editor.sketch
        
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        center_point = ellipse._center_point
        
        # Handle-Punkt sollte höhere Priorität haben
        priority = editor._entity_pick_priority(center_point)
        assert priority < 5, f"Handle-Punkt sollte Priorität < 5 haben, hat {priority}"
    
    def test_distance_to_ellipse_handle(self):
        """Distanz zu Ellipse-Handles sollte korrekt berechnet werden."""
        from gui.sketch_editor import SketchEditor
        
        editor = SketchEditor()
        sketch = editor.sketch
        
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        center_point = ellipse._center_point
        
        # Distanz zu Center-Point
        pos = QPointF(0, 0)
        dist = editor._entity_distance_to_pos(center_point, pos)
        assert abs(dist) < 0.001, f"Distanz zu Center sollte ~0 sein, ist {dist}"
        
        # Distanz zu Major-Pos
        major_pos = ellipse._major_pos
        pos = QPointF(10, 0)
        dist = editor._entity_distance_to_pos(major_pos, pos)
        assert abs(dist) < 0.001, f"Distanz zu Major-Pos sollte ~0 sein, ist {dist}"


@pytest.mark.skipif(not GUI_AVAILABLE, reason="GUI not available")
class TestEllipseDirectEdit:
    """Testet Direct-Edit Funktionalität."""
    
    def test_resolve_ellipse_target_returns_ellipse(self):
        """_resolve_direct_edit_target_ellipse sollte Ellipse zurückgeben."""
        from gui.sketch_editor import SketchEditor
        
        editor = SketchEditor()
        sketch = editor.sketch
        
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        editor.selected_ellipses = [ellipse]
        
        target, source = editor._resolve_direct_edit_target_ellipse()
        assert target is ellipse, "Sollte selektierte Ellipse zurückgeben"
        assert source == "ellipse"
    
    def test_pick_direct_edit_handle_for_center(self):
        """Center-Handle sollte pickbar sein."""
        from gui.sketch_editor import SketchEditor
        from PySide6.QtCore import QPointF
        
        editor = SketchEditor()
        sketch = editor.sketch
        
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        editor.selected_ellipses = [ellipse]
        
        # Mouse direkt auf Center
        world_pos = QPointF(0, 0)
        handle = editor._pick_direct_edit_handle(world_pos)
        
        assert handle is not None, "Handle sollte gefunden werden"
        assert handle.get("mode") == "center", f"Sollte center mode sein, ist {handle.get('mode')}"


class TestEllipseGeometryUpdate:
    """Testet die _update_ellipse_geometry Methode im Detail."""
    
    def test_update_from_axis_points(self):
        """Testet dass Ellipse-Parameter aus Achsen-Punkten berechnet werden."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        # Ändere Achsen-Endpunkte
        ellipse._major_pos.x = 20
        ellipse._major_neg.x = -20
        ellipse._major_pos.y = 0
        ellipse._major_neg.y = 0
        
        # Update
        sketch._update_ellipse_geometry()
        
        # Prüfe
        assert ellipse.radius_x == 20, f"Major radius sollte 20 sein, ist {ellipse.radius_x}"
        assert ellipse.center.x == 0
    
    def test_native_ocp_data_updated(self):
        """native_ocp_data sollte bei Update aktualisiert werden."""
        sketch = Sketch()
        ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
        
        # Ändere und update
        ellipse._center_point.x = 5
        sketch._update_ellipse_geometry()
        
        assert ellipse.native_ocp_data['center'] == (5, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
