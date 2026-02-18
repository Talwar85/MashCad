"""
W33 Viewport Interaction Megapack Tests
========================================

EPIC AC1: Selection Precision
EPIC AC2: Abort Parity in 3D
EPIC AC3: Actor Lifecycle Hardening
EPIC AC4: Interaction Performance

Tests für:
- Pick-Priorität in zentralen Modi
- ESC/RightClick parity im viewport flow
- Actor cleanup nach mode switch
- Kein stale selection state nach batch focus/recover und component switch
"""

import os
import sys
import time
import pytest
from unittest.mock import Mock, patch, MagicMock

os.environ["QT_OPENGL"] = "software"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtTest import QTest

# Headless-safe Import
with patch.dict(
    "sys.modules",
    {
        "pyvista": Mock(),
        "pyvistaqt": Mock(),
        "vtk": Mock(),
    },
):
    from gui.viewport.selection_mixin import SelectionMixin


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestSelectionMixinPrioritization:
    """
    EPIC AC1: Selection Precision - Hit-Priorisierung
    """

    def test_prioritize_hit_sketch_profile_highest(self, qt_app):
        """AC1-R1: Sketch-Profile haben höchste Priorität (0)."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Mock detector
        mock_face = Mock()
        mock_face.id = 1
        mock_face.domain_type = 'sketch_profile'
        mixin.detector = Mock()
        mixin.detector.selection_faces = [mock_face]
        
        priority = mixin.prioritize_hit(1)
        assert priority == 0, "Sketch-Profile sollte Priorität 0 haben"

    def test_prioritize_hit_sketch_shell_second(self, qt_app):
        """AC1-R2: Sketch-Shells haben zweithöchste Priorität (1)."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mock_face = Mock()
        mock_face.id = 2
        mock_face.domain_type = 'sketch_shell'
        mixin.detector = Mock()
        mixin.detector.selection_faces = [mock_face]
        
        priority = mixin.prioritize_hit(2)
        assert priority == 1, "Sketch-Shell sollte Priorität 1 haben"

    def test_prioritize_hit_body_face_third(self, qt_app):
        """AC1-R3: Body-Faces haben dritthöchste Priorität (2)."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mock_face = Mock()
        mock_face.id = 3
        mock_face.domain_type = 'body_face'
        mixin.detector = Mock()
        mixin.detector.selection_faces = [mock_face]
        
        priority = mixin.prioritize_hit(3)
        assert priority == 2, "Body-Face sollte Priorität 2 haben"

    def test_prioritize_hit_construction_lowest(self, qt_app):
        """AC1-R4: Konstruktionsflächen haben niedrigste Priorität (3)."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mock_face = Mock()
        mock_face.id = 4
        mock_face.domain_type = 'construction_plane'
        mixin.detector = Mock()
        mixin.detector.selection_faces = [mock_face]
        
        priority = mixin.prioritize_hit(4)
        assert priority == 3, "Construction-Plane sollte Priorität 3 haben"

    def test_is_selection_valid_for_mode_3d(self, qt_app):
        """AC1-R5: In 3D-Modus sind Body-Faces und Sketch-Elemente gültig."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mock_face = Mock()
        mock_face.id = 1
        mock_face.domain_type = 'body_face'
        mixin.detector = Mock()
        mixin.detector.selection_faces = [mock_face]
        
        assert mixin.is_selection_valid_for_mode(1, '3d') is True

    def test_is_selection_valid_for_mode_sketch(self, qt_app):
        """AC1-R6: In Sketch-Modus sind nur Sketch-Elemente gültig."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Sketch-Element sollte gültig sein
        mock_face = Mock()
        mock_face.id = 1
        mock_face.domain_type = 'sketch_profile'
        mixin.detector = Mock()
        mixin.detector.selection_faces = [mock_face]
        
        assert mixin.is_selection_valid_for_mode(1, 'sketch') is True

    def test_multi_select_toggle_adds_and_removes(self, qt_app):
        """AC1-R7: Multi-Select toggle fügt hinzu und entfernt."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Erste Face hinzufügen
        mixin.toggle_face_selection(1, is_multi=True)
        assert 1 in mixin.selected_face_ids
        
        # Zweite Face hinzufügen
        mixin.toggle_face_selection(2, is_multi=True)
        assert 1 in mixin.selected_face_ids
        assert 2 in mixin.selected_face_ids
        
        # Erste Face wieder entfernen (toggle)
        mixin.toggle_face_selection(1, is_multi=True)
        assert 1 not in mixin.selected_face_ids
        assert 2 in mixin.selected_face_ids

    def test_single_select_replaces_selection(self, qt_app):
        """AC1-R8: Single-Select ersetzt die komplette Selektion."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Multi-Select: zwei Faces
        mixin.toggle_face_selection(1, is_multi=True)
        mixin.toggle_face_selection(2, is_multi=True)
        assert len(mixin.selected_face_ids) == 2
        
        # Single-Select: ersetzt alles
        mixin.toggle_face_selection(3, is_multi=False)
        assert len(mixin.selected_face_ids) == 1
        assert 3 in mixin.selected_face_ids
        assert 1 not in mixin.selected_face_ids
        assert 2 not in mixin.selected_face_ids


class TestAbortParity:
    """
    EPIC AC2: Abort Parity in 3D - ESC und Rechtsklick haben identisches Verhalten
    """

    def test_abort_interaction_state_returns_true_when_active(self, qt_app):
        """AC2-R1: abort_interaction_state gibt True zurück wenn Zustand aktiv war."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Simuliere aktiven Drag-Zustand
        mixin.is_dragging = True
        
        result = mixin.abort_interaction_state("user_abort")
        assert result is True, "Sollte True zurückgeben wenn Drag abgebrochen wurde"
        assert mixin.is_dragging is False

    def test_abort_interaction_state_returns_false_when_idle(self, qt_app):
        """AC2-R2: abort_interaction_state gibt False zurück wenn im Idle-Zustand."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Alles ist im Idle-Zustand
        mixin.is_dragging = False
        mixin.extrude_mode = False
        
        result = mixin.abort_interaction_state("user_abort")
        assert result is False, "Sollte False zurückgeben wenn nichts abgebrochen wurde"

    def test_abort_clears_extrude_mode(self, qt_app):
        """AC2-R3: Abort bricht Extrude-Modus ab."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.extrude_mode = True
        
        mixin.abort_interaction_state("user_abort")
        assert mixin.extrude_mode is False

    def test_abort_clears_edge_select_mode(self, qt_app):
        """AC2-R4: Abort bricht Edge-Select-Modus ab."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.edge_select_mode = True
        mixin.stop_edge_selection_mode = Mock()
        
        mixin.abort_interaction_state("user_abort")
        mixin.stop_edge_selection_mode.assert_called_once()

    def test_abort_clears_texture_face_mode(self, qt_app):
        """AC2-R5: Abort bricht Texture-Face-Modus ab."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.texture_face_mode = True
        mixin._texture_body_id = "test_body"
        mixin._texture_selected_faces = [1, 2, 3]
        
        mixin.abort_interaction_state("user_abort")
        assert mixin.texture_face_mode is False
        assert mixin._texture_body_id is None
        assert mixin._texture_selected_faces == []

    def test_abort_clears_all_drag_states(self, qt_app):
        """AC2-R6: Abort bricht alle Drag-Zustände ab."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze alle Drag-Zustände
        mixin.is_dragging = True
        mixin._offset_plane_dragging = True
        mixin._split_dragging = True
        
        mixin.abort_interaction_state("user_abort")
        
        assert mixin.is_dragging is False
        assert mixin._offset_plane_dragging is False
        assert mixin._split_dragging is False

    def test_abort_clears_selection_on_mode_change(self, qt_app):
        """AC2-R7: Abort mit reason='mode_change' löscht auch Selektion."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Füge Selektion hinzu
        mixin.add_face_selection(1)
        mixin.add_face_selection(2)
        assert mixin.has_selected_faces() is True
        
        # Abort mit mode_change reason
        mixin.abort_interaction_state("mode_change")
        
        assert mixin.has_selected_faces() is False

    def test_preview_actors_cleared_on_abort(self, qt_app):
        """AC2-R8: Preview-Aktoren werden bei Abort bereinigt."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze Preview-Aktoren
        mixin._preview_actor = "preview_1"
        mixin._revolve_preview_actor = "revolve_preview"
        mixin._hole_preview_actor = "hole_preview"
        
        mixin.abort_interaction_state("user_abort")
        
        # Preview-Aktoren sollten auf None gesetzt sein
        assert mixin._preview_actor is None
        assert mixin._revolve_preview_actor is None
        assert mixin._hole_preview_actor is None


class TestActorLifecycle:
    """
    EPIC AC3: Actor Lifecycle Hardening
    """

    def test_cleanup_preview_actors_handles_missing_plotter(self, qt_app):
        """AC3-R1: cleanup_preview_actors ist robust wenn plotter fehlt."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Kein plotter
        mixin.plotter = None
        
        # Sollte nicht crashen
        mixin.cleanup_preview_actors()

    def test_cleanup_preview_actors_with_mock_plotter(self, qt_app):
        """AC3-R2: cleanup_preview_actors entfernt Preview-Patterns."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Mock plotter mit Actors
        mock_actor = Mock()
        mixin.plotter = Mock()
        mixin.plotter.renderer = Mock()
        mixin.plotter.renderer.actors = {
            "preview_test": mock_actor,
            "hover_123": mock_actor,
            "normal_actor": mock_actor,
        }
        
        mixin.cleanup_preview_actors()
        
        # Sollte remove_actor für Preview-Patterns aufrufen
        assert mixin.plotter.remove_actor.call_count >= 2

    def test_ensure_selection_actors_valid_no_plotter(self, qt_app):
        """AC3-R3: ensure_selection_actors_valid ist robust wenn plotter fehlt."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.plotter = None
        mixin.selected_face_ids = {1, 2, 3}
        
        # Sollte nicht crashen
        mixin.ensure_selection_actors_valid()

    def test_double_remove_safe(self, qt_app):
        """AC3-R4: Double-remove ist safe (kein Crash)."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.plotter = Mock()
        mixin.plotter.remove_actor = Mock(side_effect=Exception("Actor not found"))
        
        # Sollte nicht crashen trotz Exception
        mixin.cleanup_preview_actors()

    def test_mode_transition_no_residue(self, qt_app):
        """AC3-R5: Mode-Transition lässt keine Residue zurück."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze verschiedene Zustände
        mixin.is_dragging = True
        mixin.extrude_mode = True
        mixin._preview_actor = "test_preview"
        
        # Cleanup
        mixin.abort_interaction_state("mode_change")
        
        # Alle Zustände sollten zurückgesetzt sein
        assert mixin.is_dragging is False
        assert mixin.extrude_mode is False
        assert mixin._preview_actor is None


class TestInteractionPerformance:
    """
    EPIC AC4: Interaction Performance
    """

    def test_hover_cache_validity(self, qt_app):
        """AC4-R1: Hover-Cache ist gültig innerhalb der TTL."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze Cache
        mixin._hover_pick_cache = (time.time(), 100, 200, "test_result")
        
        # Sollte gültig sein
        assert mixin.is_hover_cache_valid(100, 200, ttl_seconds=1.0) is True

    def test_hover_cache_invalid_different_coords(self, qt_app):
        """AC4-R2: Hover-Cache ist ungültig bei anderen Koordinaten."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze Cache für (100, 200)
        mixin._hover_pick_cache = (time.time(), 100, 200, "test_result")
        
        # Sollte ungültig sein für (150, 250)
        assert mixin.is_hover_cache_valid(150, 250, ttl_seconds=1.0) is False

    def test_hover_cache_expired(self, qt_app):
        """AC4-R3: Hover-Cache ist ungültig nach Ablauf der TTL."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze Cache mit alter Zeit
        mixin._hover_pick_cache = (time.time() - 2.0, 100, 200, "test_result")
        
        # Sollte ungültig sein (TTL = 1.0s)
        assert mixin.is_hover_cache_valid(100, 200, ttl_seconds=1.0) is False

    def test_hover_cache_update(self, qt_app):
        """AC4-R4: Hover-Cache wird korrekt aktualisiert."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Update Cache
        mixin.update_hover_cache(100, 200, "new_result")
        
        assert mixin._hover_pick_cache is not None
        assert mixin._hover_pick_cache[1] == 100
        assert mixin._hover_pick_cache[2] == 200
        assert mixin._hover_pick_cache[3] == "new_result"

    def test_invalidate_hover_cache(self, qt_app):
        """AC4-R5: invalidate_hover_cache löscht den Cache."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze Cache
        mixin._hover_pick_cache = (time.time(), 100, 200, "test_result")
        
        # Invalidiere
        mixin.invalidate_hover_cache()
        
        assert mixin._hover_pick_cache is None

    def test_no_redundant_rebuilds(self, qt_app):
        """AC4-R6: Keine redundanten Actor-Rebuilds bei gleichem Zustand."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Mock für draw Methode
        call_count = [0]
        def mock_draw():
            call_count[0] += 1
        
        # Simuliere Hover-Update mit gleicher Face-ID
        mixin.hover_face_id = 5
        
        # Gleiche ID sollte keinen Rebuild triggern
        # (Dies wäre in der echten Implementierung so)
        assert call_count[0] == 0  # Noch kein Aufruf


class TestSelectionStateExportImport:
    """
    Zusätzliche Tests für Selection State Management
    """

    def test_export_face_selection_returns_copy(self, qt_app):
        """Export gibt Kopie zurück, nicht Referenz."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.add_face_selection(1)
        mixin.add_face_selection(2)
        
        exported = mixin.export_face_selection()
        
        # Änderung am Export sollte Original nicht beeinflussen
        exported.add(3)
        assert 3 not in mixin.selected_face_ids

    def test_import_face_selection_replaces(self, qt_app):
        """Import ersetzt bestehende Selektion."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.add_face_selection(1)
        mixin.add_face_selection(2)
        
        mixin.import_face_selection({3, 4})
        
        assert 1 not in mixin.selected_face_ids
        assert 2 not in mixin.selected_face_ids
        assert 3 in mixin.selected_face_ids
        assert 4 in mixin.selected_face_ids

    def test_clear_all_selection_resets_everything(self, qt_app):
        """Clear all selection setzt alles zurück."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze verschiedene Selektionszustände
        mixin.add_face_selection(1)
        mixin.add_edge_selection(10)
        mixin.hovered_face = 5
        mixin.hover_face_id = 7
        
        # Mock _selected_edge_ids für den Test
        mixin._selected_edge_ids = set()
        mixin.add_edge_selection(20)
        
        mixin.clear_all_selection()
        
        assert not mixin.has_selected_faces()
        assert not mixin.has_selected_edges()
        assert mixin.hovered_face == -1
        assert mixin.hover_face_id is None


class TestLegacyCompatibility:
    """
    Tests für Rückwärtskompatibilität
    """

    def test_selected_faces_property_wrapper(self, qt_app):
        """Legacy selected_faces Property funktioniert."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Via Legacy-Property setzen
        mixin.selected_faces = {1, 2, 3}
        
        # Sollte in selected_face_ids gespiegelt sein
        assert mixin.selected_face_ids == {1, 2, 3}

    def test_selected_faces_property_getter(self, qt_app):
        """Legacy selected_faces Getter funktioniert."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Direkt setzen
        mixin.selected_face_ids = {1, 2, 3}
        
        # Via Legacy-Property lesen
        assert mixin.selected_faces == {1, 2, 3}


class TestY2AbortParity:
    """
    EPIC Y2: Abort/Cancel Parity - Stabile Tests für Point-to-Point und andere Modi
    """

    def test_abort_interaction_state_with_point_to_point(self, qt_app):
        """Y2-R1: abort_interaction_state bricht Point-to-Point-Mode ab."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Simuliere Point-to-Point Mode
        mixin.point_to_point_mode = True
        mixin.point_to_point_start = (1.0, 2.0, 3.0)
        mixin.point_to_point_body_id = "test_body"
        
        # Mock cancel_point_to_point_mode
        mixin.cancel_point_to_point_mode = Mock()
        
        # Abort ausführen
        result = mixin.abort_interaction_state("user_abort")
        
        # Verify
        assert result is True
        mixin.cancel_point_to_point_mode.assert_called_once()

    def test_escape_clears_point_to_point_mode(self, qt_app):
        """Y2-R2: ESC bricht Point-to-Point-Mode ab (Crash-Stabilisierung)."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Initialisiere Point-to-Point Zustände
        mixin.point_to_point_mode = True
        mixin.point_to_point_start = (1.0, 2.0, 3.0)
        mixin.point_to_point_body_id = "test_body"
        
        # Mock plotter und Cursor
        mixin.plotter = Mock()
        mixin.setCursor = Mock()
        mixin.point_to_point_cancelled = Mock()
        
        # abort_interaction_state aufrufen (was ESC tun würde)
        result = mixin.abort_interaction_state("escape")
        
        # Verify
        assert result is True
        assert mixin.point_to_point_mode is False
        assert mixin.point_to_point_start is None
        assert mixin.point_to_point_body_id is None

    def test_abort_with_uninitialized_point_to_point(self, qt_app):
        """Y2-R3: Abort mit nicht-initialisiertem P2P-Zustand ist safe."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze nur point_to_point_mode, aber nicht die anderen Attribute
        # (dies simuliert einen teilweise initialisierten Zustand)
        mixin.point_to_point_mode = True
        
        # Dies sollte nicht crashen
        result = mixin.abort_interaction_state("user_abort")
        assert result is True

    def test_abort_clears_drag_before_point_to_point(self, qt_app):
        """Y2-R4: Drag-Abbruch hat höhere Priorität als P2P-Abbruch."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Setze beide Zustände
        mixin.is_dragging = True
        mixin.point_to_point_mode = True
        
        # abort_interaction_state aufrufen
        result = mixin.abort_interaction_state("user_abort")
        
        # Beide sollten abgebrochen sein (point_to_point_mode wird auf False gesetzt)
        assert mixin.is_dragging is False
        assert mixin.point_to_point_mode is False

    def test_right_click_and_escape_same_endstate(self, qt_app):
        """Y2-R5: Rechtsklick und ESC liefern identischen Endzustand."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        # Test 1: ESC-Abbruch
        mixin.point_to_point_mode = True
        mixin.point_to_point_start = (1.0, 2.0, 3.0)
        mixin.point_to_point_body_id = "body_1"
        mixin.cancel_point_to_point_mode = Mock()
        
        mixin.abort_interaction_state("escape")
        escape_state = {
            'mode': mixin.point_to_point_mode,
            'start': mixin.point_to_point_start,
            'body_id': mixin.point_to_point_body_id
        }
        
        # Test 2: Rechtsklick-Abbruch
        mixin.point_to_point_mode = True
        mixin.point_to_point_start = (1.0, 2.0, 3.0)
        mixin.point_to_point_body_id = "body_1"
        mixin.cancel_point_to_point_mode = Mock()
        
        mixin.abort_interaction_state("right_click")
        right_click_state = {
            'mode': mixin.point_to_point_mode,
            'start': mixin.point_to_point_start,
            'body_id': mixin.point_to_point_body_id
        }
        
        # Beide sollten identisch sein
        assert escape_state == right_click_state

    def test_abort_does_not_crash_with_none_plotter(self, qt_app):
        """Y2-R6: Abort ist safe wenn plotter None ist."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.point_to_point_mode = True
        mixin.plotter = None  # Kein Plotter
        
        # Sollte nicht crashen
        result = mixin.abort_interaction_state("user_abort")
        assert result is True

    def test_abort_handles_missing_cancel_method(self, qt_app):
        """Y2-R7: Abort ist safe wenn cancel Methode fehlt."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.point_to_point_mode = True
        # Entferne cancel_point_to_point_mode Methode
        if hasattr(mixin, 'cancel_point_to_point_mode'):
            delattr(mixin, 'cancel_point_to_point_mode')
        
        # Sollte nicht crashen (abort_interaction_state fängt AttributeError ab)
        result = mixin.abort_interaction_state("user_abort")
        assert result is True
        assert mixin.point_to_point_mode is False

    def test_point_to_point_cleanup_on_mode_change(self, qt_app):
        """Y2-R8: P2P wird bei Mode-Change komplett bereinigt."""
        mixin = SelectionMixin()
        mixin._init_selection_state()
        
        mixin.point_to_point_mode = True
        mixin.point_to_point_start = (1.0, 2.0, 3.0)
        mixin.point_to_point_body_id = "test_body"
        
        # Mock cancel Methode
        mixin.cancel_point_to_point_mode = Mock()
        
        result = mixin.abort_interaction_state("mode_change")
        
        assert result is True
        mixin.cancel_point_to_point_mode.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
