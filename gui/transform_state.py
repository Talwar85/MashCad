"""
MashCad - Zentrale Transform-State-Machine

Diese Klasse zentralisiert den gesamten Transform-State, der vorher über
main_window.py, viewport_pyvista.py und transform_gizmo_v3.py verteilt war.

Verwendet Qt Signals für reaktive Updates zwischen Komponenten.
"""

from PySide6.QtCore import QObject, Signal
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class TransformStateData:
    """Immutable data container for transform state"""
    mode: Optional[str] = None  # "move", "rotate", "scale", None
    pending_mode: Optional[str] = None  # Wartet auf Body-Selektion
    axis_lock: Optional[str] = None  # "X", "Y", "Z", None
    plane_lock: Optional[str] = None  # "XY", "XZ", "YZ", None
    is_dragging: bool = False
    numeric_input: str = ""
    active_body_id: Optional[str] = None
    selected_body_ids: List[str] = field(default_factory=list)
    pivot_mode: str = "center"  # "center", "cursor", "selection"
    snap_enabled: bool = True  # Snap-to-Grid aktiviert (nur mit Ctrl-Taste)
    snap_grid_size: float = 1.0  # 1mm Grid-Size


class TransformState(QObject):
    """
    Zentrale State-Machine für das Transform-System.

    Signals:
        mode_changed: Emittiert wenn Transform-Modus wechselt
        body_selected: Emittiert wenn Body für Transform selektiert wird
        axis_lock_changed: Emittiert wenn Achsen-Lock sich ändert
        dragging_changed: Emittiert wenn Drag-State sich ändert
        state_reset: Emittiert wenn State komplett zurückgesetzt wird
    """

    # Signals
    mode_changed = Signal(str)  # new_mode ("move", "rotate", "scale", None)
    body_selected = Signal(str)  # body_id
    axis_lock_changed = Signal(object)  # axis ("X", "Y", "Z", None)
    plane_lock_changed = Signal(object)  # plane ("XY", "XZ", "YZ", None)
    dragging_changed = Signal(bool)  # is_dragging
    numeric_input_changed = Signal(str)  # current_input
    state_reset = Signal()

    def __init__(self):
        super().__init__()
        self._data = TransformStateData()

    # ==================== PROPERTIES ====================

    @property
    def mode(self) -> Optional[str]:
        """Aktueller Transform-Modus"""
        return self._data.mode

    @mode.setter
    def mode(self, value: Optional[str]):
        if self._data.mode != value:
            self._data.mode = value
            self.mode_changed.emit(value or "")

    @property
    def pending_mode(self) -> Optional[str]:
        """Modus wartet auf Body-Selektion"""
        return self._data.pending_mode

    @pending_mode.setter
    def pending_mode(self, value: Optional[str]):
        self._data.pending_mode = value

    @property
    def axis_lock(self) -> Optional[str]:
        """Aktives Achsen-Lock (X/Y/Z)"""
        return self._data.axis_lock

    @axis_lock.setter
    def axis_lock(self, value: Optional[str]):
        if self._data.axis_lock != value:
            self._data.axis_lock = value
            # Bei Achsen-Lock: Plane-Lock deaktivieren
            if value:
                self._data.plane_lock = None
            self.axis_lock_changed.emit(value)

    @property
    def plane_lock(self) -> Optional[str]:
        """Aktives Ebenen-Lock (XY/XZ/YZ)"""
        return self._data.plane_lock

    @plane_lock.setter
    def plane_lock(self, value: Optional[str]):
        if self._data.plane_lock != value:
            self._data.plane_lock = value
            # Bei Plane-Lock: Achsen-Lock deaktivieren
            if value:
                self._data.axis_lock = None
            self.plane_lock_changed.emit(value)

    @property
    def is_dragging(self) -> bool:
        """Wird gerade ein Transform durchgeführt?"""
        return self._data.is_dragging

    @is_dragging.setter
    def is_dragging(self, value: bool):
        if self._data.is_dragging != value:
            self._data.is_dragging = value
            self.dragging_changed.emit(value)
            # Bei Drag-Ende: Locks und numerische Eingabe zurücksetzen
            if not value:
                self._data.axis_lock = None
                self._data.plane_lock = None
                self._data.numeric_input = ""

    @property
    def numeric_input(self) -> str:
        """Aktuelle numerische Eingabe während Transform"""
        return self._data.numeric_input

    @numeric_input.setter
    def numeric_input(self, value: str):
        if self._data.numeric_input != value:
            self._data.numeric_input = value
            self.numeric_input_changed.emit(value)

    @property
    def active_body_id(self) -> Optional[str]:
        """ID des aktuell transformierten Bodies"""
        return self._data.active_body_id

    @active_body_id.setter
    def active_body_id(self, value: Optional[str]):
        if self._data.active_body_id != value:
            self._data.active_body_id = value
            if value:
                self.body_selected.emit(value)

    @property
    def selected_body_ids(self) -> List[str]:
        """Liste aller selektierten Body-IDs (für Multi-Select)"""
        return self._data.selected_body_ids

    @selected_body_ids.setter
    def selected_body_ids(self, value: List[str]):
        self._data.selected_body_ids = value

    @property
    def pivot_mode(self) -> str:
        """Pivot-Punkt-Modus (center, cursor, selection)"""
        return self._data.pivot_mode

    @pivot_mode.setter
    def pivot_mode(self, value: str):
        self._data.pivot_mode = value

    @property
    def snap_enabled(self) -> bool:
        """Ist Grid-Snapping aktiviert?"""
        return self._data.snap_enabled

    @snap_enabled.setter
    def snap_enabled(self, value: bool):
        self._data.snap_enabled = value

    @property
    def snap_grid_size(self) -> float:
        """Grid-Größe für Snapping"""
        return self._data.snap_grid_size

    @snap_grid_size.setter
    def snap_grid_size(self, value: float):
        self._data.snap_grid_size = value

    # ==================== METHODS ====================

    def reset(self):
        """Setzt den gesamten State zurück"""
        self._data = TransformStateData()
        self.state_reset.emit()

    def start_transform(self, mode: str, body_id: str):
        """Startet einen Transform mit einem Body"""
        self.mode = mode
        self.active_body_id = body_id
        self.pending_mode = None

    def start_pending_transform(self, mode: str):
        """Startet Transform im Pending-Mode (wartet auf Body-Selektion)"""
        self.pending_mode = mode
        self.mode = None
        self.active_body_id = None

    def activate_pending_transform(self, body_id: str):
        """Aktiviert pending Transform mit selektiertem Body"""
        if self.pending_mode:
            self.mode = self.pending_mode
            self.active_body_id = body_id
            self.pending_mode = None

    def cancel_transform(self):
        """Bricht aktuellen Transform ab"""
        self.reset()

    def toggle_axis_lock(self, axis: str):
        """Togglet Achsen-Lock (X/Y/Z)"""
        if self.axis_lock == axis:
            self.axis_lock = None
        else:
            self.axis_lock = axis

    def toggle_plane_lock(self, plane: str):
        """Togglet Ebenen-Lock (XY/XZ/YZ)"""
        if self.plane_lock == plane:
            self.plane_lock = None
        else:
            self.plane_lock = plane

    def is_active(self) -> bool:
        """Ist ein Transform aktiv?"""
        return self.mode is not None or self.pending_mode is not None

    def is_waiting_for_body(self) -> bool:
        """Wartet auf Body-Selektion?"""
        return self.pending_mode is not None

    def get_constraint_info(self) -> dict:
        """Gibt aktuelle Constraint-Info zurück (für UI-Anzeige)"""
        return {
            "axis_lock": self.axis_lock,
            "plane_lock": self.plane_lock,
            "snap_enabled": self.snap_enabled,
            "snap_grid_size": self.snap_grid_size
        }

    def __repr__(self) -> str:
        return (f"TransformState(mode={self.mode}, "
                f"axis_lock={self.axis_lock}, "
                f"is_dragging={self.is_dragging}, "
                f"active_body={self.active_body_id})")
