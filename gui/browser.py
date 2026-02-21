"""
MashCad - Project Browser (Fusion360-Style)
Collapsible tree with Origin planes, Components, Sketches, Bodies

Phase 3 Assembly: Unterstützt hierarchische Component-Struktur
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTreeWidget, QTreeWidgetItem, QMenu, QSizePolicy,
    QToolButton, QScrollArea, QSlider, QInputDialog, QAbstractItemView,
    QComboBox, QLineEdit, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QTimer
from PySide6.QtGui import QFont, QIcon, QColor, QDrag, QKeySequence, QShortcut
from loguru import logger

from i18n import tr
from config.feature_flags import is_enabled
from gui.design_tokens import DesignTokens


def _safe_int(value, default: int = 0) -> int:
    """Defensive int conversion — returns default on None/non-numeric."""
    if value is None:
        return default
    # Mock-Objekte haben keinen echten numerischen Wert
    if hasattr(value, '__class__') and 'Mock' in value.__class__.__name__:
        return default
    try:
        result = int(value)
        # Prüfe ob das Ergebnis tatsächlich ein int ist (Mock gibt Mock zurück)
        if isinstance(result, int) and not hasattr(result, '__class__'):
            return result
        if hasattr(result, '__class__') and 'Mock' in result.__class__.__name__:
            return default
        return result
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    """Defensive float conversion — returns default on None/non-numeric."""
    if value is None:
        return default
    # Mock-Objekte haben keinen echten numerischen Wert
    if hasattr(value, '__class__') and 'Mock' in value.__class__.__name__:
        return default
    try:
        result = float(value)
        # Prüfe ob das Ergebnis tatsächlich ein float ist (Mock gibt Mock zurück)
        if isinstance(result, float) and not hasattr(result, '__class__'):
            return result
        if hasattr(result, '__class__') and 'Mock' in result.__class__.__name__:
            return default
        return result
    except (TypeError, ValueError):
        return default


def _safe_details(raw) -> dict:
    """Ensure status_details is always a dict, even if Mock/None/str."""
    if isinstance(raw, dict):
        return raw
    return {}


def _format_feature_status_tooltip(status_msg: str, status: str = "", status_details=None) -> str:
    """
    Formatiert Feature-Statusmeldungen für den Browser-Tooltip.

    W7: Nutzt status_class/severity aus Error-Envelope v2 für konsistente Klassifikation.

    Erkennt den technischen Suffix `| refs: ...` und stellt Referenzen
    als eigene Liste dar, damit gebrochene TNP-Referenzen direkt lesbar sind.
    """
    details = status_details if isinstance(status_details, dict) else {}
    if not status_msg and not details:
        return ""

    msg = str(status_msg).strip()
    if not msg:
        msg = str(details.get("message", "") or "").strip()
    if not msg and not details.get("refs") and not details.get("hint") and not details.get("code"):
        return ""

    marker = "| refs:"
    base_msg = msg
    refs_part = ""
    if marker in msg:
        base_msg, refs_part = msg.split(marker, 1)
        base_msg = base_msg.strip().rstrip(";")
        refs_part = refs_part.strip()

    if not base_msg:
        base_msg = str(details.get("message", "") or "").strip()

    lines = []

    # W7: PAKET C - Priorisiere status_class/severity aus Error-Envelope v2
    status_class = details.get("status_class", "")
    severity = details.get("severity", "")

    # Fallback: code-basierte Erkennung (W5-Compat)
    is_drift = (status_class == "WARNING_RECOVERABLE" or
                severity == "warning" or
                details.get("code") == "tnp_ref_drift" or
                details.get("tnp_failure", {}).get("category") == "drift")

    # Mapping status_class -> Anzeige-Text
    if status_class == "WARNING_RECOVERABLE":
        lines.append(tr("Warning (Recoverable)"))
    elif status_class == "BLOCKED":
        lines.append(tr("Blocked"))
    elif status_class == "CRITICAL":
        lines.append(tr("Critical Error"))
    elif status_class == "ERROR":
        lines.append(tr("Error"))
    # Fallback: Legacy status-basiert
    elif status == "ERROR":
        if is_drift:
            lines.append(tr("Warning (Recoverable)"))
        else:
            lines.append(tr("Error"))
    elif status == "WARNING":
        lines.append(tr("Warning"))

    if base_msg:
        lines.append(base_msg)

    ref_items = []
    if refs_part:
        ref_items = [item.strip() for item in refs_part.split(";") if item.strip()]
    elif isinstance(details.get("refs"), dict):
        for key, value in details["refs"].items():
            if value in (None, "", [], (), {}):
                continue
            ref_items.append(f"{key}={value!r}")

    if ref_items:
        lines.append("")
        lines.append(tr("Broken refs:"))
        max_items = 8
        for item in ref_items[:max_items]:
            lines.append(f"- {item}")
        if len(ref_items) > max_items:
            lines.append(f"- +{len(ref_items) - max_items} {tr('more')}")

    hint = str(details.get("hint", "") or "").strip()
    if not hint:
        hint = str(details.get("next_action", "") or "").strip()
    if hint:
        lines.append("")
        lines.append(f"{tr('Hint')}: {hint}")

    code = str(details.get("code", "") or "").strip()
    
    # W3: TNP Category 
    tnp_failure = details.get("tnp_failure", {})
    category = tnp_failure.get("category")
    if category:
        cat_map = {
            "missing_ref": tr("Referenz verloren"),
            "mismatch": tr("Formkonflikt"),
            "drift": tr("Geometrie-Drift"),
        }
        cat_str = cat_map.get(category, category)
        lines.append("")
        lines.append(f"[{cat_str}]")

    if code:
        lines.append(f"{tr('Code')}: {code}")

    return "\n".join(lines)


class DraggableTreeWidget(QTreeWidget):
    """
    QTreeWidget mit Drag & Drop Support für Bodies/Sketches zwischen Components.

    Phase 6 Assembly: Ermöglicht Drag & Drop von Bodies/Sketches zu anderen Components.
    W21 Product Leap: Keyboard-first Navigation, Status-Badges, Filter-Support.
    W26 Product Leap: Problem-First Navigation mit Priorisierung, Multi-Select Batch-Aktionen.

    Keyboard Shortcuts:
    - Enter: Component/Feature aktivieren
    - Esc: Zur Root-Component zurück
    - F2: Umbenennen
    - Ctrl+Down: Nächstes Item mit Fehler
    - Ctrl+Up: Vorheriges Item mit Fehler
    - Ctrl+Shift+Down: Nächstes kritisches Problem (CRITICAL > BLOCKED > ERROR > WARNING)
    - Ctrl+Shift+Up: Vorheriges kritisches Problem
    - Ctrl+N: Nächstes Item selektieren
    - Ctrl+P: Vorheriges Item selektieren
    - Ctrl+A: Alle Problem-Features selektieren
    """

    # Signal wenn Item gedroppt wird: (item_type, item, source_comp, target_comp)
    item_dropped = Signal(str, object, object, object)

    # Keyboard Shortcuts
    activate_component = Signal(object)      # Enter gedrückt auf Component
    go_to_root = Signal()                    # Esc gedrückt
    rename_requested = Signal(object)        # F2 gedrückt auf Component

    # W21: Navigation-Signale
    next_problem_item = Signal()             # Ctrl+Down: Nächstes Problem-Item
    prev_problem_item = Signal()             # Ctrl+Up: Vorheriges Problem-Item
    next_item = Signal()                     # Ctrl+N: Nächstes Item
    prev_item = Signal()                     # Ctrl+P: Vorheriges Item

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)  # Nicht InternalMove!
        self.setDefaultDropAction(Qt.MoveAction)
        self._drag_item_data = None

        # W21: Filter für Tree-Inhalte
        self._filter_mode = "all"  # all, errors, warnings, blocked
        self._visible_items = []  # Cache für sichtbare Items (für Navigation)
        self._current_visible_index = -1

        # W21: Status-Badges für Problemfeatures
        self._problem_items_cache = {}  # item -> status_class

    def set_filter_mode(self, mode: str):
        """
        W21 Paket A: Setzt den Filter-Modus für Tree-Inhalte.

        Args:
            mode: 'all', 'errors', 'warnings', 'blocked'
        """
        if self._filter_mode == mode:
            return  # Keine Änderung, kein Refresh nötig

        self._filter_mode = mode
        self._apply_filter()
        self._update_visible_items_cache()

    def _apply_filter(self):
        """W21 Paket A: Wendet den Filter auf alle Tree-Items an."""
        root = self.invisibleRootItem()
        count = root.childCount()

        for i in range(count):
            self._filter_item_recursive(root.child(i))

    def _filter_item_recursive(self, item: QTreeWidgetItem):
        """Rekursive Filter-Anwendung."""
        data = item.data(0, Qt.UserRole)
        should_show = self._should_show_item(data, item)

        # Kinder zuerst verarbeiten
        has_visible_child = False
        for i in range(item.childCount()):
            child = item.itemAt(i) if hasattr(item, 'itemAt') else item.child(i)
            if child:
                self._filter_item_recursive(child)
                if not child.isHidden():
                    has_visible_child = True

        # Item selbst verstecken/zeigen
        # Wenn Kinder sichtbar sind, muss Eltern auch sichtbar sein
        if has_visible_child:
            item.setHidden(False)
        else:
            item.setHidden(not should_show)

    def _should_show_item(self, data, item: QTreeWidgetItem) -> bool:
        """Prüft ob ein Item gemäß Filter sichtbar sein soll."""
        if self._filter_mode == "all":
            return True

        if not data:
            return True  # Struktur-Items (Origin, etc.) immer zeigen

        item_type = data[0]

        # Features filtern basierend auf Status
        if item_type == 'feature':
            feature = data[1] if len(data) > 1 else None
            if feature:
                status = str(getattr(feature, 'status', 'OK') or 'OK')
                details = _safe_details(getattr(feature, 'status_details', None))
                status_class = str(details.get('status_class', '') or '')
                severity = str(details.get('severity', '') or '')

                if self._filter_mode == "errors":
                    return status in ('ERROR',) or status_class in ('ERROR', 'CRITICAL')
                elif self._filter_mode == "warnings":
                    return status in ('WARNING', 'ERROR') or status_class in ('WARNING_RECOVERABLE', 'BLOCKED')
                elif self._filter_mode == "blocked":
                    return status_class in ('BLOCKED',) or severity == 'blocked'

        return True  # Default: sichtbar

    def _update_visible_items_cache(self):
        """W21: Aktualisiert den Cache der sichtbaren Items für Navigation."""
        self._visible_items = []
        root = self.invisibleRootItem()

        def collect_visible(item):
            if not item.isHidden():
                self._visible_items.append(item)
            for i in range(item.childCount()):
                child = item.child(i)
                if child:
                    collect_visible(child)

        for i in range(root.childCount()):
            collect_visible(root.child(i))

        # Aktuellen Index finden
        current = self.currentItem()
        if current in self._visible_items:
            self._current_visible_index = self._visible_items.index(current)
        else:
            self._current_visible_index = -1

    def navigate_to_next_item(self):
        """W21: Navigiert zum nächsten sichtbaren Item."""
        self._update_visible_items_cache()
        if not self._visible_items:
            return

        new_index = self._current_visible_index + 1
        if new_index >= len(self._visible_items):
            new_index = 0  # Wrap around

        self._current_visible_index = new_index
        self.setCurrentItem(self._visible_items[new_index])
        self.scrollToItem(self._visible_items[new_index])

    def navigate_to_prev_item(self):
        """W21: Navigiert zum vorherigen sichtbaren Item."""
        self._update_visible_items_cache()
        if not self._visible_items:
            return

        new_index = self._current_visible_index - 1
        if new_index < 0:
            new_index = len(self._visible_items) - 1  # Wrap around

        self._current_visible_index = new_index
        self.setCurrentItem(self._visible_items[new_index])
        self.scrollToItem(self._visible_items[new_index])

    def navigate_to_next_problem(self):
        """W21: Navigiert zum nächsten Problem-Item."""
        items = self._get_all_items()
        current = self.currentItem()
        found_current = False

        for item in items:
            if item.isHidden():
                continue
            if found_current:
                if self._is_problem_item(item):
                    self.setCurrentItem(item)
                    self.scrollToItem(item)
                    return
            elif item == current:
                found_current = True

        # Wrap around - von vorne beginnen
        for item in items:
            if item.isHidden():
                continue
            if self._is_problem_item(item):
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return

    def navigate_to_prev_problem(self):
        """W21: Navigiert zum vorherigen Problem-Item."""
        items = self._get_all_items()
        current = self.currentItem()
        found_current = False
        prev_problem = None

        for item in reversed(items):
            if item.isHidden():
                continue
            if item == current:
                found_current = True
                if prev_problem:
                    self.setCurrentItem(prev_problem)
                    self.scrollToItem(prev_problem)
                    return
            elif not found_current and self._is_problem_item(item):
                prev_problem = item

        # Wrap around
        for item in reversed(items):
            if item.isHidden():
                continue
            if self._is_problem_item(item):
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return

    def _get_all_items(self):
        """Sammelt alle Items rekursiv."""
        items = []
        root = self.invisibleRootItem()

        def collect(item):
            items.append(item)
            for i in range(item.childCount()):
                child = item.child(i)
                if child:
                    collect(child)

        for i in range(root.childCount()):
            collect(root.child(i))

        return items

    def _is_problem_item(self, item: QTreeWidgetItem) -> bool:
        """Prüft ob ein Item ein Problem-Item ist."""
        try:
            data = item.data(0, Qt.UserRole)
        except (TypeError, AttributeError):
            return False
        if not data or len(data) < 2:
            return False

        item_type = data[0]

        # Nur Features haben Status
        if item_type == 'feature':
            feature = data[1]
            status = str(getattr(feature, 'status', 'OK') or 'OK')
            details = _safe_details(getattr(feature, 'status_details', None))
            status_class = str(details.get('status_class', '') or '')
            severity = str(details.get('severity', '') or '')

            return status in ('ERROR', 'WARNING') or \
                   status_class in ('ERROR', 'WARNING_RECOVERABLE', 'BLOCKED', 'CRITICAL') or \
                   severity in ('error', 'warning', 'blocked', 'critical')

        return False

    def _get_problem_priority(self, item: QTreeWidgetItem) -> int:
        """
        W26: Gibt die Priorität eines Problem-Items zurück (niedriger = höhere Priorität).

        Prioritätsordnung: CRITICAL (0) > BLOCKED (1) > ERROR (2) > WARNING (3)
        """
        try:
            data = item.data(0, Qt.UserRole)
        except (TypeError, AttributeError):
            return 999
        if not data or len(data) < 2:
            return 999

        item_type = data[0]
        if item_type != 'feature':
            return 999

        feature = data[1]
        details = _safe_details(getattr(feature, 'status_details', None))
        status_class = str(details.get('status_class', '') or '')
        severity = str(details.get('severity', '') or '')

        # W26: Prioritätsordnung für Problem-First Navigation
        if status_class == 'CRITICAL' or severity == 'critical':
            return 0
        elif status_class == 'BLOCKED' or severity == 'blocked':
            return 1
        elif status_class == 'ERROR' or severity == 'error':
            return 2
        elif status_class == 'WARNING_RECOVERABLE' or severity == 'warning':
            return 3
        else:
            return 4

    def navigate_to_next_critical_problem(self):
        """W26: Navigiert zum nächsten kritischen Problem (CRITICAL > BLOCKED > ERROR > WARNING)."""
        items = self._get_all_items()
        current = self.currentItem()
        found_current = False

        # Sammle alle Problem-Items mit ihrer Priorität
        problem_items = []
        for item in items:
            if item.isHidden():
                continue
            priority = self._get_problem_priority(item)
            if priority < 999:
                problem_items.append((item, priority))

        if not problem_items:
            return

        # Sortiere nach Priorität (niedrigste zuerst)
        problem_items.sort(key=lambda x: x[1])

        # Finde aktuelle Position
        current_idx = -1
        for idx, (item, _) in enumerate(problem_items):
            if item == current:
                current_idx = idx
                break

        # Nächstes Item (Wrap-around)
        next_idx = (current_idx + 1) % len(problem_items)
        next_item = problem_items[next_idx][0]

        self.setCurrentItem(next_item)
        self.scrollToItem(next_item)

    def navigate_to_prev_critical_problem(self):
        """W26: Navigiert zum vorherigen kritischen Problem."""
        items = self._get_all_items()
        current = self.currentItem()

        problem_items = []
        for item in items:
            if item.isHidden():
                continue
            priority = self._get_problem_priority(item)
            if priority < 999:
                problem_items.append((item, priority))

        if not problem_items:
            return

        # Sortiere nach Priorität
        problem_items.sort(key=lambda x: x[1])

        # Finde aktuelle Position
        current_idx = -1
        for idx, (item, _) in enumerate(problem_items):
            if item == current:
                current_idx = idx
                break

        # Vorheriges Item (Wrap-around)
        prev_idx = (current_idx - 1) % len(problem_items)
        prev_item = problem_items[prev_idx][0]

        self.setCurrentItem(prev_item)
        self.scrollToItem(prev_item)

    def select_all_problem_items(self):
        """W26: Selektiert alle Problem-Features (Multi-Select)."""
        items = self._get_all_items()
        problem_items = []

        for item in items:
            if not item.isHidden() and self._is_problem_item(item):
                problem_items.append(item)

        if problem_items:
            self.clearSelection()
            for item in problem_items:
                item.setSelected(True)
            # Setze Fokus auf erstes Problem
            self.setCurrentItem(problem_items[0])
            self.scrollToItem(problem_items[0])

    def keyPressEvent(self, event):
        """Keyboard Shortcuts für Component-Operationen und W21/W26 Navigation."""
        item = self.currentItem()
        data = item.data(0, Qt.UserRole) if item else None
        modifiers = event.modifiers()

        # W26: Ctrl+Shift+Down - Nächstes kritisches Problem (CRITICAL > BLOCKED > ERROR > WARNING)
        if (event.key() == Qt.Key_Down and
            modifiers & Qt.ControlModifier and
            modifiers & Qt.ShiftModifier):
            self.navigate_to_next_critical_problem()
            return

        # W26: Ctrl+Shift+Up - Vorheriges kritisches Problem
        if (event.key() == Qt.Key_Up and
            modifiers & Qt.ControlModifier and
            modifiers & Qt.ShiftModifier):
            self.navigate_to_prev_critical_problem()
            return

        # W26: Ctrl+A - Alle Problem-Features selektieren
        if event.key() == Qt.Key_A and modifiers & Qt.ControlModifier:
            self.select_all_problem_items()
            return

        # W21: Ctrl+Down - Nächstes Problem-Item
        if event.key() == Qt.Key_Down and modifiers & Qt.ControlModifier:
            self.navigate_to_next_problem()
            self.next_problem_item.emit()
            return

        # W21: Ctrl+Up - Vorheriges Problem-Item
        if event.key() == Qt.Key_Up and modifiers & Qt.ControlModifier:
            self.navigate_to_prev_problem()
            self.prev_problem_item.emit()
            return

        # W21: Ctrl+N - Nächstes Item
        if event.key() == Qt.Key_N and modifiers & Qt.ControlModifier:
            self.navigate_to_next_item()
            self.next_item.emit()
            return

        # W21: Ctrl+P - Vorheriges Item
        if event.key() == Qt.Key_P and modifiers & Qt.ControlModifier:
            self.navigate_to_prev_item()
            self.prev_item.emit()
            return

        # Enter: Component oder Feature aktivieren
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if data and data[0] == 'component' and data[1]:
                self.activate_component.emit(data[1])
                return
            # W21: Feature auch aktivieren
            elif data and data[0] == 'feature':
                self.activate_component.emit(data[1])  # Reuse signal for feature
                return

        # Esc: Zur Root-Component
        if event.key() == Qt.Key_Escape:
            self.go_to_root.emit()
            return

        # F2: Umbenennen
        if event.key() == Qt.Key_F2:
            if data and data[0] == 'component' and data[1]:
                self.rename_requested.emit(data[1])
                return

        # Default handling
        super().keyPressEvent(event)

    def startDrag(self, supportedActions):
        """Startet Drag-Operation für Body oder Sketch."""
        item = self.currentItem()
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data[0]

        # Nur Bodies und Sketches können gedragged werden
        if item_type not in ('body', 'sketch'):
            return

        self._drag_item_data = data

        # Drag starten
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"{item_type}:{data[1].id}")
        drag.setMimeData(mime_data)

        # Drag ausführen
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        """Akzeptiert Drag wenn es ein Body/Sketch ist."""
        if event.mimeData().hasText():
            text = event.mimeData().text()
            if text.startswith('body:') or text.startswith('sketch:'):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        """Highlight Drop-Target wenn über Component."""
        item = self.itemAt(event.position().toPoint())
        if item:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == 'component':
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        """Führt Drop-Operation aus."""
        if not self._drag_item_data:
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        if not target_item:
            event.ignore()
            return

        target_data = target_item.data(0, Qt.UserRole)
        if not target_data or target_data[0] != 'component':
            event.ignore()
            return

        target_component = target_data[1]
        source_data = self._drag_item_data
        item_type = source_data[0]
        item = source_data[1]

        # Source-Component finden
        source_component = self._find_source_component(item, item_type)

        if source_component and source_component != target_component:
            # Signal emittieren
            self.item_dropped.emit(item_type, item, source_component, target_component)
            event.acceptProposedAction()
        else:
            event.ignore()

        self._drag_item_data = None

    def _find_source_component(self, item, item_type):
        """Findet die Component die das Item enthält."""
        # Wird von parent (ProjectBrowser) gesetzt
        browser = self.parent()
        while browser and not isinstance(browser, ProjectBrowser):
            browser = browser.parent()

        if not browser or not browser.document:
            return None

        def search(comp):
            if item_type == 'body' and item in comp.bodies:
                return comp
            if item_type == 'sketch' and item in comp.sketches:
                return comp
            for sub in comp.sub_components:
                result = search(sub)
                if result:
                    return result
            return None

        return search(browser.document.root_component)


class ProjectBrowser(QFrame):
    """
    Fusion360-style Project Browser - collapsible

    Phase 3 Assembly: Unterstützt hierarchische Component-Struktur
    """

    # Bestehende Signale
    feature_selected = Signal(object)
    feature_double_clicked = Signal(object)
    feature_deleted = Signal(object, object)  # (feature, body)
    visibility_changed = Signal()
    body_vis_changed = Signal(str, bool)
    plane_selected = Signal(str)
    construction_plane_selected = Signal(object)  # ConstructionPlane
    construction_plane_vis_changed = Signal(str, bool)  # (plane_id, visible)
    collapsed_changed = Signal(bool)
    rollback_changed = Signal(object, int)  # (body, rollback_index)

    # Phase 3 Assembly: Neue Signale für Component-Operationen
    component_activated = Signal(object)           # Component - wird aktiviert
    component_created = Signal(object, object)     # (parent_component, new_component)
    component_deleted = Signal(object)             # Component - wird gelöscht
    component_renamed = Signal(object, str)        # (component, new_name)
    component_vis_changed = Signal(str, bool)      # (component_id, visible)

    # Phase 6: Move Body/Sketch zwischen Components
    body_moved_to_component = Signal(object, object, object)      # (body, source_comp, target_comp)
    sketch_moved_to_component = Signal(object, object, object)    # (sketch, source_comp, target_comp)

    # W21: Filter- und Navigation-Signale
    filter_changed = Signal(str)  # Filter-Modus hat sich geändert

    # W26: Batch-Aktionen für Problem-Features
    batch_retry_rebuild = Signal(list)     # List[(feature, body)] - Retry rebuild für ausgewählte Features
    batch_open_diagnostics = Signal(list)  # List[(feature, body)] - Öffne Diagnostik für ausgewählte Features
    batch_isolate_bodies = Signal(list)    # List[body] - Isoliere Bodies mit Problemen
    batch_unhide_bodies = Signal(list)     # List[body] - Mache versteckte Bodies sichtbar
    batch_focus_features = Signal(list)    # List[(feature, body)] - Fokus auf Features im Viewport

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._expanded_width = 180

        self.setStyleSheet(DesignTokens.stylesheet_browser())

        self.document = None
        self.sketch_visibility = {}
        self.body_visibility = {}
        self.plane_visibility = {}
        self.component_visibility = {}  # Phase 3 Assembly

        # Assembly System ist permanent aktiviert
        self._assembly_enabled = True

        # W21: Refresh-Blocker um Flackern zu vermeiden
        self._refresh_pending = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # === CONTENT AREA ===
        self.content = QWidget()
        self.content.setMinimumWidth(160)
        self.content.setMaximumWidth(240)  # W21: Etwas breiter für Filter-UI
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # === W21 PAKET A: FILTER BAR ===
        self.filter_bar = QFrame()
        self.filter_bar.setStyleSheet(f"""
            QFrame {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border-bottom: 1px solid {DesignTokens.COLOR_BORDER.name()};
            }}
            QComboBox {{
                background: {DesignTokens.COLOR_BG_PANEL.name()};
                color: {DesignTokens.COLOR_TEXT_SECONDARY.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 10px;
            }}
            QComboBox:hover {{
                border: 1px solid {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setContentsMargins(4, 2, 4, 2)
        filter_layout.setSpacing(4)

        # Filter-Dropdown
        self.filter_combo = QComboBox()
        self.filter_combo.setFixedHeight(20)
        self.filter_combo.addItem("📋 " + tr("Alle"), "all")
        self.filter_combo.addItem("⚠ " + tr("Warnungen"), "warnings")
        self.filter_combo.addItem("❌ " + tr("Fehler"), "errors")
        self.filter_combo.addItem("🚫 " + tr("Blockiert"), "blocked")
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)

        # Problembadge (zeigt Anzahl der Problem-Features)
        self.problem_badge = QLabel("0")
        self.problem_badge.setStyleSheet(f"""
            background: {DesignTokens.COLOR_ERROR.name()};
            color: white;
            border-radius: 8px;
            padding: 1px 6px;
            font-size: 9px;
            font-weight: bold;
        """)
        self.problem_badge.setVisible(False)
        filter_layout.addWidget(self.problem_badge)

        filter_layout.addStretch()

        content_layout.addWidget(self.filter_bar)

        # Tree Widget - Phase 6: Mit Drag & Drop Support, W21: Filter-Support
        self.tree = DraggableTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)  # Multi-Select aktivieren
        self.tree.setStyleSheet(DesignTokens.stylesheet_browser())
        self.tree.itemClicked.connect(self._on_click)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        # Phase 6: Drag & Drop Signal verbinden
        self.tree.item_dropped.connect(self._on_item_dropped)

        # Phase 6: Keyboard Shortcuts
        self.tree.activate_component.connect(self._on_keyboard_activate)
        self.tree.go_to_root.connect(self._on_keyboard_go_to_root)
        self.tree.rename_requested.connect(self._rename_component)

        # W21: Navigation-Signale verbinden
        self.tree.next_problem_item.connect(self._on_next_problem)
        self.tree.prev_problem_item.connect(self._on_prev_problem)
        self.tree.next_item.connect(self._on_next_item)
        self.tree.prev_item.connect(self._on_prev_item)

        content_layout.addWidget(self.tree)

        # === ROLLBACK BAR ===
        self.rollback_frame = QFrame()
        self.rollback_frame.setStyleSheet(f"background: {DesignTokens.COLOR_BG_PANEL.name()}; border-top: 1px solid {DesignTokens.COLOR_BORDER.name()};")
        self.rollback_frame.setFixedHeight(40)
        self.rollback_frame.setVisible(False)
        rb_layout = QHBoxLayout(self.rollback_frame)
        rb_layout.setContentsMargins(6, 2, 6, 2)

        rb_label = QLabel("⏪")
        rb_label.setStyleSheet(f"color: {DesignTokens.COLOR_PRIMARY.name()}; font-size: 12px;")
        rb_layout.addWidget(rb_label)

        self.rollback_slider = QSlider(Qt.Horizontal)
        self.rollback_slider.setStyleSheet(DesignTokens.stylesheet_browser())
        self.rollback_slider.valueChanged.connect(self._on_rollback_changed)
        rb_layout.addWidget(self.rollback_slider)

        self.rollback_label = QLabel("")
        self.rollback_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; min-width: 30px;")
        rb_layout.addWidget(self.rollback_label)

        content_layout.addWidget(self.rollback_frame)

        self._rollback_body = None

        self.main_layout.addWidget(self.content)
        
        # === COLLAPSE BAR (rechts vom Content) ===
        self.collapse_bar = QFrame()
        self.collapse_bar.setFixedWidth(16)
        self.collapse_bar.setStyleSheet(f"""
            QFrame {{ 
                background: {DesignTokens.COLOR_BG_PANEL.name()}; 
                border-left: 1px solid {DesignTokens.COLOR_BORDER.name()};
            }}
            QFrame:hover {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
            }}
        """)
        self.collapse_bar.setCursor(Qt.PointingHandCursor)
        self.collapse_bar.mousePressEvent = self._toggle_collapse
        
        collapse_layout = QVBoxLayout(self.collapse_bar)
        collapse_layout.setContentsMargins(0, 0, 0, 0)
        collapse_layout.setAlignment(Qt.AlignCenter)
        
        self.collapse_icon = QLabel("◀")
        self.collapse_icon.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px;")
        collapse_layout.addWidget(self.collapse_icon)
        
        self.main_layout.addWidget(self.collapse_bar)
    
    def _toggle_collapse(self, event=None):
        self._collapsed = not self._collapsed
        self.content.setVisible(not self._collapsed)
        self.collapse_icon.setText("▶" if self._collapsed else "◀")
        
        if self._collapsed:
            self.setFixedWidth(16)
        else:
            self.setMinimumWidth(160)
            self.setMaximumWidth(240)
            self.setFixedWidth(self._expanded_width)
        
        self.collapsed_changed.emit(self._collapsed)
    
    def set_document(self, doc):
        self.document = doc
        if doc:
            # WICHTIG: get_all_sketches/get_all_bodies statt .sketches/.bodies
            # .sketches/.bodies geben nur die aktive Component zurück!
            for s in doc.get_all_sketches():
                if s.id not in self.sketch_visibility:
                    self.sketch_visibility[s.id] = True
            for b in doc.get_all_bodies():
                if b.id not in self.body_visibility:
                    self.body_visibility[b.id] = True
        self.refresh()
    
    def refresh(self):
        self.tree.clear()
        if not self.document:
            return
        
        # Root: Document
        root = QTreeWidgetItem(self.tree, [f"{self.document.name}"])
        root.setExpanded(True)
        root.setForeground(0, QColor("#ddd"))
        
        # Origin (Standard-Ebenen) - eingeklappt
        origin = QTreeWidgetItem(root, ["◎ Origin"])
        origin.setExpanded(False)
        origin.setForeground(0, QColor("#666"))
        
        planes = [
            ("XY Plane (Top)", "xy", "#5588dd"),
            ("XZ Plane (Front)", "xz", "#55dd88"),
            ("YZ Plane (Right)", "yz", "#dd8855"),
        ]
        for name, plane_id, color in planes:
            item = QTreeWidgetItem(origin, [f"▬ {name}"])
            item.setData(0, Qt.UserRole, ('plane', plane_id))
            item.setForeground(0, QColor(color))
        
        axes = [("X Axis", "x", "#dd5555"), ("Y Axis", "y", "#55dd55"), ("Z Axis", "z", "#5555dd")]
        for name, axis_id, color in axes:
            item = QTreeWidgetItem(origin, [f"→ {name}"])
            item.setData(0, Qt.UserRole, ('axis', axis_id))
            item.setForeground(0, QColor(color))

        # Construction Planes (Offset Planes)
        if hasattr(self.document, 'planes') and self.document.planes:
            for cp in self.document.planes:
                vis = self.plane_visibility.get(cp.id, True)
                icon = "●" if vis else "○"
                item = QTreeWidgetItem(origin, [f"{icon} ▬ {cp.name}"])
                item.setData(0, Qt.UserRole, ('construction_plane', cp))
                item.setForeground(0, QColor("#bb88dd" if vis else "#555"))

        # =========================================================================
        # Phase 3 Assembly: Component-Hierarchie oder Legacy-Modus
        # =========================================================================
        if self._assembly_enabled and hasattr(self.document, 'root_component') and self.document.root_component:
            # Assembly-Modus: Component-Hierarchie anzeigen
            self._add_component_to_tree(root, self.document.root_component)
        else:
            # Legacy-Modus: Flache Struktur wie bisher
            if self.document.bodies or self.document.sketches:
                comp = QTreeWidgetItem(root, ["⊞ Component1"])
                comp.setExpanded(True)
                comp.setForeground(0, QColor("#b8b8b8"))
                comp.setData(0, Qt.UserRole, ('component', None))

                # Sketches unter Component
                for s in self.document.sketches:
                    vis = self.sketch_visibility.get(s.id, True)
                    icon = "●" if vis else "○"
                    item = QTreeWidgetItem(comp, [f"{icon} {s.name}"])
                    item.setData(0, Qt.UserRole, ('sketch', s))
                    item.setForeground(0, QColor("#7cb3f7" if vis else "#555"))

                # Bodies unter Component
                self._add_bodies_to_tree(comp, self.document.bodies)

    def _add_component_to_tree(self, parent_item: QTreeWidgetItem, component):
        """
        Fügt Component rekursiv zum Tree hinzu.

        Phase 3 Assembly: Hierarchische Darstellung von Components.
        """
        # Component sichtbar?
        vis = self.component_visibility.get(component.id, component.visible)
        is_active = component.is_active

        # Icon basierend auf Status
        if not vis:
            # Versteckt hat höchste Priorität bei der Anzeige
            icon = "⊟"  # Geschlossen = versteckt
            color = "#666" if is_active else "#444"  # Etwas heller wenn aktiv
        elif is_active:
            icon = "◆"  # Aktive Component
            color = "#f0a030"  # Orange/Gold für aktiv
        else:
            icon = "⊞"
            color = "#b8b8b8"

        # Component-Item erstellen
        comp_item = QTreeWidgetItem(parent_item, [f"{icon} {component.name}"])
        comp_item.setExpanded(component.expanded)
        comp_item.setForeground(0, QColor(color))
        comp_item.setData(0, Qt.UserRole, ('component', component))

        # Font-Styling basierend auf Status
        font = comp_item.font(0)
        if is_active:
            font.setBold(True)
        if not vis:
            font.setStrikeOut(True)  # Durchgestrichen wenn unsichtbar
        comp_item.setFont(0, font)

        # Sketches dieser Component
        for s in component.sketches:
            s_vis = self.sketch_visibility.get(s.id, True)
            s_icon = "●" if s_vis else "○"
            item = QTreeWidgetItem(comp_item, [f"{s_icon} {s.name}"])
            item.setData(0, Qt.UserRole, ('sketch', s))
            item.setForeground(0, QColor("#7cb3f7" if s_vis else "#555"))

        # Bodies dieser Component
        self._add_bodies_to_tree(comp_item, component.bodies)

        # Sub-Components rekursiv
        for sub in component.sub_components:
            self._add_component_to_tree(comp_item, sub)

    def _add_bodies_to_tree(self, parent_item: QTreeWidgetItem, bodies: list):
        """Fügt Bodies zum Tree hinzu (wiederverwendbar für Legacy und Assembly)."""
        for b in bodies:
            vis = self.body_visibility.get(b.id, True)
            icon = "●" if vis else "○"
            bi = QTreeWidgetItem(parent_item, [f"{icon} {b.name}"])
            bi.setData(0, Qt.UserRole, ('body', b))
            bi.setExpanded(True)
            bi.setForeground(0, QColor("#a8d4a8" if vis else "#555"))

            if hasattr(b, 'features'):
                rb_idx = b.rollback_index if b.rollback_index is not None else len(b.features)
                for fi_idx, f in enumerate(b.features):
                    rolled_back = fi_idx >= rb_idx
                    prefix = "↳" if not rolled_back else "⊘"
                    color = "#777" if not rolled_back else "#444"
                    if hasattr(f, 'status') and f.status == "ERROR":
                        # W7: PAKET C - Color basierend auf status_class (Error-Envelope v2)
                        details = _safe_details(getattr(f, "status_details", None))
                        status_class = details.get("status_class", "")
                        severity = details.get("severity", "")

                        # Priority 1: status_class mapping
                        if status_class == "WARNING_RECOVERABLE" or severity == "warning":
                            color = "#e0a030"  # Orange for recoverable warnings
                        elif status_class == "BLOCKED" or severity == "blocked":
                            color = "#aa5500"  # Dark orange for blocked
                        elif status_class == "CRITICAL" or severity == "critical":
                            color = "#ff0000"  # Bright red for critical
                        elif status_class == "ERROR" or severity == "error":
                            color = "#cc5555"  # Red for standard errors
                        else:
                            # Fallback: W5 code-basierte Erkennung
                            tnp = details.get("tnp_failure", {})
                            if details.get("code") == "tnp_ref_drift" or tnp.get("category") == "drift":
                                color = "#e0a030"  # Orange for drift/recoverable
                            else:
                                color = "#cc5555"  # Red for hard errors

                    # Geometry Badge: zeigt Volume-Delta und Edge-Erfolgsrate
                    badge = ""
                    gd = getattr(f, '_geometry_delta', None)
                    if isinstance(gd, dict) and not rolled_back:
                        vol_pct = _safe_float(gd.get("volume_pct", 0))
                        if vol_pct != 0:
                            sign = "+" if vol_pct > 0 else ""
                            badge = f"  Vol{sign}{vol_pct:.1f}%"
                        else:
                            fd = _safe_int(gd.get("faces_delta", 0))
                            if fd != 0:
                                badge = f"  {'+' if fd > 0 else ''}{fd}F"
                        edges_ok = _safe_int(gd.get("edges_ok"), -1)
                        edges_total = _safe_int(gd.get("edges_total"), 0)
                        if edges_total > 0 and edges_ok >= 0 and edges_ok < edges_total:
                            badge = f"  ⚠ {edges_ok}/{edges_total}{badge}"

                    fi = QTreeWidgetItem(bi, [f"{prefix} {f.name}{badge}"])
                    fi.setData(0, Qt.UserRole, ('feature', f, b))
                    fi.setForeground(0, QColor(color))
                    status_msg = getattr(f, "status_message", "")
                    status_details = _safe_details(getattr(f, "status_details", None))
                    if status_msg or status_details:
                        tooltip = _format_feature_status_tooltip(
                            status_msg,
                            getattr(f, "status", ""),
                            status_details,
                        )
                        if tooltip:
                            fi.setToolTip(0, tooltip)

    def _is_component_visible(self, component) -> bool:
        """Prüft ob Component und alle Parent-Components sichtbar sind."""
        # Prüfe diese Component
        if not self.component_visibility.get(component.id, component.visible):
            return False
        # Prüfe Parent-Kette (rekursiv nach oben)
        if component.parent:
            return self._is_component_visible(component.parent)
        return True

    def get_visible_sketches(self):
        """
        Gibt alle Sketches mit Visibility und Inactive-Status zurück.

        Returns:
            List[(sketch, is_visible, is_inactive_component)]
        """
        if not self.document:
            return []

        result = []

        if self._assembly_enabled and hasattr(self.document, 'root_component') and self.document.root_component:
            # Assembly: Sketches mit Component-Visibility und Inactive-Status
            active_comp = self.document._active_component

            def collect_sketches(component):
                """Rekursiv Sketches aus Component sammeln."""
                comp_visible = self._is_component_visible(component)
                is_inactive = (component != active_comp)
                for sketch in component.sketches:
                    sketch_vis = self.sketch_visibility.get(sketch.id, True)
                    # Sketch ist nur sichtbar wenn BEIDE: Component UND Sketch sichtbar
                    final_vis = comp_visible and sketch_vis
                    result.append((sketch, final_vis, is_inactive))
                for sub in component.sub_components:
                    collect_sketches(sub)

            collect_sketches(self.document.root_component)
        else:
            # Legacy: Alle Sketches sind "aktiv"
            all_sketches = self.document.get_all_sketches()
            for s in all_sketches:
                result.append((s, self.sketch_visibility.get(s.id, True), False))

        return result

    def get_visible_bodies(self):
        """
        Gibt Liste von (body, is_visible, is_inactive_component) Tupeln zurück.

        Bei Assembly-Modus: Alle Bodies aus ALLEN Components werden zurückgegeben,
        nicht nur die der aktiven Component. Component-Visibility wird berücksichtigt.

        Returns:
            List[(body, is_visible, is_inactive_component)]
        """
        if not self.document:
            return []

        result = []

        if self._assembly_enabled and hasattr(self.document, 'root_component') and self.document.root_component:
            # Assembly: Bodies mit Component-Info
            active_comp = self.document._active_component

            def collect_bodies(component):
                """Rekursiv Bodies aus Component sammeln."""
                is_inactive = (component != active_comp)
                comp_visible = self._is_component_visible(component)
                for body in component.bodies:
                    body_vis = self.body_visibility.get(body.id, True)
                    # Body ist nur sichtbar wenn BEIDE: Component UND Body sichtbar
                    final_vis = comp_visible and body_vis
                    result.append((body, final_vis, is_inactive))
                for sub in component.sub_components:
                    collect_bodies(sub)

            collect_bodies(self.document.root_component)
        else:
            # Legacy: Alle Bodies sind "aktiv"
            for body in self.document._bodies:
                vis = self.body_visibility.get(body.id, True)
                result.append((body, vis, False))

        return result
    
    def _on_click(self, item, column):
        data = item.data(0, Qt.UserRole)
        if data:
            if data[0] == 'plane':
                self.plane_selected.emit(data[1])
            elif data[0] == 'construction_plane':
                self.construction_plane_selected.emit(data[1])
            else:
                self.feature_selected.emit(data)
    
    def _on_double_click(self, item, column):
        data = item.data(0, Qt.UserRole)
        if data:
            # Phase 3 Assembly: Doppelklick auf Component aktiviert sie
            if data[0] == 'component' and data[1] is not None:
                self._activate_component(data[1])
            else:
                self.feature_double_clicked.emit(data)
    
    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        # W29: Selektierte Items für Batch-Kontext ermitteln
        selected_items = self.tree.selectedItems()
        selected_count = len(selected_items)

        # W29: Prüfe ob Selektion gemischt ist (Features + Bodies + andere)
        has_features = any(
            i.data(0, Qt.UserRole) and i.data(0, Qt.UserRole)[0] == 'feature'
            for i in selected_items
        )
        has_bodies = any(
            i.data(0, Qt.UserRole) and i.data(0, Qt.UserRole)[0] == 'body'
            for i in selected_items
        )

        menu = QMenu(self)
        menu.setStyleSheet(DesignTokens.stylesheet_browser())

        if data[0] == 'sketch':
            sketch = data[1]
            menu.addAction(tr("Edit"), lambda: self.feature_double_clicked.emit(data))
            vis = self.sketch_visibility.get(sketch.id, True)
            menu.addAction(tr("Hide") if vis else tr("Show"), lambda: self._toggle_vis(sketch, 'sketch'))

            # Phase 6: Move to Component submenu
            move_menu = self._create_move_to_component_menu(sketch, 'sketch')
            if move_menu:
                menu.addMenu(move_menu)

            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_sketch(sketch))

        elif data[0] == 'body':
            body = data[1]
            vis = self.body_visibility.get(body.id, True)
            menu.addAction(tr("Hide") if vis else tr("Show"), lambda: self._toggle_vis(body, 'body'))

            # W29: Batch unhide nur wenn versteckte Bodies existieren
            if self.document:
                try:
                    all_bodies = self.document.get_all_bodies()
                    has_hidden = any(
                        not self.body_visibility.get(b.id, True)
                        for b in all_bodies
                    )
                    if has_hidden:
                        menu.addAction(tr("📦 Alle einblenden"), self.batch_unhide_selected_bodies)
                except Exception:
                    pass

            # Phase 6: Move to Component submenu
            move_menu = self._create_move_to_component_menu(body, 'body')
            if move_menu:
                menu.addMenu(move_menu)

            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_body(body))

        elif data[0] == 'construction_plane':
            cp = data[1]
            vis = self.plane_visibility.get(cp.id, True)
            menu.addAction(tr("Hide") if vis else tr("Show"), lambda: self._toggle_vis(cp, 'construction_plane'))
            menu.addAction(tr("New Sketch"), lambda: self.construction_plane_selected.emit(cp))
            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_construction_plane(cp))

        elif data[0] == 'plane':
            menu.addAction(tr("New Sketch"), lambda: self.plane_selected.emit(data[1]))

        elif data[0] == 'component':
            comp = data[1]
            if comp is not None:
                # Phase 3 Assembly: Vollständiges Component-Menü
                if not comp.is_active:
                    menu.addAction(tr("Activate"), lambda c=comp: self._activate_component(c))
                    menu.addSeparator()

                menu.addAction(tr("New Sketch"), lambda: self.plane_selected.emit('xy'))
                menu.addAction(tr("New Component"), lambda c=comp: self._create_sub_component(c))

                vis = self.component_visibility.get(comp.id, comp.visible)
                menu.addAction(tr("Hide") if vis else tr("Show"), lambda c=comp: self._toggle_vis(c, 'component'))

                menu.addSeparator()
                menu.addAction(tr("Rename"), lambda c=comp: self._rename_component(c))

                # Root-Component kann nicht gelöscht werden
                if comp.parent is not None:
                    menu.addAction(tr("Delete"), lambda c=comp: self._delete_component(c))
            else:
                # Legacy-Modus: Einfaches Menü
                menu.addAction(tr("New Sketch"), lambda: self.plane_selected.emit('xy'))

        elif data[0] == 'feature':
            # NEU: Feature-Kontext-Menü (Edit, Delete, W26 Batch-Aktionen)
            feature = data[1]
            body = data[2]

            # W26: Prüfe ob Problem-Feature
            is_problem = self.tree._is_problem_item(item)

            menu.addAction(tr("Edit"), lambda: self.feature_double_clicked.emit(data))

            # W26: Recovery-Aktionen für Problem-Features (nur bei Einzel-Selektion)
            if is_problem and selected_count == 1:
                menu.addSeparator()
                recovery_menu = menu.addMenu(tr("🩹 Recovery"))
                recovery_menu.addAction(tr("Retry Rebuild"), self.batch_retry_selected)
                recovery_menu.addAction(tr("Open Diagnostics"), self.batch_open_selected_diagnostics)
                if body:
                    recovery_menu.addAction(tr("Isolate Body"), self.batch_isolate_selected_bodies)

            # W29: Batch-Aktionen nur bei Multi-Select ohne gemischte Typen
            if selected_count > 1 and has_features and not has_bodies:
                # W30: Guard gegen Hidden-Only-Selection
                hidden_count = sum(
                    1 for i in selected_items
                    if self._is_item_hidden_or_invalid(i)
                )

                menu.addSeparator()
                batch_menu = menu.addMenu(tr("📦 Batch"))

                # W30: Recover & Focus Aktion (Primary Batch Action)
                problem_count = sum(
                    1 for i in selected_items
                    if self.tree._is_problem_item(i)
                )

                if problem_count > 0:
                    batch_menu.addAction(tr(f"🔧 Recover & Focus ({problem_count})"), self.recover_and_focus_selected)

                # Nur Focus-Aktion wenn alle Features sind
                batch_menu.addAction(tr("Focus Features"), self.batch_focus_selected_features)

                # Recovery-Aktionen wenn Problem-Features selektiert
                if problem_count > 0:
                    batch_menu.addAction(tr(f"Retry Rebuild ({problem_count})"), self.batch_retry_selected)
                    batch_menu.addAction(tr(f"Open Diagnostics ({problem_count})"), self.batch_diagnostics_selected_features)

                # W30: Warnung bei Hidden-Only-Selection
                if hidden_count == selected_count:
                    warning = batch_menu.addAction(tr("⚠️ Alle Items versteckt"))
                    warning.setEnabled(False)
                    warning.setToolTip(tr("Einige selektierte Items sind aktuell versteckt"))

            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_feature(feature, body))

        menu.exec(self.tree.mapToGlobal(pos))

    def _is_item_hidden_or_invalid(self, item: QTreeWidgetItem) -> bool:
        """
        W30: Prüft ob ein Item versteckt oder ungültig ist.

        Args:
            item: Das zu prüfende Tree-Item

        Returns:
            True wenn Item versteckt oder Body/Feature ungültig ist
        """
        if item.isHidden():
            return True

        data = item.data(0, Qt.UserRole)
        if not data:
            return False

        item_type = data[0]

        # Prüfe ob Body versteckt ist
        if item_type == 'body':
            body = data[1]
            if body and hasattr(body, 'id'):
                return not self.body_visibility.get(body.id, True)

        # Prüfe ob Feature in einem versteckten Body ist
        elif item_type == 'feature':
            body = data[2] if len(data) > 2 else None
            if body and hasattr(body, 'id'):
                return not self.body_visibility.get(body.id, True)

        return False

    def _validate_batch_selection(self) -> dict:
        """
        W30: Validiert die aktuelle Selektion für Batch-Aktionen.

        Returns:
            dict mit keys: valid, is_mixed, is_hidden_only, has_invalid_refs,
                          error_message
        """
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return {
                "valid": False,
                "error_message": tr("Keine Items ausgewählt")
            }

        # Prüfe auf gemischte Selektion
        has_features = any(
            i.data(0, Qt.UserRole) and i.data(0, Qt.UserRole)[0] == 'feature'
            for i in selected_items
        )
        has_bodies = any(
            i.data(0, Qt.UserRole) and i.data(0, Qt.UserRole)[0] == 'body'
            for i in selected_items
        )
        has_sketches = any(
            i.data(0, Qt.UserRole) and i.data(0, Qt.UserRole)[0] == 'sketch'
            for i in selected_items
        )

        is_mixed = sum([has_features, has_bodies, has_sketches]) > 1

        # Prüfe auf Hidden-Only-Selection
        hidden_count = sum(1 for i in selected_items if self._is_item_hidden_or_invalid(i))
        is_hidden_only = hidden_count == len(selected_items)

        # Prüfe auf ungültige Referenzen
        has_invalid_refs = False
        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == 'feature':
                feature = data[1]
                if feature and hasattr(feature, 'status'):
                    details = _safe_details(getattr(feature, 'status_details', None))
                    code = details.get('code', '')
                    if code in ('tnp_ref_missing', 'tnp_ref_mismatch'):
                        has_invalid_refs = True
                        break

        if is_mixed:
            return {
                "valid": False,
                "is_mixed": True,
                "error_message": tr("Gemischte Selektion (Features, Bodies, Sketches) nicht unterstützt")
            }

        if is_hidden_only:
            return {
                "valid": False,
                "is_hidden_only": True,
                "error_message": tr("Alle ausgewählten Items sind versteckt")
            }

        return {
            "valid": True,
            "has_invalid_refs": has_invalid_refs,
        }

    def _toggle_vis(self, obj, type_):
        if type_ == 'sketch':
            self.sketch_visibility[obj.id] = not self.sketch_visibility.get(obj.id, True)
        elif type_ == 'body':
            new_vis = not self.body_visibility.get(obj.id, True)
            self.body_visibility[obj.id] = new_vis
            self.body_vis_changed.emit(obj.id, new_vis)
        elif type_ == 'construction_plane':
            new_vis = not self.plane_visibility.get(obj.id, True)
            self.plane_visibility[obj.id] = new_vis
            obj.visible = new_vis
            self.construction_plane_vis_changed.emit(obj.id, new_vis)
        elif type_ == 'component':
            # Phase 3 Assembly: Component Visibility
            new_vis = not self.component_visibility.get(obj.id, obj.visible)
            self.component_visibility[obj.id] = new_vis
            obj.visible = new_vis
            self.component_vis_changed.emit(obj.id, new_vis)
            logger.debug(f"[BROWSER] Component '{obj.name}' visibility: {new_vis}")
        self.refresh()
        self.visibility_changed.emit()
    
    def _del_construction_plane(self, cp):
        if hasattr(self.document, 'planes') and cp in self.document.planes:
            self.document.planes.remove(cp)
            self.plane_visibility.pop(cp.id, None)
            self.refresh()
            self.visibility_changed.emit()

    def _del_sketch(self, s):
        if s in self.document.sketches:
            self.document.sketches.remove(s)
            self.refresh()
            self.visibility_changed.emit()
    
    def _del_body(self, b):
        if b in self.document.bodies:
            self.document.bodies.remove(b)
            self.refresh()
            self.visibility_changed.emit()

    def _del_feature(self, feature, body):
        """Löscht ein Feature aus einem Body via UndoCommand"""
        if feature in body.features:
            # Feature NICHT hier entfernen - das macht DeleteFeatureCommand.redo()
            # Signal emittieren für MainWindow, das den UndoCommand erstellt
            self.feature_deleted.emit(feature, body)

    # =========================================================================
    # Phase 3 Assembly: Component-Operationen
    # =========================================================================

    def _show_styled_input_dialog(self, title: str, label: str, default_text: str = "") -> tuple:
        """
        Zeigt einen gestylten Input-Dialog im App-Design.

        Returns:
            (text, ok) - wie QInputDialog.getText()
        """
        from PySide6.QtWidgets import QDialog, QLineEdit

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(340, 130)
        dialog.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Label
        lbl = QLabel(label)
        layout.addWidget(lbl)

        # Input
        input_field = QLineEdit(default_text)
        input_field.selectAll()
        layout.addWidget(input_field)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton(tr("Cancel"))

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        input_field.returnPressed.connect(dialog.accept)

        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        input_field.setFocus()

        result = dialog.exec()
        return (input_field.text(), result == QDialog.Accepted)

    def _activate_component(self, component):
        """Aktiviert eine Component (macht sie zur aktiven Bearbeitungs-Component)."""
        self._activate_component_safe(component)

    def _activate_component_safe(self, component):
        """Aktiviert eine Component mit robusten Guards."""
        if not self._assembly_enabled or not self.document:
            return False
        if component is None:
            return False

        # Signal emittieren - MainWindow handhabt die Aktivierung
        try:
            self.component_activated.emit(component)
            logger.debug(f"[BROWSER] Component aktivieren: {component.name}")
            return True
        except Exception as e:
            logger.warning(f"[BROWSER] Component-Aktivierung fehlgeschlagen: {e}")
            return False

    def _create_sub_component(self, parent_component):
        """Erstellt eine neue Sub-Component."""
        if not self._assembly_enabled or not self.document:
            return

        # Name abfragen mit gestyltem Dialog
        default_name = f"Component{len(parent_component.sub_components) + 1}"
        name, ok = self._show_styled_input_dialog(
            tr("New Component"),
            tr("Name:"),
            default_name
        )

        if ok and name:
            # Neue Component erstellen
            from modeling import Component
            new_comp = Component(name=name)
            new_comp.parent = parent_component

            # Signal emittieren - MainWindow erstellt UndoCommand
            self.component_created.emit(parent_component, new_comp)
            logger.debug(f"[BROWSER] Neue Component: {name} in {parent_component.name}")

    def _rename_component(self, component):
        """Benennt eine Component um."""
        if not self._assembly_enabled:
            return

        # Neuen Namen abfragen mit gestyltem Dialog
        new_name, ok = self._show_styled_input_dialog(
            tr("Rename Component"),
            tr("Name:"),
            component.name
        )

        if ok and new_name and new_name != component.name:
            old_name = component.name
            # Signal emittieren - MainWindow erstellt UndoCommand
            self.component_renamed.emit(component, new_name)
            logger.debug(f"[BROWSER] Component umbenennen: {old_name} → {new_name}")

    def _delete_component(self, component):
        """Löscht eine Component (nicht Root!)."""
        if not self._assembly_enabled:
            return

        if component.parent is None:
            logger.warning("[BROWSER] Root-Component kann nicht gelöscht werden")
            return

        # Signal emittieren - MainWindow erstellt UndoCommand
        self.component_deleted.emit(component)
        logger.debug(f"[BROWSER] Component löschen: {component.name}")

    def _create_move_to_component_menu(self, item, item_type: str) -> 'QMenu':
        """
        Erstellt ein Submenu mit allen verfügbaren Components zum Verschieben.

        Args:
            item: Body oder Sketch
            item_type: 'body' oder 'sketch'

        Returns:
            QMenu oder None wenn keine anderen Components verfügbar
        """
        if not self._assembly_enabled or not self.document:
            return None

        # Source-Component finden
        source_comp = self._find_component_containing(item, item_type)
        if not source_comp:
            return None

        # Alle Components sammeln (rekursiv)
        all_components = self._collect_all_components(self.document.root_component)

        # Nur Components zeigen, die nicht die Source sind
        available_components = [c for c in all_components if c != source_comp]

        if not available_components:
            return None

        move_menu = QMenu(tr("Move to Component"), self)
        move_menu.setStyleSheet(DesignTokens.stylesheet_browser())

        for target_comp in available_components:
            # Hierarchie-Indikator (→ zeigt Tiefe)
            depth = self._get_component_depth(target_comp)
            prefix = "  " * depth
            action = move_menu.addAction(f"{prefix}⊕ {target_comp.name}")
            action.triggered.connect(
                lambda checked, t=target_comp, s=source_comp, i=item, tp=item_type:
                    self._move_item_to_component(i, s, t, tp)
            )

        return move_menu

    def _find_component_containing(self, item, item_type: str):
        """Findet die Component, die ein Body oder Sketch enthält."""
        if not self.document:
            return None

        def search_in_component(comp, item, item_type):
            if item_type == 'body' and item in comp.bodies:
                return comp
            if item_type == 'sketch' and item in comp.sketches:
                return comp
            for sub in comp.sub_components:
                result = search_in_component(sub, item, item_type)
                if result:
                    return result
            return None

        return search_in_component(self.document.root_component, item, item_type)

    def _collect_all_components(self, comp) -> list:
        """Sammelt alle Components rekursiv."""
        result = [comp]
        for sub in comp.sub_components:
            result.extend(self._collect_all_components(sub))
        return result

    def _get_component_depth(self, comp) -> int:
        """Gibt die Tiefe einer Component in der Hierarchie zurück."""
        depth = 0
        current = comp
        while current.parent:
            depth += 1
            current = current.parent
        return depth

    def _move_item_to_component(self, item, source_comp, target_comp, item_type: str):
        """Emitiert Signal zum Verschieben eines Items."""
        if item_type == 'body':
            self.body_moved_to_component.emit(item, source_comp, target_comp)
            logger.debug(f"[BROWSER] Body '{item.name}' verschieben: {source_comp.name} → {target_comp.name}")
        elif item_type == 'sketch':
            self.sketch_moved_to_component.emit(item, source_comp, target_comp)
            logger.debug(f"[BROWSER] Sketch '{item.name}' verschieben: {source_comp.name} → {target_comp.name}")

    def _on_item_dropped(self, item_type: str, item, source_comp, target_comp):
        """
        Handler für Drag & Drop von Bodies/Sketches.

        Phase 6 Assembly: Wird von DraggableTreeWidget aufgerufen.
        """
        if not self._assembly_enabled:
            return

        logger.debug(f"[BROWSER] Drag&Drop: {item_type} '{item.name}' von {source_comp.name} nach {target_comp.name}")
        self._move_item_to_component(item, source_comp, target_comp, item_type)

    def _on_keyboard_activate(self, component):
        """
        Handler für Enter-Taste: Component aktivieren.

        Phase 6 Assembly: Keyboard Shortcut.
        """
        if not self._assembly_enabled or not component:
            return

        if not component.is_active:
            self._activate_component(component)
            logger.debug(f"[BROWSER] Keyboard: Component aktiviert: {component.name}")

    def _on_keyboard_go_to_root(self):
        """
        Handler für Esc-Taste: Zur Root-Component zurück.

        Phase 6 Assembly: Keyboard Shortcut.
        """
        if not self._assembly_enabled or not self.document:
            return

        root = self.document.root_component
        if root and not root.is_active:
            self._activate_component(root)
        logger.debug(f"[BROWSER] Keyboard: Zur Root-Component gewechselt")

    def get_selected_body_ids(self):
        """
        Gibt Liste aller selektierten Body-IDs zurück (für Multi-Select).

        Returns:
            List[str]: Liste von Body-IDs
        """
        selected_items = self.tree.selectedItems()
        body_ids = []

        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == 'body':
                body = data[1]
                body_ids.append(body.id)

        return body_ids

    def get_selected_bodies(self):
        """
        Gibt Liste aller selektierten Body-Objekte zurück.

        Returns:
            List[Body]: Liste von Body-Objekten
        """
        selected_items = self.tree.selectedItems()
        bodies = []

        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == 'body':
                body = data[1]
                bodies.append(body)

        return bodies

    def get_selected_features(self):
        """
        W26: Gibt Liste aller selektierten Features zurück.

        Returns:
            List[(feature, body)]: Liste von (Feature, Body) Tupeln
        """
        selected_items = self.tree.selectedItems()
        features = []

        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == 'feature':
                feature = data[1]
                body = data[2] if len(data) > 2 else None
                features.append((feature, body))

        return features

    def get_selected_problem_features(self):
        """
        W26: Gibt Liste aller selektierten Problem-Features zurück.

        Returns:
            List[(feature, body)]: Liste von (Feature, Body) Tupeln mit Problem-Status
        """
        features = self.get_selected_features()
        problem_features = []

        for feature, body in features:
            status = str(getattr(feature, 'status', 'OK') or 'OK')
            details = _safe_details(getattr(feature, 'status_details', None))
            status_class = str(details.get('status_class', '') or '')
            severity = str(details.get('severity', '') or '')

            if status in ('ERROR', 'WARNING') or \
               status_class in ('ERROR', 'WARNING_RECOVERABLE', 'BLOCKED', 'CRITICAL') or \
               severity in ('error', 'warning', 'blocked', 'critical'):
                problem_features.append((feature, body))

        return problem_features

    def batch_retry_selected(self):
        """W26: Löst Batch-Retry-Rebuild für alle selektierten Problem-Features aus."""
        problem_features = self.get_selected_problem_features()
        if problem_features:
            self.batch_retry_rebuild.emit(problem_features)
            logger.debug(f"[BROWSER] Batch retry rebuild für {len(problem_features)} Features")

    def batch_open_selected_diagnostics(self):
        """W26: Löst Batch-Open-Diagnostics für alle selektierten Problem-Features aus."""
        problem_features = self.get_selected_problem_features()
        if problem_features:
            self.batch_open_diagnostics.emit(problem_features)
            logger.debug(f"[BROWSER] Batch open diagnostics für {len(problem_features)} Features")

    def batch_isolate_selected_bodies(self):
        """W26: Isoliert alle Bodies mit selektierten Problem-Features."""
        problem_features = self.get_selected_problem_features()
        bodies = set()

        for _, body in problem_features:
            if body:
                bodies.add(body)

        if bodies:
            self.batch_isolate_bodies.emit(list(bodies))
            logger.debug(f"[BROWSER] Batch isolate {len(bodies)} Bodies")

    def batch_unhide_selected_bodies(self):
        """W28: Macht alle versteckten Bodies sichtbar."""
        all_bodies = []
        if self.document:
            try:
                all_bodies = self.document.get_all_bodies()
            except Exception:
                all_bodies = []

        # Finde alle versteckten Bodies
        hidden_bodies = []
        for body in all_bodies:
            if body and not self.body_visibility.get(body.id, True):
                hidden_bodies.append(body)

        if hidden_bodies:
            # Mache alle sichtbar
            for body in hidden_bodies:
                self.body_visibility[body.id] = True
            self.batch_unhide_bodies.emit(hidden_bodies)
            self.refresh()
            self.visibility_changed.emit()
            logger.debug(f"[BROWSER] Batch unhide {len(hidden_bodies)} Bodies")

    def batch_focus_selected_features(self):
        """W28: Fokus auf alle selektierten Features im Viewport."""
        selected_features = self.get_selected_features()

        if selected_features:
            self.batch_focus_features.emit(selected_features)
            logger.debug(f"[BROWSER] Batch focus {len(selected_features)} Features")

    # =========================================================================
    # W30 PRODUCT LEAP: BATCH RECOVERY ORCHESTRATION
    # =========================================================================

    def batch_recover_selected_features(self):
        """
        W30: Batch-Recovery-Orchestrierung für ausgewählte Problem-Features.

        Führt eine intelligente Recovery-Aktionssequenz aus:
        1. Sammle alle Problem-Features und ihre Bodies
        2. Mache Bodies sichtbar
        3. Führe Recovery-Aktion aus (je nach Error-Code)
        4. Bereinige Selektion nach Aktion
        """
        problem_features = self.get_selected_problem_features()

        if not problem_features:
            logger.debug("[BROWSER] Batch Recovery: Keine Problem-Features ausgewählt")
            return

        # W30: Bodies sichtbar machen (Unhide)
        affected_bodies = set()
        for feature, body in problem_features:
            if body:
                affected_bodies.add(body)

        # Alle betroffenen Bodies sichtbar machen
        for body in affected_bodies:
            self.body_visibility[body.id] = True

        # Batch-Rebuild-Signal emittieren
        self.batch_retry_rebuild.emit(problem_features)

        logger.info(f"[BROWSER] Batch Recovery: {len(problem_features)} Features in {len(affected_bodies)} Bodies")

        # W30: Selektion nach Aktion bereinigen (stale state vermeiden)
        self._clear_selection_after_batch_action()

    def _clear_selection_after_batch_action(self):
        """
        W30: Bereinigt die Selektion nach Batch-Aktionen.

        Verhindert stale-selection States nach Batch-Operationen.
        """
        self.tree.clearSelection()
        logger.debug("[BROWSER] Selektion nach Batch-Aktion bereinigt")

    def batch_diagnostics_selected_features(self):
        """
        W30: Batch-Diagnostics-Orchestrierung.

        Öffnet Diagnostics-Panel für die ersten 3 Problem-Features
        und zeigt eine Zusammenfassung an.
        """
        problem_features = self.get_selected_problem_features()

        if not problem_features:
            logger.debug("[BROWSER] Batch Diagnostics: Keine Problem-Features ausgewählt")
            return

        # W30: Statistik sammeln
        error_types = {}
        for feature, body in problem_features:
            details = _safe_details(getattr(feature, "status_details", None))
            code = details.get("code", "unknown")
            error_types[code] = error_types.get(code, 0) + 1

        # Zusammenfassung loggen
        summary = ", ".join([f"{code}: {count}" for code, count in error_types.items()])
        logger.info(f"[BROWSER] Batch Diagnostics: {len(problem_features)} Features ({summary})")

        # Diagnostics-Signal für erstes Feature emittieren
        self.batch_open_diagnostics.emit(problem_features)

        # W30: Selektion bereinigen
        self._clear_selection_after_batch_action()

    def get_batch_selection_summary(self) -> dict:
        """
        W30: Gibt eine Zusammenfassung der aktuellen Selektion zurück.

        Returns:
            dict mit keys: total_features, problem_features, bodies,
                          hidden_bodies, error_types
        """
        selected_features = self.get_selected_features()
        problem_features = self.get_selected_problem_features()

        bodies = set()
        hidden_bodies = set()
        error_types = {}

        for feature, body in problem_features:
            if body:
                bodies.add(body)
                if not self.body_visibility.get(body.id, True):
                    hidden_bodies.add(body)

            details = _safe_details(getattr(feature, "status_details", None))
            code = details.get("code", "unknown")
            error_types[code] = error_types.get(code, 0) + 1

        return {
            "total_features": len(selected_features),
            "problem_features": len(problem_features),
            "bodies": len(bodies),
            "hidden_bodies": len(hidden_bodies),
            "error_types": error_types,
        }

    def recover_and_focus_selected(self):
        """
        W30: Workflow-Leap 'Recover & Focus' - Kombinierte Aktion.

        Führt einen vollständigen Recovery-Workflow aus:
        1. Problematische Features sammeln
        2. Betroffene Bodies sichtbar machen
        3. Viewport-Fokus auf Bodies
        4. Detailpanel öffnen mit erstem Problem-Feature

        Diese Aktion ist stabil bei leeren/inkonsistenten Inputs.
        """
        problem_features = self.get_selected_problem_features()

        if not problem_features:
            logger.debug("[BROWSER] Recover & Focus: Keine Problem-Features ausgewählt")
            return

        # W30: Guards gegen leere/inkonsistente Inputs
        if not self.document:
            logger.warning("[BROWSER] Recover & Focus: Kein Dokument geladen")
            return

        # 1. Bodies sammeln und sichtbar machen
        affected_bodies = set()
        for feature, body in problem_features:
            if body and hasattr(body, 'id'):
                affected_bodies.add(body)
                self.body_visibility[body.id] = True

        if not affected_bodies:
            logger.warning("[BROWSER] Recover & Focus: Keine gültigen Bodies gefunden")
            return

        # 2. Viewport-Fokus emittieren
        feature_body_pairs = [(f, b) for f, b in problem_features if b]
        if feature_body_pairs:
            self.batch_focus_features.emit(feature_body_pairs)

        # 3. Detailpanel öffnen mit erstem Problem-Feature
        first_feature, first_body = problem_features[0]
        if first_feature and first_body:
            self.feature_selected.emit(("feature", first_feature, first_body))

        # 4. Refresh für Sichtbarkeit
        self.refresh()
        self.visibility_changed.emit()

        logger.info(f"[BROWSER] Recover & Focus: {len(problem_features)} Features in {len(affected_bodies)} Bodies")

    def show_rollback_bar(self, body):
        """Show rollback slider for a body with features."""
        if not body or not hasattr(body, 'features') or not body.features:
            self.rollback_frame.setVisible(False)
            self._rollback_body = None
            return
        self._rollback_body = body
        n = len(body.features)
        rb = body.rollback_index if body.rollback_index is not None else n
        self.rollback_slider.blockSignals(True)
        self.rollback_slider.setRange(0, n)
        self.rollback_slider.setValue(rb)
        self.rollback_slider.blockSignals(False)
        self.rollback_label.setText(f"{rb}/{n}")
        self.rollback_frame.setVisible(True)

    def _on_rollback_changed(self, value):
        """Slider value changed - emit rollback signal."""
        if not self._rollback_body:
            return
        n = len(self._rollback_body.features)
        self.rollback_label.setText(f"{value}/{n}")
        idx = value if value < n else None  # None = all features
        self._rollback_body.rollback_index = idx
        self.rollback_changed.emit(self._rollback_body, value)

    # =========================================================================
    # W21 PAKET A: FILTER UND NAVIGATION
    # =========================================================================

    def _on_filter_changed(self, index):
        """
        W21 Paket A: Handler für Filter-Änderung.

        Wendet den gewählten Filter auf den Tree an und aktualisiert
        das Problembadge.

        W29 Closeout: Bereinigt Batch-State bei Filterwechsel um Korruption zu vermeiden.
        """
        # W29: Batch-State bereinigen vor Filterwechsel
        self._clear_batch_state_on_filter_change()

        mode_data = self.filter_combo.itemData(index)
        if mode_data:
            self.tree.set_filter_mode(mode_data)
            self.filter_changed.emit(mode_data)
            self._update_problem_badge()
            logger.debug(f"[BROWSER] Filter geändert zu: {mode_data}")

    def _clear_batch_state_on_filter_change(self):
        """
        W29 Closeout: Bereinigt Batch-State bei Filterwechsel.

        Verhindert dass ausgeblendete Items im Batch-State verbleiben
        was zu inkonsistentem Verhalten führen würde.
        """
        # Selektion bereinigen: Nur sichtbare Items dürfen selektiert bleiben
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return

        # Deselektiere alle versteckten Items
        for item in selected_items:
            if item.isHidden():
                item.setSelected(False)

        # Wenn nach Bereinigung keine Selektion mehr übrig, Status aktualisieren
        remaining_selected = self.tree.selectedItems()
        if not remaining_selected and selected_items:
            logger.debug("[BROWSER] Batch-State bereinigt: Alle selektierten Items wurden durch Filter ausgeblendet")

    def _update_problem_badge(self):
        """W21 Paket A: Aktualisiert das Problembadge mit der Anzahl der Problem-Features."""
        if not self.document:
            self.problem_badge.setVisible(False)
            return

        problem_count = 0

        # Alle Bodies und Features durchsuchen
        try:
            all_bodies = self.document.get_all_bodies()
            if all_bodies is None:
                all_bodies = []
        except Exception:
            all_bodies = []
        for body in all_bodies:
            if body is None:
                continue
            if hasattr(body, 'features'):
                try:
                    features = body.features
                    if features is None:
                        continue
                    for feature in features:
                        if feature is None:
                            continue
                        status = str(getattr(feature, 'status', 'OK') or 'OK')
                        details = _safe_details(getattr(feature, 'status_details', None))
                        status_class = str(details.get('status_class', '') or '')
                        severity = str(details.get('severity', '') or '')

                        if status in ('ERROR', 'WARNING') or \
                           status_class in ('ERROR', 'WARNING_RECOVERABLE', 'BLOCKED', 'CRITICAL') or \
                           severity in ('error', 'warning', 'blocked', 'critical'):
                            problem_count += 1
                except (TypeError, AttributeError):
                    # features ist möglicherweise kein Iterable
                    continue

        if problem_count > 0:
            self.problem_badge.setText(str(problem_count))
            self.problem_badge.setVisible(True)

            # Badge-Farbe basierend auf Filter-Modus
            mode = self.filter_combo.currentData()
            if mode == 'errors':
                self.problem_badge.setStyleSheet(f"""
                    background: #ef4444;
                    color: white;
                    border-radius: 8px;
                    padding: 1px 6px;
                    font-size: 9px;
                    font-weight: bold;
                """)
            elif mode == 'warnings':
                self.problem_badge.setStyleSheet(f"""
                    background: #f59e0b;
                    color: white;
                    border-radius: 8px;
                    padding: 1px 6px;
                    font-size: 9px;
                    font-weight: bold;
                """)
            elif mode == 'blocked':
                self.problem_badge.setStyleSheet(f"""
                    background: #f97316;
                    color: white;
                    border-radius: 8px;
                    padding: 1px 6px;
                    font-size: 9px;
                    font-weight: bold;
                """)
            else:
                self.problem_badge.setStyleSheet(f"""
                    background: {DesignTokens.COLOR_ERROR.name()};
                    color: white;
                    border-radius: 8px;
                    padding: 1px 6px;
                    font-size: 9px;
                    font-weight: bold;
                """)
        else:
            self.problem_badge.setVisible(False)

    def schedule_refresh(self):
        """
        W21 Paket A: Verzögertes Refresh um Flackern zu vermeiden.

        Statt sofortigem refresh() wird ein Timer gestartet, der
        nach 50ms den tatsächlichen Refresh durchführt. Wenn innerhalb
        dieses Zeitraums erneut schedule_refresh() aufgerufen wird,
        wird der Timer zurückgesetzt.
        """
        self._refresh_pending = True
        self._refresh_timer.start(50)  # 50ms Verzögerung

    def _do_refresh(self):
        """W21 Paket A: Führt den eigentlichen Refresh durch."""
        if self._refresh_pending:
            self._refresh_pending = False
            self.refresh()
            self._update_problem_badge()

    def refresh(self):
        """W26 Paket F1: Verbesserte refresh() mit Anti-Flicker und Performance-Optimierung."""
        # W26: Anti-Flicker durch Updates-Blocker
        self.tree.setUpdatesEnabled(False)
        # W26: Scroll-Position merken für konsistentes UX
        scroll_pos = self.tree.verticalScrollBar().value() if self.tree.verticalScrollBar() else 0

        try:
            self._do_tree_build()
        finally:
            # W26: Filter nach dem Build erneut anwenden
            if hasattr(self.tree, '_filter_mode'):
                self.tree._apply_filter()
            # W26: Scroll-Position wiederherstellen
            if self.tree.verticalScrollBar():
                self.tree.verticalScrollBar().setValue(scroll_pos)
            self.tree.setUpdatesEnabled(True)

        # W26: Problembadge aktualisieren
        self._update_problem_badge()

    def _do_tree_build(self):
        """Interne Methode für den Tree-Aufbau (von refresh() aufgerufen)."""
        self.tree.clear()
        if not self.document:
            return

        # Root: Document
        root = QTreeWidgetItem(self.tree, [f"{self.document.name}"])
        root.setExpanded(True)
        root.setForeground(0, QColor("#ddd"))

        # Origin (Standard-Ebenen) - eingeklappt
        origin = QTreeWidgetItem(root, ["◎ Origin"])
        origin.setExpanded(False)
        origin.setForeground(0, QColor("#666"))

        planes = [
            ("XY Plane (Top)", "xy", "#5588dd"),
            ("XZ Plane (Front)", "xz", "#55dd88"),
            ("YZ Plane (Right)", "yz", "#dd8855"),
        ]
        for name, plane_id, color in planes:
            item = QTreeWidgetItem(origin, [f"▬ {name}"])
            item.setData(0, Qt.UserRole, ('plane', plane_id))
            item.setForeground(0, QColor(color))

        axes = [("X Axis", "x", "#dd5555"), ("Y Axis", "y", "#55dd55"), ("Z Axis", "z", "#5555dd")]
        for name, axis_id, color in axes:
            item = QTreeWidgetItem(origin, [f"→ {name}"])
            item.setData(0, Qt.UserRole, ('axis', axis_id))
            item.setForeground(0, QColor(color))

        # Construction Planes (Offset Planes)
        if hasattr(self.document, 'planes') and self.document.planes:
            for cp in self.document.planes:
                vis = self.plane_visibility.get(cp.id, True)
                icon = "●" if vis else "○"
                item = QTreeWidgetItem(origin, [f"{icon} ▬ {cp.name}"])
                item.setData(0, Qt.UserRole, ('construction_plane', cp))
                item.setForeground(0, QColor("#bb88dd" if vis else "#555"))

        # =========================================================================
        # Phase 3 Assembly: Component-Hierarchie oder Legacy-Modus
        # =========================================================================
        if self._assembly_enabled and hasattr(self.document, 'root_component') and self.document.root_component:
            # Assembly-Modus: Component-Hierarchie anzeigen
            self._add_component_to_tree(root, self.document.root_component)
        else:
            # Legacy-Modus: Flache Struktur wie bisher
            if self.document.bodies or self.document.sketches:
                comp = QTreeWidgetItem(root, ["⊞ Component1"])
                comp.setExpanded(True)
                comp.setForeground(0, QColor("#b8b8b8"))
                comp.setData(0, Qt.UserRole, ('component', None))

                # Sketches unter Component
                for s in self.document.sketches:
                    vis = self.sketch_visibility.get(s.id, True)
                    icon = "●" if vis else "○"
                    item = QTreeWidgetItem(comp, [f"{icon} {s.name}"])
                    item.setData(0, Qt.UserRole, ('sketch', s))
                    item.setForeground(0, QColor("#7cb3f7" if vis else "#555"))

                # Bodies unter Component
                self._add_bodies_to_tree(comp, self.document.bodies)

    def _on_next_problem(self):
        """W21: Handler für Ctrl+Down - Nächstes Problem-Item."""
        self.tree.navigate_to_next_problem()
        # Status-Bar aktualisieren wenn verfügbar
        logger.debug("[BROWSER] Navigation: Nächstes Problem-Item")

    def _on_prev_problem(self):
        """W21: Handler für Ctrl+Up - Vorheriges Problem-Item."""
        self.tree.navigate_to_prev_problem()
        logger.debug("[BROWSER] Navigation: Vorheriges Problem-Item")

    def _on_next_item(self):
        """W21: Handler für Ctrl+N - Nächstes Item."""
        self.tree.navigate_to_next_item()
        logger.debug("[BROWSER] Navigation: Nächstes Item")

    def _on_prev_item(self):
        """W21: Handler für Ctrl+P - Vorheriges Item."""
        self.tree.navigate_to_prev_item()
        logger.debug("[BROWSER] Navigation: Vorheriges Item")

    def get_problem_count(self) -> int:
        """W21 Paket A: Gibt die Anzahl der Problem-Features zurück."""
        if not self.document:
            return 0

        count = 0
        try:
            all_bodies = self.document.get_all_bodies()
        except Exception:
            return 0
        for body in all_bodies:
            if hasattr(body, 'features'):
                for feature in body.features:
                    status = str(getattr(feature, 'status', 'OK') or 'OK')
                    details = _safe_details(getattr(feature, 'status_details', None))
                    status_class = str(details.get('status_class', '') or '')
                    severity = str(details.get('severity', '') or '')

                    if status in ('ERROR', 'WARNING') or \
                       status_class in ('ERROR', 'WARNING_RECOVERABLE', 'BLOCKED', 'CRITICAL') or \
                       severity in ('error', 'warning', 'blocked', 'critical'):
                        count += 1
        return count

    def get_filtered_features(self) -> list:
        """W21 Paket A: Gibt die gefilterten Features zurück."""
        if not self.document:
            return []

        mode = self.filter_combo.currentData() or 'all'
        result = []

        try:
            all_bodies = self.document.get_all_bodies()
        except Exception:
            return []
        for body in all_bodies:
            if hasattr(body, 'features'):
                for feature in body.features:
                    status = str(getattr(feature, 'status', 'OK') or 'OK')
                    details = _safe_details(getattr(feature, 'status_details', None))
                    status_class = str(details.get('status_class', '') or '')
                    severity = str(details.get('severity', '') or '')

                    include = False
                    if mode == 'all':
                        include = True
                    elif mode == 'errors':
                        include = status in ('ERROR',) or status_class in ('ERROR', 'CRITICAL')
                    elif mode == 'warnings':
                        include = status in ('WARNING', 'ERROR') or status_class in ('WARNING_RECOVERABLE', 'BLOCKED')
                    elif mode == 'blocked':
                        include = status_class in ('BLOCKED',) or severity == 'blocked'

                    if include:
                        result.append((feature, body))

        return result

    def set_filter_mode(self, mode: str):
        """W21 Paket A: Setzt den Filter-Modus programmatisch."""
        for i in range(self.filter_combo.count()):
            if self.filter_combo.itemData(i) == mode:
                self.filter_combo.setCurrentIndex(i)
                break
