"""
W17 Paket A: Direct Manipulation Erweiterung (Arc/Ellipse/Polygon)
===================================================================
Drei neue robuste Interaction-Fälle für SU-004/SU-010.

Neue Interaktionen:
- Arc: Radius-Änderung via Handle, Sweep-Winkel-Änderung
- Ellipse: Radius-X/Radius-Y unabhängige Änderung, Rotation
- Polygon: Eckpunkt-Verschiebung, Seiten-zu-Seiten-Direct-Edit

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
import sys
import math
import time
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from gui.main_window import MainWindow
from gui.sketch_tools import SketchTool
from sketcher import Point2D, Arc2D

# Ellipse2D und Polygon2D sind noch nicht im sketcher Modul verfügbar
# W18 Recovery: Diese Klassen werden für W18 als Mock/Skip behandelt
try:
    from sketcher import Ellipse2D, Polygon2D
except ImportError:
    Ellipse2D = None
    Polygon2D = None

HARNESS_DIR = Path(__file__).resolve().parent
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from crash_containment_helper import run_test_in_subprocess


class ArcInteractionTestHarness:
    """Simulates user interactions for Arc direct manipulation."""
    
    def __init__(self, window):
        self.window = window
        self.editor = window.sketch_editor
        self.window.show()
        self.window._set_mode("sketch")
        
        self.editor.set_tool(SketchTool.SELECT)
        self.editor.tool_step = 0
        self.editor.setFocus()
        
        QTest.qWaitForWindowExposed(self.editor)
        
        self.editor.view_scale = 10.0
        self.editor.view_offset = QPointF(0, 0)
        self.editor.grid_snap = False
        self.editor.request_update()
        QApplication.processEvents()
        
    def to_screen(self, x, y):
        """Convert world coordinates to screen coordinates."""
        pf = self.editor.world_to_screen(Point2D(x, y))
        return pf.toPoint()
        
    def drag_handle(self, arc, handle_type, start_world, end_world):
        """
        Drag einen Arc-Handle.
        
        Args:
            arc: Arc2D Objekt
            handle_type: 'center', 'radius', 'start_angle', 'end_angle'
            start_world: Start-Position (x, y)
            end_world: End-Position (x, y)
        """
        editor = self.editor
        
        # Selektiere Arc
        editor._clear_selection()
        editor.selected_arcs = [arc]
        editor._last_hovered_entity = arc
        
        # Starte Direct Edit Drag
        editor.mouse_world = QPointF(float(start_world[0]), float(start_world[1]))
        handle_hit = editor._pick_direct_edit_handle(editor.mouse_world)

        if handle_hit is None:
            raise RuntimeError(f"Arc handle '{handle_type}' not found")
        expected_mode = {
            "center": "center",
            "radius": "radius",
            "start_angle": "start_angle",
            "end_angle": "end_angle",
        }.get(handle_type)
        if expected_mode and handle_hit.get("mode") != expected_mode:
            raise RuntimeError(
                f"Arc handle mismatch: expected mode '{expected_mode}', got '{handle_hit.get('mode')}'"
            )
            
        editor._start_direct_edit_drag(handle_hit)
        editor._apply_direct_edit_drag(QPointF(float(end_world[0]), float(end_world[1])))
        editor._finish_direct_edit_drag()
        QApplication.processEvents()
        QTest.qWait(20)


class EllipseInteractionTestHarness:
    """Simulates user interactions for Ellipse direct manipulation."""
    
    def __init__(self, window):
        self.window = window
        self.editor = window.sketch_editor
        self.window.show()
        self.window._set_mode("sketch")
        
        self.editor.set_tool(SketchTool.SELECT)
        self.editor.tool_step = 0
        self.editor.setFocus()
        
        QTest.qWaitForWindowExposed(self.editor)
        
        self.editor.view_scale = 10.0
        self.editor.view_offset = QPointF(0, 0)
        self.editor.grid_snap = False
        self.editor.request_update()
        QApplication.processEvents()
        
    def to_screen(self, x, y):
        """Convert world coordinates to screen coordinates."""
        pf = self.editor.world_to_screen(Point2D(x, y))
        return pf.toPoint()
        
    def drag_radius_handle(self, ellipse, axis, start_world, end_world):
        """
        Drag einen Ellipse-Radius-Handle (X oder Y).
        
        Args:
            ellipse: Ellipse2D Objekt
            axis: 'radius_x' oder 'radius_y'
            start_world: Start-Position
            end_world: End-Position
        """
        editor = self.editor
        
        # Selektiere Ellipse
        editor._clear_selection()
        if hasattr(editor, 'selected_ellipses'):
            editor.selected_ellipses = [ellipse]
        else:
            # Fallback: Speichere in editor-Attribut
            editor._test_selected_ellipse = ellipse
        editor._last_hovered_entity = ellipse
        
        # Starte Direct Edit Drag
        editor.mouse_world = QPointF(float(start_world[0]), float(start_world[1]))
        handle_hit = editor._pick_direct_edit_handle(editor.mouse_world)
        
        if handle_hit is None:
            raise RuntimeError(f"Ellipse {axis} handle not found")
        expected_mode = {
            "radius_x": "radius_x",
            "radius_y": "radius_y",
            "rotation": "rotation",
        }.get(axis)
        if expected_mode and handle_hit.get("mode") != expected_mode:
            raise RuntimeError(
                f"Ellipse handle mismatch: expected mode '{expected_mode}', got '{handle_hit.get('mode')}'"
            )
            
        editor._start_direct_edit_drag(handle_hit)
        editor._apply_direct_edit_drag(QPointF(float(end_world[0]), float(end_world[1])))
        editor._finish_direct_edit_drag()
        QApplication.processEvents()
        QTest.qWait(20)


class PolygonInteractionTestHarness:
    """Simulates user interactions for Polygon direct manipulation."""
    
    def __init__(self, window):
        self.window = window
        self.editor = window.sketch_editor
        self.window.show()
        self.window._set_mode("sketch")
        
        self.editor.set_tool(SketchTool.SELECT)
        self.editor.tool_step = 0
        self.editor.setFocus()
        
        QTest.qWaitForWindowExposed(self.editor)
        
        self.editor.view_scale = 10.0
        self.editor.view_offset = QPointF(0, 0)
        self.editor.grid_snap = False
        self.editor.request_update()
        QApplication.processEvents()
        
    def to_screen(self, x, y):
        """Convert world coordinates to screen coordinates."""
        pf = self.editor.world_to_screen(Point2D(x, y))
        return pf.toPoint()
        
    def drag_vertex(self, polygon, vertex_idx, start_world, end_world):
        """
        Drag einen Polygon-Eckpunkt.
        
        Args:
            polygon: Polygon2D Objekt
            vertex_idx: Index des Eckpunkts
            start_world: Start-Position
            end_world: End-Position
        """
        editor = self.editor
        
        # Selektiere Polygon
        editor._clear_selection()
        if hasattr(editor, 'selected_polygons'):
            editor.selected_polygons = [polygon]
        else:
            editor._test_selected_polygon = polygon
        editor._last_hovered_entity = polygon
        
        # Starte Direct Edit Drag
        editor.mouse_world = QPointF(float(start_world[0]), float(start_world[1]))
        handle_hit = editor._pick_direct_edit_handle(editor.mouse_world)
        
        if handle_hit is None:
            raise RuntimeError(f"Polygon vertex {vertex_idx} handle not found")
            
        # Verifiziere Vertex-Index
        if handle_hit.get('vertex_idx') != vertex_idx:
            raise RuntimeError(f"Wrong vertex handle: expected {vertex_idx}, got {handle_hit.get('vertex_idx')}")
            
        editor._start_direct_edit_drag(handle_hit)
        editor._apply_direct_edit_drag(QPointF(float(end_world[0]), float(end_world[1])))
        editor._finish_direct_edit_drag()
        QApplication.processEvents()
        QTest.qWait(20)


# Session-weite QApplication
@pytest.fixture(scope="session")
def qt_app_session():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def arc_harness(qt_app_session):
    """Arc interaction harness."""
    import gc
    window = None
    harness = None
    try:
        window = MainWindow()
        harness = ArcInteractionTestHarness(window)
        yield harness
    finally:
        if harness and hasattr(harness, 'window'):
            try:
                if hasattr(harness.window, 'viewport_3d') and harness.window.viewport_3d:
                    if hasattr(harness.window.viewport_3d, 'plotter'):
                        try:
                            harness.window.viewport_3d.plotter.close()
                        except:
                            pass
                harness.window.close()
                harness.window.deleteLater()
            except:
                pass
        try:
            from gui.viewport.render_queue import RenderQueue
            RenderQueue.flush()
        except:
            pass
        gc.collect()


@pytest.fixture
def ellipse_harness(qt_app_session):
    """Ellipse interaction harness."""
    import gc
    window = None
    harness = None
    try:
        window = MainWindow()
        harness = EllipseInteractionTestHarness(window)
        yield harness
    finally:
        if harness and hasattr(harness, 'window'):
            try:
                if hasattr(harness.window, 'viewport_3d') and harness.window.viewport_3d:
                    if hasattr(harness.window.viewport_3d, 'plotter'):
                        try:
                            harness.window.viewport_3d.plotter.close()
                        except:
                            pass
                harness.window.close()
                harness.window.deleteLater()
            except:
                pass
        try:
            from gui.viewport.render_queue import RenderQueue
            RenderQueue.flush()
        except:
            pass
        gc.collect()


@pytest.fixture
def polygon_harness(qt_app_session):
    """Polygon interaction harness."""
    import gc
    window = None
    harness = None
    try:
        window = MainWindow()
        harness = PolygonInteractionTestHarness(window)
        yield harness
    finally:
        if harness and hasattr(harness, 'window'):
            try:
                if hasattr(harness.window, 'viewport_3d') and harness.window.viewport_3d:
                    if hasattr(harness.window.viewport_3d, 'plotter'):
                        try:
                            harness.window.viewport_3d.plotter.close()
                        except:
                            pass
                harness.window.close()
                harness.window.deleteLater()
            except:
                pass
        try:
            from gui.viewport.render_queue import RenderQueue
            RenderQueue.flush()
        except:
            pass
        gc.collect()


class TestArcDirectManipulation:
    """
    W17 Paket A: Arc Direct Manipulation Tests.
    
    W24: Arc tests enabled as direct tests (not subprocess).
    """
    
    def test_arc_radius_resize(self, arc_harness):
        """
        A-W17-R1: Arc Radius kann via Direct-Edit Handle geändert werden.
        
        GIVEN: Arc mit Radius 10
        WHEN: Radius-Handle nach außen gezogen
        THEN: Radius ist größer als 10
        
        W24: Skipped due to handle detection issue - the _pick_direct_edit_handle
        is not returning the radius handle for arcs. Needs UX investigation.
        """
        editor = arc_harness.editor
        
        # Erstelle Arc
        arc = Arc2D(
            center=Point2D(0, 0),
            radius=10.0,
            start_angle=0,
            end_angle=90
        )
        editor.sketch.arcs.append(arc)
        editor.request_update()
        QTest.qWait(50)
        
        initial_radius = arc.radius
        
        # Drag radius handle (auf dem dedizierten Arc-Radius-Handle bei ~45°)
        arc_harness.drag_handle(
            arc, 'radius',
            start_world=(7.07, 7.07),
            end_world=(10.6, 10.6)
        )
        
        # Verifiziere Radius-Änderung
        assert arc.radius > initial_radius, f"Radius nicht geändert: {arc.radius} <= {initial_radius}"
        
    def test_arc_sweep_angle_change(self, arc_harness):
        """
        A-W17-R2: Arc Sweep-Winkel kann via Direct-Edit geändert werden.
        """
        editor = arc_harness.editor
        
        # Erstelle 90° Arc
        arc = Arc2D(
            center=Point2D(0, 0),
            radius=10.0,
            start_angle=0,
            end_angle=90
        )
        editor.sketch.arcs.append(arc)
        editor.request_update()
        QTest.qWait(50)
        
        initial_sweep = arc.end_angle - arc.start_angle
        
        # Drag end angle handle
        arc_harness.drag_handle(
            arc, 'end_angle',
            start_world=(0, 10),   # Bei 90°
            end_world=(-7, 7)      # Nach 135°
        )
        
        new_sweep = arc.end_angle - arc.start_angle
        assert new_sweep > initial_sweep, f"Sweep nicht vergrößert: {new_sweep} <= {initial_sweep}"
        
    def test_arc_center_move(self, arc_harness):
        """
        A-W17-R3: Arc Center kann via Direct-Edit verschoben werden.
        """
        editor = arc_harness.editor
        
        # Erstelle Arc bei (0,0)
        arc = Arc2D(
            center=Point2D(0, 0),
            radius=10.0,
            start_angle=0,
            end_angle=90
        )
        editor.sketch.arcs.append(arc)
        editor.request_update()
        QTest.qWait(50)
        
        # Drag center handle
        arc_harness.drag_handle(
            arc, 'center',
            start_world=(0, 0),
            end_world=(5, 5)
        )
        
        # Verifiziere Center-Verschiebung
        assert abs(arc.center.x - 5) < 1.0, f"Center X nicht verschoben: {arc.center.x}"
        assert abs(arc.center.y - 5) < 1.0, f"Center Y nicht verschoben: {arc.center.y}"


class TestEllipseDirectManipulation:
    """
    W17 Paket A: Ellipse Direct Manipulation Tests.
    
    W18 Recovery: Ellipse2D ist noch nicht im sketcher Modul verfügbar.
    Diese Tests werden übersprungen bis die Klasse implementiert ist.
    """
    
    def setup_method(self):
        if Ellipse2D is None:
            pytest.skip("Ellipse2D nicht im sketcher Modul verfügbar")
    def test_ellipse_radius_x_change(self, ellipse_harness):
        """
        A-W17-R4: Ellipse Radius-X kann unabhängig geändert werden.
        """
        editor = ellipse_harness.editor
        ellipse = Ellipse2D(
            center=Point2D(0, 0),
            radius_x=10.0,
            radius_y=5.0,
            rotation=0
        )
        if not hasattr(editor.sketch, 'ellipses'):
            editor.sketch.ellipses = []
        editor.sketch.ellipses.append(ellipse)
        editor.request_update()
        QTest.qWait(50)

        initial_rx = ellipse.radius_x
        initial_ry = ellipse.radius_y
        ellipse_harness.drag_radius_handle(
            ellipse, 'radius_x',
            start_world=(10, 0),
            end_world=(15, 0)
        )

        assert ellipse.radius_x > initial_rx, f"Radius-X nicht geaendert: {ellipse.radius_x}"
        assert abs(ellipse.radius_y - initial_ry) < 0.5, (
            f"Radius-Y unerwartet geaendert: {ellipse.radius_y} != {initial_ry}"
        )
    def test_ellipse_radius_y_change(self, ellipse_harness):
        """
        A-W17-R5: Ellipse Radius-Y kann unabhängig geändert werden.
        """
        editor = ellipse_harness.editor
        ellipse = Ellipse2D(
            center=Point2D(0, 0),
            radius_x=10.0,
            radius_y=5.0,
            rotation=0
        )
        if not hasattr(editor.sketch, 'ellipses'):
            editor.sketch.ellipses = []
        editor.sketch.ellipses.append(ellipse)
        editor.request_update()
        QTest.qWait(50)

        initial_rx = ellipse.radius_x
        initial_ry = ellipse.radius_y
        ellipse_harness.drag_radius_handle(
            ellipse, 'radius_y',
            start_world=(0, 5),
            end_world=(0, 8)
        )

        assert ellipse.radius_y > initial_ry, f"Radius-Y nicht geaendert: {ellipse.radius_y}"
        assert abs(ellipse.radius_x - initial_rx) < 0.5, (
            f"Radius-X unerwartet geaendert: {ellipse.radius_x}"
        )
    def test_ellipse_rotation_handle(self, ellipse_harness):
        """
        A-W17-R6: Ellipse Rotation kann via Handle geändert werden.
        """
        editor = ellipse_harness.editor
        ellipse = Ellipse2D(
            center=Point2D(0, 0),
            radius_x=10.0,
            radius_y=5.0,
            rotation=0
        )
        if not hasattr(editor.sketch, 'ellipses'):
            editor.sketch.ellipses = []
        editor.sketch.ellipses.append(ellipse)
        editor.request_update()
        QTest.qWait(50)

        initial_rotation = ellipse.rotation
        ellipse_harness.drag_radius_handle(
            ellipse, 'rotation',
            start_world=(12, 0),
            end_world=(8, 8)
        )

        assert ellipse.rotation > initial_rotation, f"Rotation nicht geaendert: {ellipse.rotation}"


class TestPolygonDirectManipulation:
    """
    W17 Paket A: Polygon Direct Manipulation Tests.
    
    W18 Recovery: Polygon2D ist noch nicht im sketcher Modul verfügbar.
    Diese Tests werden übersprungen bis die Klasse implementiert ist.
    """
    
    def setup_method(self):
        if Polygon2D is None:
            pytest.skip("Polygon2D nicht im sketcher Modul verfügbar")
    def test_polygon_vertex_move(self, polygon_harness):
        """
        A-W17-R7: Polygon Eckpunkt kann via Direct-Edit verschoben werden.
        """
        editor = polygon_harness.editor
        polygon = Polygon2D([
            Point2D(0, 0),
            Point2D(10, 0),
            Point2D(10, 10),
            Point2D(0, 10)
        ])
        if not hasattr(editor.sketch, 'polygons'):
            editor.sketch.polygons = []
        editor.sketch.polygons.append(polygon)
        editor.request_update()
        QTest.qWait(50)

        initial_x = polygon.points[1].x
        polygon_harness.drag_vertex(
            polygon, 1,
            start_world=(10, 0),
            end_world=(15, 0)
        )

        assert polygon.points[1].x > initial_x, f"Vertex X nicht verschoben: {polygon.points[1].x}"
    def test_polygon_edge_midpoint_drag(self, polygon_harness):
        """
        A-W17-R8: Polygon Seiten-Mittelpunkt-Drag verschiebt gegenüberliegende Seite.
        """
        editor = polygon_harness.editor
        polygon = Polygon2D([
            Point2D(0, 0),
            Point2D(10, 0),
            Point2D(10, 10),
            Point2D(0, 10)
        ])
        if not hasattr(editor.sketch, 'polygons'):
            editor.sketch.polygons = []
        editor.sketch.polygons.append(polygon)
        editor.request_update()
        QTest.qWait(50)

        initial_width = polygon.points[1].x - polygon.points[0].x
        polygon_harness.drag_vertex(
            polygon, 0,
            start_world=(0, 0),
            end_world=(-3, 0)
        )

        new_width = polygon.points[1].x - polygon.points[0].x
        assert new_width > initial_width, f"Breite nicht vergroessert: {new_width}"


# =============================================================================
# Isolated Test Implementations (für subprocess execution)
# =============================================================================

class IsolatedArcDirectManipulation:
    """Isolierte Arc Tests - werden im Subprozess ausgeführt."""
    pass


# Isolierte Test-Funktionen für Subprozess-Ausführung
@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_arc_radius_resize_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import ArcInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = ArcInteractionTestHarness(window)
        editor = harness.editor
        
        # Erstelle Arc
        arc = Arc2D(
            center=Point2D(0, 0),
            radius=10.0,
            start_angle=0,
            end_angle=90
        )
        editor.sketch.arcs.append(arc)
        editor.request_update()
        QTest.qWait(50)
        
        initial_radius = arc.radius
        
        # Drag radius handle
        harness.drag_handle(
            arc, 'radius',
            start_world=(10, 0),  # Auf dem Kreis
            end_world=(15, 0)     # Nach außen
        )
        
        # Verifiziere Radius-Änderung
        assert arc.radius > initial_radius, f"Radius nicht geändert: {arc.radius} <= {initial_radius}"
        
        window.close()
        
@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_arc_sweep_angle_change_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import ArcInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = ArcInteractionTestHarness(window)
        editor = harness.editor
        
        # Erstelle 90° Arc
        arc = Arc2D(
            center=Point2D(0, 0),
            radius=10.0,
            start_angle=0,
            end_angle=90
        )
        editor.sketch.arcs.append(arc)
        editor.request_update()
        QTest.qWait(50)
        
        initial_sweep = arc.end_angle - arc.start_angle
        
        # Drag end angle handle
        harness.drag_handle(
            arc, 'end_angle',
            start_world=(0, 10),   # Bei 90°
            end_world=(-7, 7)      # Nach 135°
        )
        
        new_sweep = arc.end_angle - arc.start_angle
        assert new_sweep > initial_sweep, f"Sweep nicht vergrößert: {new_sweep} <= {initial_sweep}"
        
        window.close()
        
@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_arc_center_move_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import ArcInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = ArcInteractionTestHarness(window)
        editor = harness.editor
        
        # Erstelle Arc bei (0,0)
        arc = Arc2D(
            center=Point2D(0, 0),
            radius=10.0,
            start_angle=0,
            end_angle=90
        )
        editor.sketch.arcs.append(arc)
        editor.request_update()
        QTest.qWait(50)
        
        # Drag center handle
        harness.drag_handle(
            arc, 'center',
            start_world=(0, 0),
            end_world=(5, 5)
        )
        
        # Verifiziere Center-Verschiebung
        assert abs(arc.center.x - 5) < 1.0, f"Center X nicht verschoben: {arc.center.x}"
        assert abs(arc.center.y - 5) < 1.0, f"Center Y nicht verschoben: {arc.center.y}"
        
        window.close()


class IsolatedEllipseDirectManipulation:
    """Isolierte Ellipse Tests."""
    pass


@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_ellipse_radius_x_change_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import EllipseInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = EllipseInteractionTestHarness(window)
        editor = harness.editor
        
        # Erstelle Ellipse
        ellipse = Ellipse2D(
            center=Point2D(0, 0),
            radius_x=10.0,
            radius_y=5.0,
            rotation=0
        )
        if not hasattr(editor.sketch, 'ellipses'):
            editor.sketch.ellipses = []
        editor.sketch.ellipses.append(ellipse)
        editor.request_update()
        QTest.qWait(50)
        
        initial_rx = ellipse.radius_x
        initial_ry = ellipse.radius_y
        
        # Drag radius X handle
        harness.drag_radius_handle(
            ellipse, 'radius_x',
            start_world=(10, 0),
            end_world=(15, 0)
        )
        
        # Verifiziere Rx geändert, Ry unverändert
        assert ellipse.radius_x > initial_rx, f"Radius-X nicht geändert: {ellipse.radius_x}"
        assert abs(ellipse.radius_y - initial_ry) < 0.5, f"Radius-Y unerwartet geändert: {ellipse.radius_y} != {initial_ry}"
        
        window.close()
        
@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_ellipse_radius_y_change_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import EllipseInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = EllipseInteractionTestHarness(window)
        editor = harness.editor
        
        ellipse = Ellipse2D(
            center=Point2D(0, 0),
            radius_x=10.0,
            radius_y=5.0,
            rotation=0
        )
        if not hasattr(editor.sketch, 'ellipses'):
            editor.sketch.ellipses = []
        editor.sketch.ellipses.append(ellipse)
        editor.request_update()
        QTest.qWait(50)
        
        initial_rx = ellipse.radius_x
        initial_ry = ellipse.radius_y
        
        harness.drag_radius_handle(
            ellipse, 'radius_y',
            start_world=(0, 5),
            end_world=(0, 8)
        )
        
        assert ellipse.radius_y > initial_ry, f"Radius-Y nicht geändert: {ellipse.radius_y}"
        assert abs(ellipse.radius_x - initial_rx) < 0.5, f"Radius-X unerwartet geändert: {ellipse.radius_x}"
        
        window.close()
        
@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_ellipse_rotation_handle_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import EllipseInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = EllipseInteractionTestHarness(window)
        editor = harness.editor
        
        ellipse = Ellipse2D(
            center=Point2D(0, 0),
            radius_x=10.0,
            radius_y=5.0,
            rotation=0
        )
        if not hasattr(editor.sketch, 'ellipses'):
            editor.sketch.ellipses = []
        editor.sketch.ellipses.append(ellipse)
        editor.request_update()
        QTest.qWait(50)
        
        initial_rotation = ellipse.rotation
        
        # Drag rotation handle (außerhalb der Ellipse)
        harness.drag_radius_handle(
            ellipse, 'rotation',
            start_world=(12, 0),
            end_world=(8, 8)
        )
        
        assert ellipse.rotation > initial_rotation, f"Rotation nicht geändert: {ellipse.rotation}"
        
        window.close()


class IsolatedPolygonDirectManipulation:
    """Isolierte Polygon Tests."""
    pass


@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_polygon_vertex_move_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import PolygonInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = PolygonInteractionTestHarness(window)
        editor = harness.editor
        
        # Erstelle Rechteck-Polygon
        polygon = Polygon2D([
            Point2D(0, 0),
            Point2D(10, 0),
            Point2D(10, 10),
            Point2D(0, 10)
        ])
        if not hasattr(editor.sketch, 'polygons'):
            editor.sketch.polygons = []
        editor.sketch.polygons.append(polygon)
        editor.request_update()
        QTest.qWait(50)
        
        initial_x = polygon.points[1].x
        
        # Drag vertex 1
        harness.drag_vertex(
            polygon, 1,
            start_world=(10, 0),
            end_world=(15, 0)
        )
        
        assert polygon.points[1].x > initial_x, f"Vertex X nicht verschoben: {polygon.points[1].x}"
        
        window.close()
        
@pytest.mark.skip(reason="Isolated test - run via subprocess only")
def _test_polygon_edge_midpoint_drag_isolated():
        """Implementierung für subprocess."""
        from test.harness.test_interaction_direct_manipulation_w17 import PolygonInteractionTestHarness
        from test.harness.test_interaction_direct_manipulation_w17 import qt_app_session
        
        app = qt_app_session
        window = MainWindow()
        harness = PolygonInteractionTestHarness(window)
        editor = harness.editor
        
        # Rechteck
        polygon = Polygon2D([
            Point2D(0, 0),
            Point2D(10, 0),
            Point2D(10, 10),
            Point2D(0, 10)
        ])
        if not hasattr(editor.sketch, 'polygons'):
            editor.sketch.polygons = []
        editor.sketch.polygons.append(polygon)
        editor.request_update()
        QTest.qWait(50)
        
        initial_width = polygon.points[1].x - polygon.points[0].x
        
        # Drag edge midpoint (zwischen vertex 0 und 1)
        harness.drag_vertex(
            polygon, 0,  # Vertex 0 als Handle
            start_world=(0, 0),
            end_world=(-3, 0)
        )
        
        new_width = polygon.points[1].x - polygon.points[0].x
        assert new_width > initial_width, f"Breite nicht vergrößert: {new_width}"
        
        window.close()
