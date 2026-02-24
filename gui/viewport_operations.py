"""
MashCAD Viewport Operations Module
===================================

Extracted from main_window.py (AR-005: Phase 2 Split).

This module contains viewport-related operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(ViewportMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple
import numpy as np
from loguru import logger
from modeling.geometry_utils import normalize_plane_axes

from PySide6.QtCore import Qt, QTimer, QPoint

if TYPE_CHECKING:
    from modeling import Body, Document
    from gui.viewport_pyvista import PyVistaViewport


class ViewportMixin:
    """
    Mixin class containing viewport-related operations for MainWindow.
    
    This class provides:
    - View manipulation methods
    - Camera controls
    - View orientation presets
    - Body mesh updates
    - Section view operations
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # Viewport Update Methods
    # =========================================================================
    
    def _trigger_viewport_update(self):
        """Startet den Timer für das Update (Debounce)"""
        self._update_timer.start()

    def _update_viewport_all(self):
        """Aktualisiert ALLES im Viewport"""
        self._trigger_viewport_update()

    def _update_viewport_all_impl(self):
        """
        Implementierung des Viewport-Updates (wird vom Timer aufgerufen).
        
        Rendert alle Bodies, Sketches und Konstruktionsebenen.
        Performance-optimiert mit async Tessellation.
        """
        if not hasattr(self, 'viewport_3d') or not self.viewport_3d:
            return

        # Bodies rendern
        bodies_to_render = []
        for body in self.document.get_all_bodies():
            if self.viewport_3d.is_body_visible(body.id):
                bodies_to_render.append(body)

        # Sketches rendern
        visible_sketches = self.browser.get_visible_sketches()
        self.viewport_3d.set_sketches(visible_sketches)

        # Konstruktionsebenen rendern
        self._render_construction_planes()

        # Bodies async rendern für Performance
        for body in bodies_to_render:
            self._update_single_body(body)

        # Getting Started Overlay aktualisieren
        self._update_getting_started()

    def _update_single_body(self, body):
        """
        Aktualisiert einen einzelnen Body im Viewport.
        Delegiert an viewport_3d.update_single_body() für korrekte Tessellation.
        
        Args:
            body: Der zu aktualisierende Body
        """
        if not hasattr(self, 'viewport_3d') or not self.viewport_3d:
            return

        try:
            color = getattr(body, 'color', None)
            inactive = self._is_body_in_inactive_component(body)
            self.viewport_3d.update_single_body(body, color=color, inactive_component=inactive)
            if hasattr(self.viewport_3d, 'set_body_object'):
                self.viewport_3d.set_body_object(body.id, body)
        except Exception as e:
            logger.debug(f"Body update fehlgeschlagen für {body.name}: {e}")

    def _update_body_from_build123d(self, body, solid):
        """
        Aktualisiert einen Body aus einem build123d Solid und triggert Viewport-Refresh.

        Diese Methode wird von mehreren Feature-Workflows erwartet
        (Shell, Copy, Mirror, Transform etc.).
        """
        if body is None or solid is None:
            return

        body._build123d_solid = solid
        if hasattr(body, 'invalidate_mesh'):
            body.invalidate_mesh()
        self._update_single_body(body)

    def _update_body_mesh(self, body, mesh_override=None):
        """Lädt die Mesh-Daten aus dem Body-Objekt in den Viewport"""
        self._update_single_body(body)

    def _update_getting_started(self):
        """Versteckt Getting-Started Overlay wenn Dokument nicht mehr leer ist."""
        if not hasattr(self, '_getting_started_overlay'):
            return
            
        # Prüfe ob Dokument Bodies oder Sketches hat
        has_content = False

        all_bodies = []
        if hasattr(self.document, 'get_all_bodies'):
            try:
                all_bodies = list(self.document.get_all_bodies() or [])
            except Exception:
                all_bodies = []
        if not all_bodies and hasattr(self.document, 'bodies'):
            all_bodies = list(getattr(self.document, 'bodies', []) or [])
        if all_bodies:
            has_content = True

        all_sketches = []
        if hasattr(self.document, 'get_all_sketches'):
            try:
                all_sketches = list(self.document.get_all_sketches() or [])
            except Exception:
                all_sketches = []
        if not all_sketches and hasattr(self.document, 'sketches'):
            all_sketches = list(getattr(self.document, 'sketches', []) or [])
        if all_sketches:
            has_content = True

        if has_content and self._getting_started_overlay.isVisible():
            self._getting_started_overlay.hide()
    
    # =========================================================================
    # Camera Controls
    # =========================================================================
    
    def _focus_camera_on_bodies(self, bodies):
        """Fokussiert die Kamera auf die angegebenen Bodies."""
        if not hasattr(self, 'viewport_3d') or not bodies:
            return

        # Sammle alle Meshes
        meshes = []
        for body in bodies:
            mesh = self.viewport_3d.get_body_mesh(body.id)
            if mesh is not None:
                meshes.append(mesh)

        if not meshes:
            return

        # Berechne gemeinsame Bounding Box
        import pyvista as pv
        combined = pv.MultiBlock(meshes)
        center = combined.center
        length = combined.length

        # Kamera positionieren
        self.viewport_3d.plotter.camera_position = 'xy'
        self.viewport_3d.plotter.camera.focal_point = center
        self.viewport_3d.plotter.camera.position = [
            center[0],
            center[1] - length * 2,
            center[2] + length * 0.5
        ]
        self.viewport_3d.plotter.reset_camera()

    def _reset_view(self):
        """Setzt die Kamera auf die Standardansicht zurück."""
        if hasattr(self, 'viewport_3d') and hasattr(self.viewport_3d, 'plotter'):
            self.viewport_3d.plotter.camera_position = 'xy'
            self.viewport_3d.plotter.reset_camera()

    def _set_view_xy(self):
        """Setzt die Ansicht auf XY-Ebene (Top)."""
        if hasattr(self, 'viewport_3d') and hasattr(self.viewport_3d, 'plotter'):
            self.viewport_3d.plotter.view_xy()

    def _set_view_xz(self):
        """Setzt die Ansicht auf XZ-Ebene (Front)."""
        if hasattr(self, 'viewport_3d') and hasattr(self.viewport_3d, 'plotter'):
            self.viewport_3d.plotter.view_xz()

    def _set_view_yz(self):
        """Setzt die Ansicht auf YZ-Ebene (Right)."""
        if hasattr(self, 'viewport_3d') and hasattr(self.viewport_3d, 'plotter'):
            self.viewport_3d.plotter.view_yz()

    def _set_view_isometric(self):
        """Setzt die Ansicht auf Isometrisch."""
        if hasattr(self, 'viewport_3d') and hasattr(self.viewport_3d, 'plotter'):
            self.viewport_3d.plotter.view_isometric()

    def _zoom_to_fit(self):
        """Zoomt so dass alle Objekte sichtbar sind."""
        if hasattr(self, 'viewport_3d') and hasattr(self.viewport_3d, 'plotter'):
            self.viewport_3d.plotter.reset_camera()
    
    # =========================================================================
    # Section View Operations
    # =========================================================================
    
    def _toggle_section_view(self):
        """Toggle section view on/off."""
        if not hasattr(self, 'section_panel'):
            return

        if self.section_panel.isVisible():
            self.section_panel.hide()
            self._on_section_disabled()
        else:
            self.section_panel.show_at(self.viewport_3d)
            self._on_section_enabled('XY', 0.0)

    def _on_section_enabled(self, plane: str, position: float):
        """Section View wurde aktiviert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.enable_section_view(plane, position)

    def _on_section_disabled(self):
        """Section View wurde deaktiviert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.disable_section_view()

    def _on_section_position_changed(self, position: float):
        """Section Position wurde geändert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.update_section_position(position)

    def _on_section_plane_changed(self, plane: str):
        """Section Plane wurde geändert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.update_section_plane(plane)

    def _on_section_invert_toggled(self):
        """Section Seite wurde invertiert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.toggle_section_invert()
    
    # =========================================================================
    # Body Visibility
    # =========================================================================
    
    def _on_body_opacity_changed(self, body_id: str, opacity: float):
        """
        Handler für Opacity-Änderung aus dem Properties-Panel.
        
        Args:
            body_id: ID des Bodies
            opacity: Neue Opacity (0.0 - 1.0)
        """
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.set_body_opacity(body_id, opacity)

    def _hide_body(self, body_id: str):
        """Versteckt einen Body."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.set_body_visible(body_id, False)

    def _show_body(self, body_id: str):
        """Zeigt einen Body."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.set_body_visible(body_id, True)

    def _show_all_bodies(self):
        """Zeigt alle Bodies."""
        if hasattr(self, 'viewport_3d'):
            for body in self.document.get_all_bodies():
                self.viewport_3d.set_body_visible(body.id, True)
            self._trigger_viewport_update()

    def _hide_all_bodies(self):
        """Versteckt alle Bodies."""
        if hasattr(self, 'viewport_3d'):
            for body in self.document.get_all_bodies():
                self.viewport_3d.set_body_visible(body.id, False)
            self._trigger_viewport_update()
    
    # =========================================================================
    # Panel Positioning
    # =========================================================================
    
    def _position_extrude_panel(self):
        """Positioniert das Extrude-Panel rechts mittig im Viewport."""
        if hasattr(self, 'extrude_panel') and self.extrude_panel.isVisible():
            self.extrude_panel.adjustSize()
            pw = self.extrude_panel.width()
            ph = self.extrude_panel.height()

            if hasattr(self, 'viewport_3d') and self.viewport_3d:
                vg = self.viewport_3d.geometry()
                top_left = self.viewport_3d.mapTo(self, QPoint(0, 0))
                area_x, area_y, area_w, area_h = top_left.x(), top_left.y(), vg.width(), vg.height()
            else:
                area_x, area_y, area_w, area_h = 0, 0, self.width(), self.height()

            margin = 12
            x = area_x + area_w - pw - margin
            y = area_y + (area_h - ph) // 2

            # Position links vom Transform-Panel oder Transform-Toolbar
            if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
                x = min(x, self.transform_panel.x() - pw - margin)
                y = self.transform_panel.y() + (self.transform_panel.height() - ph) // 2
            if hasattr(self, 'transform_toolbar') and self.transform_toolbar.isVisible():
                tb_pos = self.transform_toolbar.mapTo(self, QPoint(0, 0))
                x = min(x, tb_pos.x() - pw - margin)

            x = max(area_x + margin, min(x, area_x + area_w - pw - margin))
            y = max(area_y + margin, min(y, area_y + area_h - ph - margin))

            self.extrude_panel.move(x, y)
            self.extrude_panel.raise_()

    def _position_transform_panel(self):
        """Positioniert das Transform-Panel rechts mittig im Viewport."""
        if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
            self.transform_panel.adjustSize()
            pw = self.transform_panel.width()
            ph = self.transform_panel.height()

            if hasattr(self, 'viewport_3d') and self.viewport_3d:
                vg = self.viewport_3d.geometry()
                top_left = self.viewport_3d.mapTo(self, QPoint(0, 0))
                area_x, area_y, area_w, area_h = top_left.x(), top_left.y(), vg.width(), vg.height()
            else:
                area_x, area_y, area_w, area_h = 0, 0, self.width(), self.height()

            margin = 12
            x = area_x + area_w - pw - margin
            y = area_y + (area_h - ph) // 2

            if hasattr(self, 'transform_toolbar') and self.transform_toolbar.isVisible():
                tb_pos = self.transform_toolbar.mapTo(self, QPoint(0, 0))
                x = min(x, tb_pos.x() - pw - margin)

            x = max(area_x + margin, min(x, area_x + area_w - pw - margin))
            y = max(area_y + margin, min(y, area_y + area_h - ph - margin))

            self.transform_panel.move(x, y)
            self.transform_panel.raise_()

    def _position_transform_toolbar(self):
        """Positioniert die Transform-Toolbar rechts im Viewport, vertikal zentriert."""
        if hasattr(self, 'transform_toolbar') and hasattr(self, 'viewport_3d'):
            vw = self.viewport_3d.width()
            vh = self.viewport_3d.height()
            tw = self.transform_toolbar.width()
            th = self.transform_toolbar.height()
            x = vw - tw - 8
            y = (vh - th) // 2
            self.transform_toolbar.move(x, y)
            self.transform_toolbar.raise_()
    
    def _reposition_all_panels(self):
        """Repositioniert alle Panels nach Window-Resize."""
        self._position_extrude_panel()
        self._position_transform_panel()
        self._position_transform_toolbar()
        self._reposition_notifications()
        if hasattr(self, '_getting_started_overlay') and self._getting_started_overlay.isVisible():
            self._getting_started_overlay.center_on_parent()
        if hasattr(self, "p2p_panel") and self.p2p_panel.isVisible():
            self.p2p_panel.show_at(self.viewport_3d)
        if hasattr(self, "measure_panel") and self.measure_panel.isVisible():
            self.measure_panel.show_at(self.viewport_3d)
        if hasattr(self, "section_panel") and self.section_panel.isVisible():
            if hasattr(self.section_panel, "clamp_to_parent"):
                self.section_panel.clamp_to_parent()
    
    # =========================================================================
    # Mode Switching
    # =========================================================================
    
    def _set_mode(self, mode):
        """
        Wechselt zwischen 3D- und Sketch-Modus.
        
        Args:
            mode: "3d" oder "sketch"
        """
        if mode == self.mode:
            return

        self.mode = mode

        if mode == "3d":
            self.center_stack.setCurrentIndex(0)  # 3D Viewport
            self.tool_stack.setCurrentIndex(0)    # 3D Tool Panel
            self.right_stack.setCurrentIndex(0)   # 3D Properties
            self.statusBar().showMessage("3D-Modus")
            
        elif mode == "sketch":
            self.center_stack.setCurrentIndex(1)  # Sketch Editor
            self.tool_stack.setCurrentIndex(1)    # 2D Tool Panel
            self.right_stack.setCurrentIndex(1)   # 2D Properties
            self.statusBar().showMessage("Sketch-Modus")
            self.sketch_editor.setFocus()

    def _set_mode_fallback(self, mode):
        """
        Fallback für Mode-Switching ohne UI-Stack.
        """
        self.mode = mode
        logger.info(f"Modus gewechselt zu: {mode}")
    
    # =========================================================================
    # Transform Operations
    # =========================================================================
    
    def _on_body_transform_requested(self, body_ids, mode: str, data):
        """
        Handler für Transform-Requests von Bodies.
        
        Args:
            body_ids: Einzelne ID oder Liste von Body-IDs
            mode: Transform-Modus ("move", "rotate", "scale")
            data: Transform-Daten (Vektor, Winkel, Faktor)
        """
        # Normalisiere zu Liste
        if isinstance(body_ids, str):
            body_ids = [body_ids]

        for body_id in body_ids:
            body = self.document.find_body_by_id(body_id)
            if not body:
                logger.warning(f"Body nicht gefunden: {body_id}")
                continue

            # Führe Transformation durch
            if mode == "move":
                self._apply_move(body, data)
            elif mode == "rotate":
                self._apply_rotate(body, data)
            elif mode == "scale":
                self._apply_scale(body, data)

        # Viewport aktualisieren
        self._trigger_viewport_update()

    def _apply_move(self, body, data):
        """Wendet eine Verschiebung auf einen Body an."""
        from modeling import TransformFeature
        
        dx, dy, dz = data.get('translation', (0, 0, 0))
        
        feature = TransformFeature(
            type='translate',
            translation=(dx, dy, dz)
        )
        body.add_feature(feature)
        body._rebuild()

    def _apply_rotate(self, body, data):
        """Wendet eine Rotation auf einen Body an."""
        from modeling import TransformFeature
        
        axis = data.get('axis', (0, 0, 1))
        angle = data.get('angle', 0)
        origin = data.get('origin', (0, 0, 0))
        
        feature = TransformFeature(
            type='rotate',
            axis=axis,
            angle=angle,
            origin=origin
        )
        body.add_feature(feature)
        body._rebuild()

    def _apply_scale(self, body, data):
        """Wendet eine Skalierung auf einen Body an."""
        from modeling import TransformFeature
        
        factor = data.get('factor', 1.0)
        origin = data.get('origin', (0, 0, 0))
        
        feature = TransformFeature(
            type='scale',
            factor=factor,
            origin=origin
        )
        body.add_feature(feature)
        body._rebuild()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _calculate_plane_axes(self, normal_vec):
        """
        Berechnet stabile X- und Y-Achsen für eine Ebene basierend auf der Normalen.
        Muss IDENTISCH zu viewport_pyvista.py sein!
        """
        _normal, x_dir, y_dir = normalize_plane_axes(normal_vec)
        return x_dir, y_dir
    
    def _find_component_for_body(self, body):
        """Findet die Component die einen Body enthält."""
        if not hasattr(self.document, '_assembly_enabled'):
            return None
            
        def search_component(comp):
            if body in comp.bodies:
                return comp
            for child in comp.children:
                result = search_component(child)
                if result:
                    return result
            return None

        return search_component(self.document.root_component)
    
    def _is_body_in_inactive_component(self, body) -> bool:
        """Prüft ob Body zu einer inaktiven Component gehört (Assembly-System)."""
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return False
            
        comp = self._find_component_for_body(body)
        if comp is None:
            return False
            
        active = self.document._active_component
        if active is None:
            return False
            
        # Body ist inaktiv wenn es nicht in der aktiven Component oder einer ihrer Kinder ist
        def is_ancestor_of(potential_ancestor, component):
            while component:
                if component == potential_ancestor:
                    return True
                component = component.parent
            return False

        return not is_ancestor_of(active, comp)
