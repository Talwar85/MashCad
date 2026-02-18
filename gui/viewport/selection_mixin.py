"""
Unified Selection Mixin (Paket B: Selection-State Konsolidierung)
================================================================

Provides single source of truth for face and edge selection.

W33 EPIC Y1-Y4: Viewport Interaction Stability
- Hit-Priorisierung für präzise Auswahl
- Abort/Cancel Parity für konsistentes Verhalten
- Actor Lifecycle Management
- Performance-Optimierungen

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Author: Claude (AI-LARGE-Y) - W33 EPIC Y1-Y4
Date: 2026-02-16 / 2026-02-17
Branch: feature/v1-ux-aiB
"""

from typing import Set, List, Tuple, Any, Optional
from loguru import logger


class SelectionMixin:
    """
    Unified Selection API for Face and Edge Selection (Paket B).

    Single Source of Truth:
    - selected_face_ids: Set of face IDs (TNP v4 shape IDs)
    - selected_edge_ids: Set of edge IDs (TNP v4 edge IDs)

    Legacy Compatibility:
    - selected_faces: Property wrapper (deprecated but functional)
    - selected_edges: Property wrapper (deprecated but functional)
    """

    # ========================================================================
    # Phase 1: Single Source of Truth Attributes
    # ========================================================================

    def _init_selection_state(self):
        """
        Initialisiert die unified selection state.
        Muss im __init__ des Viewports aufgerufen werden.
        """
        # Single Source of Truth für Faces (TNP v4 Shape IDs)
        self.selected_face_ids: Set[int] = set()

        # Single Source of Truth für Edges (TNP v4 Edge IDs)
        # Wir nutzen _selected_edge_ids aus edge_selection_mixin
        self.selected_edge_ids: Set[int] = set()

        # Legacy compatibility flags
        self._legacy_selected_faces: Set[int] = set()
        self._legacy_selected_edges: List[Any] = []

        logger.debug("[SelectionMixin] Unified selection state initialized")

    # ========================================================================
    # Phase 2: Legacy Property Wrappers (Rückwärtskompatibilität)
    # ========================================================================

    @property
    def selected_faces(self) -> Set[int]:
        """
        Legacy wrapper für selected_faces (Index-basiert → ID-basiert).

        DEPRECATED: Bitte selected_face_ids verwenden.
        """
        # Legacy-First: Falls ein legacy-Set aktiv gepflegt wird (z. B. String-IDs
        # aus älteren UI-Tests), dieses zurückgeben. Sonst auf TNP-v4 IDs fallen.
        return self._legacy_selected_faces if self._legacy_selected_faces else self.selected_face_ids

    @selected_faces.setter
    def selected_faces(self, value: Any) -> None:
        """
        Legacy setter für selected_faces.

        DEPRECATED: Bitte selected_face_ids verwenden.
        """
        # Konvertiere verschiedene Input-Typen zu Set
        if isinstance(value, set):
            values = set(value)
        elif isinstance(value, (list, tuple)):
            values = set(value)
        else:
            logger.warning(f"[SelectionMixin] Unexpected type for selected_faces: {type(value)}")
            values = set()

        self._legacy_selected_faces = set(values)

        # Nur numerische IDs in den TNP-v4 State spiegeln.
        # Nicht-numerische Legacy-Werte (z. B. "face_1") bleiben separat erhalten.
        if all(isinstance(v, int) for v in values):
            self.selected_face_ids = set(values)

    @property
    def selected_edges(self) -> List[Any]:
        """
        Legacy wrapper für selected_edges (VTK Objects → IDs).

        DEPRECATED: Bitte selected_edge_ids oder edge_selection_mixin verwenden.
        """
        return self._legacy_selected_edges

    @selected_edges.setter
    def selected_edges(self, value: List[Any]) -> None:
        """
        Legacy setter für selected_edges.

        DEPRECATED: Bitte selected_edge_ids verwenden.
        """
        self._legacy_selected_edges = list(value)

    # ========================================================================
    # Phase 3: Unified Clear Operations
    # ========================================================================

    def clear_face_selection(self) -> None:
        """
        Cleart die Face-Selektion (unified).

        Diese Methode sollte anstelle von direktem clear() aufgerufen werden.
        """
        self.selected_face_ids.clear()
        self._legacy_selected_faces.clear()

        # Auch detected_faces interactors clearen
        if hasattr(self, '_face_actors'):
            self._face_actors.clear()
        if hasattr(self, 'detected_faces'):
            self.detected_faces.clear()

        logger.debug("[SelectionMixin] Face selection cleared")

    def clear_edge_selection(self) -> None:
        """
        Cleart die Edge-Selektion (unified).

        Diese Methode sollte anstelle von direktem clear() aufgerufen werden.
        """
        self.selected_edge_ids.clear()
        self._legacy_selected_edges.clear()

        # Edge-Selection-Mixin sync
        if hasattr(self, '_selected_edge_ids'):
            self._selected_edge_ids.clear()

        logger.debug("[SelectionMixin] Edge selection cleared")

    def clear_all_selection(self) -> None:
        """
        Cleart alle Selektionen (Faces + Edges).

        Dies ist die empfohlene Methode für kompletten Clear.
        """
        self.clear_face_selection()
        self.clear_edge_selection()

        # Auch hovered state clearen
        if hasattr(self, 'hovered_face'):
            self.hovered_face = -1
        if hasattr(self, 'hover_face_id'):
            self.hover_face_id = None

        logger.debug("[SelectionMixin] All selection cleared")

    # ========================================================================
    # Phase 4: Selection Query Methods
    # ========================================================================

    def has_selected_faces(self) -> bool:
        """Prüft ob Faces selektiert sind."""
        return len(self.selected_face_ids) > 0

    def has_selected_edges(self) -> bool:
        """Prüft ob Edges selektiert sind."""
        return len(self.selected_edge_ids) > 0 or len(self._selected_edge_ids) > 0

    def get_face_count(self) -> int:
        """Gibt Anzahl der selektierten Faces zurück."""
        return len(self.selected_face_ids)

    def get_edge_count(self) -> int:
        """Gibt Anzahl der selektierten Edges zurück."""
        # Nutze _selected_edge_ids aus edge_selection_mixin wenn verfügbar
        if hasattr(self, '_selected_edge_ids'):
            return len(self._selected_edge_ids)
        return len(self.selected_edge_ids)

    # ========================================================================
    # Phase 5: Selection Modification Methods (Type-Safe)
    # ========================================================================

    def add_face_selection(self, face_id: int) -> None:
        """
        Fügt eine Face-ID zur Selektion hinzu.
        """
        self.selected_face_ids.add(face_id)
        self._legacy_selected_faces.add(face_id)

    def remove_face_selection(self, face_id: int) -> None:
        """
        Entfernt eine Face-ID aus der Selektion.
        """
        self.selected_face_ids.discard(face_id)
        self._legacy_selected_faces.discard(face_id)

    def toggle_face_selection(self, face_id: int, is_multi: bool = False) -> None:
        """
        Toggelt eine Face-Selektion.

        Args:
            face_id: Die Face ID
            is_multi: True für Multi-Select (Toggle), False für Single-Select (Replace)
        """
        if is_multi:
            if face_id in self.selected_face_ids:
                self.remove_face_selection(face_id)
            else:
                self.add_face_selection(face_id)
        else:
            # Single select: erst clearen, dann addieren
            self.clear_face_selection()
            self.add_face_selection(face_id)

    def add_edge_selection(self, edge_id: int) -> None:
        """
        Fügt eine Edge-ID zur Selektion hinzu.
        """
        self.selected_edge_ids.add(edge_id)
        # Sync mit edge_selection_mixin
        if hasattr(self, '_selected_edge_ids'):
            self._selected_edge_ids.add(edge_id)

    def remove_edge_selection(self, edge_id: int) -> None:
        """
        Entfernt eine Edge-ID aus der Selektion.
        """
        self.selected_edge_ids.discard(edge_id)
        # Sync mit edge_selection_mixin
        if hasattr(self, '_selected_edge_ids'):
            self._selected_edge_ids.discard(edge_id)

    # ========================================================================
    # Phase 6: Selection State Export (für Feature-Commands)
    # ========================================================================

    def export_face_selection(self) -> Set[int]:
        """
        Exportiert die aktuelle Face-Selektion als Set von IDs.

        Returns:
            Set[int]: Die selektierten Face IDs
        """
        return self.selected_face_ids.copy()

    def export_edge_selection(self) -> Set[int]:
        """
        Exportiert die aktuelle Edge-Selektion als Set von IDs.

        Returns:
            Set[int]: Die selektierten Edge IDs
        """
        # Nutze _selected_edge_ids aus edge_selection_mixin wenn verfügbar
        if hasattr(self, '_selected_edge_ids'):
            return self._selected_edge_ids.copy()
        return self.selected_edge_ids.copy()

    # ========================================================================
    # Phase 7: Selection State Import (für Restore/Undo)
    # ========================================================================

    def import_face_selection(self, face_ids: Set[int]) -> None:
        """
        Importiert Face-Selektion aus einem Set von IDs.

        Args:
            face_ids: Set von Face IDs die selektiert werden sollen
        """
        self.clear_face_selection()
        self.selected_face_ids.update(face_ids)
        self._legacy_selected_faces.update(face_ids)

    def import_edge_selection(self, edge_ids: Set[int]) -> None:
        """
        Importiert Edge-Selektion aus einem Set von IDs.

        Args:
            edge_ids: Set von Edge IDs die selektiert werden sollen
        """
        self.clear_edge_selection()
        self.selected_edge_ids.update(edge_ids)
        if hasattr(self, '_selected_edge_ids'):
            self._selected_edge_ids.update(edge_ids)

    # ========================================================================
    # W33 EPIC Y1: Selection Robustness - Hit Priorisierung
    # ========================================================================

    def prioritize_hit(self, face_id: int, domain_type: str = None) -> int:
        """
        EPIC Y1: Bestimmt die Priorität eines Hits für die Selektion.

        Prioritätsordnung (höchste zuerst):
        1. Sketch-Profile (für Extrude-Workflows)
        2. Sketch-Shells (gefüllte Flächen)
        3. Body-Faces (3D-Körper)
        4. Konstruktionsflächen

        Args:
            face_id: Die Face ID
            domain_type: Optional der Domain-Typ (wenn bereits bekannt)

        Returns:
            int: Priorität (0 = höchste, größere Zahlen = niedrigere Priorität)
        """
        if domain_type is None and hasattr(self, 'detector'):
            face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
            if face:
                domain_type = getattr(face, 'domain_type', 'unknown')

        # Prioritätszuordnung
        if domain_type == 'sketch_profile':
            return 0  # Höchste Priorität
        elif domain_type == 'sketch_shell':
            return 1
        elif domain_type == 'body_face':
            return 2
        elif domain_type and domain_type.startswith('construction'):
            return 3
        else:
            return 99  # Niedrigste Priorität für unbekannte Typen

    def is_selection_valid_for_mode(self, face_id: int, current_mode: str) -> bool:
        """
        EPIC Y1: Prüft ob eine Selektion für den aktuellen Modus gültig ist.

        Args:
            face_id: Die Face ID
            current_mode: Der aktuelle Modus ('3d', 'sketch', etc.)

        Returns:
            bool: True wenn die Selektion gültig ist
        """
        if not hasattr(self, 'detector'):
            return True  # Keine Prüfung möglich, erlaube

        face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
        if not face:
            return False

        domain_type = getattr(face, 'domain_type', 'unknown')

        # In 3D-Modus: Body-Faces haben Priorität
        if current_mode == '3d':
            return domain_type in ('body_face', 'sketch_profile', 'sketch_shell')

        # In Sketch-Modus: Sketch-Elemente haben Priorität
        if current_mode == 'sketch':
            return domain_type.startswith('sketch')

        # Extrude-Modus: Nur Profile erlaubt
        if hasattr(self, 'extrude_mode') and self.extrude_mode:
            return domain_type == 'sketch_profile'

        return True  # Standard: Erlaube alles

    # ========================================================================
    # W33 EPIC Y2: Abort/Cancel Parity - Zentrale Abort-Methode
    # ========================================================================

    def abort_interaction_state(self, reason: str = "user_abort") -> bool:
        """
        EPIC Y2: Zentrale Abort-Methode für alle interaktiven Zustände.

        Diese Methode sorgt für Parity zwischen ESC und Rechtsklick bei:
        - Drag-Operationen (is_dragging, _offset_plane_dragging, _split_dragging)
        - Interaktionsmodi (extrude_mode, measure_mode, point_to_point_mode)
        - Edge/Texture-Selection-Modi
        - Preview-Aktoren

        Args:
            reason: Grund für den Abort (für Logging)

        Returns:
            bool: True wenn ein Zustand abgebrochen wurde, False wenn im Idle-Zustand
        """
        aborted = False
        states_cleared = []

        # 1. Drag-Zustände abbrechen (Priority 1)
        if hasattr(self, 'is_dragging') and self.is_dragging:
            self.is_dragging = False
            self.drag_start_pos = None  # type: ignore
            states_cleared.append("is_dragging")
            aborted = True

        if hasattr(self, '_offset_plane_dragging') and self._offset_plane_dragging:
            self._offset_plane_dragging = False
            self._offset_plane_drag_start = None
            states_cleared.append("offset_plane_dragging")
            aborted = True

        if hasattr(self, '_split_dragging') and self._split_dragging:
            self._split_dragging = False
            self._split_drag_start = None
            states_cleared.append("split_dragging")
            aborted = True

        # 2. Interaktionsmodi abbrechen (Priority 2)
        if hasattr(self, 'extrude_mode') and self.extrude_mode:
            self.extrude_mode = False
            self._is_potential_drag = False  # type: ignore
            states_cleared.append("extrude_mode")
            aborted = True

        if hasattr(self, 'point_to_point_mode') and self.point_to_point_mode:
            try:
                # W32 Crash-Stabilisierung: cancel Methode existiert möglicherweise nicht
                if hasattr(self, 'cancel_point_to_point_mode') and callable(getattr(self, 'cancel_point_to_point_mode', None)):
                    self.cancel_point_to_point_mode()
                else:
                    # Fallback: Manuelles Bereinigen
                    self.point_to_point_mode = False
                    if hasattr(self, 'point_to_point_start'):
                        self.point_to_point_start = None
                    if hasattr(self, 'point_to_point_body_id'):
                        self.point_to_point_body_id = None
            except Exception as e:
                logger.debug(f"[SelectionMixin] Error during point_to_point cleanup: {e}")
                # Fallback: Minimale Bereinigung
                self.point_to_point_mode = False
            states_cleared.append("point_to_point_mode")
            aborted = True

        if hasattr(self, 'edge_select_mode') and self.edge_select_mode:
            self.stop_edge_selection_mode()
            states_cleared.append("edge_select_mode")
            aborted = True

        if hasattr(self, 'texture_face_mode') and self.texture_face_mode:
            self.texture_face_mode = False
            self._texture_body_id = None
            self._texture_selected_faces = []
            states_cleared.append("texture_face_mode")
            aborted = True

        # 3. Preview-Aktoren bereinigen (Priority 3)
        preview_actors = [
            '_preview_actor', '_revolve_preview_actor',
            '_hole_preview_actor', '_thread_preview_actor',
            '_draft_preview_actor', '_offset_plane_preview_actor'
        ]
        for attr in preview_actors:
            if hasattr(self, attr) and getattr(self, attr) is not None:
                setattr(self, attr, None)
                states_cleared.append(f"preview_{attr}")

        # 4. Selektion bei Bedarf clearen (abhängig vom reason)
        if reason in ("mode_change", "component_switch"):
            self.clear_all_selection()
            states_cleared.append("selection")

        # 5. Cursor zurücksetzen
        try:
            from PySide6.QtCore import Qt
            if hasattr(self, 'setCursor'):
                self.setCursor(Qt.ArrowCursor)
        except Exception:
            pass

        if states_cleared:
            logger.debug(f"[SelectionMixin] Abort ({reason}): {', '.join(states_cleared)}")

        return aborted

    # ========================================================================
    # W33 EPIC Y3: Preview & Actor Lifecycle Hardening
    # ========================================================================

    def cleanup_preview_actors(self) -> None:
        """
        EPIC Y3: Bereinigt alle Preview-Aktoren deterministisch.

        Diese Methode sollte bei Moduswechseln und vor neuen Operationen
        aufgerufen werden, um Actor-Leaks zu vermeiden.
        """
        if not hasattr(self, 'plotter') or self.plotter is None:
            return

        # Liste aller bekannten Preview-Actor-Namen
        preview_patterns = [
            'preview', 'highlight', 'hover_', 'det_face_',
            'draft_face_highlight_', 'texture_face_highlight_',
            'body_face_highlight', 'edit_edge_highlight', 'edit_face_highlight',
            'p2p_hover_marker', 'p2p_start_marker', 'p2p_line',
            'projection_preview_', 'tnp_debug_',
            'batch_edges_', 'edge_hover'
        ]

        actors_to_remove = []
        try:
            # Alle aktuellen Actors auflisten
            if hasattr(self.plotter, 'renderer') and hasattr(self.plotter.renderer, 'actors'):
                for name in list(self.plotter.renderer.actors.keys()):
                    # Prüfen ob der Name einem Preview-Muster entspricht
                    if any(pattern in name for pattern in preview_patterns):
                        actors_to_remove.append(name)
        except Exception:
            pass

        # Actors entfernen (mit try-except für robustheit)
        for name in actors_to_remove:
            try:
                self.plotter.remove_actor(name, render=False)
            except Exception:
                pass

        if actors_to_remove:
            logger.debug(f"[SelectionMixin] Cleaned up {len(actors_to_remove)} preview actors")

    def ensure_selection_actors_valid(self) -> None:
        """
        EPIC Y3: Stellt sicher dass alle Selektions-Aktoren gültig sind.

        Entfernt "stale" Actors die nicht mehr zum aktuellen Selektionszustand passen.
        """
        if not hasattr(self, 'plotter') or self.plotter is None:
            return

        # Entferne Hover-Actors für nicht-selektierte Faces
        if hasattr(self, 'selected_face_ids'):
            for face_id in list(self.selected_face_ids):
                actor_name = f"hover_{face_id}"
                try:
                    if actor_name in self.plotter.renderer.actors:
                        self.plotter.remove_actor(actor_name, render=False)
                except Exception:
                    pass

    # ========================================================================
    # W33 EPIC Y4: Interaction Performance - Hot-Path Optimierung
    # ========================================================================

    def is_hover_cache_valid(self, x: int, y: int, ttl_seconds: float = 0.016) -> bool:
        """
        EPIC Y4: Prüft ob der Hover-Cache noch gültig ist.

        Args:
            x: X-Koordinate
            y: Y-Koordinate
            ttl_seconds: Time-To-Live in Sekunden (default: 16ms = 60 FPS)

        Returns:
            bool: True wenn der Cache gültig ist
        """
        if not hasattr(self, '_hover_pick_cache') or self._hover_pick_cache is None:
            return False

        try:
            import time
            timestamp, cache_x, cache_y, *_ = self._hover_pick_cache
            return (time.time() - timestamp) < ttl_seconds and cache_x == x and cache_y == y
        except Exception:
            return False

    def update_hover_cache(self, x: int, y: int, result: Any) -> None:
        """
        EPIC Y4: Aktualisiert den Hover-Cache.

        Args:
            x: X-Koordinate
            y: Y-Koordinate
            result: Das Pick-Ergebnis zum Cachen
        """
        import time
        self._hover_pick_cache = (time.time(), x, y, result)

    def invalidate_hover_cache(self) -> None:
        """EPIC Y4: Invalidiert den Hover-Cache."""
        self._hover_pick_cache = None


# Export für Viewport Integration
__all__ = [
    'SelectionMixin',
]
