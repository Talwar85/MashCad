"""
Unified Selection Mixin (Paket B: Selection-State Konsolidierung)
================================================================

Provides single source of truth for face and edge selection.

Problem:
- Doppelmodell: selected_faces (Legacy, Index-basiert) vs selected_face_ids (TNP v4)
- Doppelmodell: selected_edges (Legacy, VTK Objekte) vs _selected_edge_ids (TNP v4)

Lösung:
- Unified Selection API mit Single Source of Truth
- Rückwärtskompatible Wrapper für Legacy-Access
- Zentrale Clear-Methoden für alle Selektions-Typen

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
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
        # Gibt selected_face_ids zurück für Kompatibilität
        # Note: Dies ist ein Mapping von IDs auf sich selbst
        # Für echten Index-basierten Zugriff müsste eine Mapping-Tabelle her
        return self.selected_face_ids

    @selected_faces.setter
    def selected_faces(self, value: Any) -> None:
        """
        Legacy setter für selected_faces.

        DEPRECATED: Bitte selected_face_ids verwenden.
        """
        # Konvertiere verschiedene Input-Typen zu Set[int]
        if isinstance(value, set):
            self.selected_face_ids = value
        elif isinstance(value, (list, tuple)):
            self.selected_face_ids = set(value)
        else:
            logger.warning(f"[SelectionMixin] Unexpected type for selected_faces: {type(value)}")
            self.selected_face_ids = set()

        # Sync für legacy compatibility
        self._legacy_selected_faces = self.selected_face_ids.copy()

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


# Export für Viewport Integration
__all__ = [
    'SelectionMixin',
]
