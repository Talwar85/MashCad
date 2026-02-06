"""
MashCad - Project Browser (Fusion360-Style)
Collapsible tree with Origin planes, Components, Sketches, Bodies

Phase 3 Assembly: Unterstützt hierarchische Component-Struktur
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTreeWidget, QTreeWidgetItem, QMenu, QSizePolicy,
    QToolButton, QScrollArea, QSlider, QInputDialog, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QFont, QIcon, QColor, QDrag
from loguru import logger

from i18n import tr
from config.feature_flags import is_enabled
from gui.design_tokens import DesignTokens


class DraggableTreeWidget(QTreeWidget):
    """
    QTreeWidget mit Drag & Drop Support für Bodies/Sketches zwischen Components.

    Phase 6 Assembly: Ermöglicht Drag & Drop von Bodies/Sketches zu anderen Components.
    Keyboard Shortcuts:
    - Enter: Component aktivieren
    - Esc: Zur Root-Component zurück
    - F2: Umbenennen
    """

    # Signal wenn Item gedroppt wird: (item_type, item, source_comp, target_comp)
    item_dropped = Signal(str, object, object, object)

    # Keyboard Shortcuts
    activate_component = Signal(object)      # Enter gedrückt auf Component
    go_to_root = Signal()                    # Esc gedrückt
    rename_requested = Signal(object)        # F2 gedrückt auf Component

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)  # Nicht InternalMove!
        self.setDefaultDropAction(Qt.MoveAction)
        self._drag_item_data = None

    def keyPressEvent(self, event):
        """Keyboard Shortcuts für Component-Operationen."""
        item = self.currentItem()
        data = item.data(0, Qt.UserRole) if item else None

        # Enter: Component aktivieren
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if data and data[0] == 'component' and data[1]:
                self.activate_component.emit(data[1])
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

        # Phase 3 Assembly: Feature Flag prüfen
        self._assembly_enabled = is_enabled("assembly_system")

        self._setup_ui()
    
    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # === CONTENT AREA ===
        self.content = QWidget()
        self.content.setMinimumWidth(160)
        self.content.setMaximumWidth(220)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Header mit Collapse-Button
        header = QFrame()
        header.setStyleSheet(f"background: {DesignTokens.COLOR_BG_PANEL.name()}; border-bottom: 1px solid {DesignTokens.COLOR_BORDER.name()};")
        header.setFixedHeight(28)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        header_layout.setSpacing(4)
        
        title = QLabel("BROWSER")
        title.setStyleSheet(f"color: {DesignTokens.COLOR_PRIMARY.name()}; font-weight: bold; font-size: 10px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        content_layout.addWidget(header)
        
        # Tree Widget - Phase 6: Mit Drag & Drop Support
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
                        color = "#cc5555"
                    fi = QTreeWidgetItem(bi, [f"{prefix} {f.name}"])
                    fi.setData(0, Qt.UserRole, ('feature', f, b))
                    fi.setForeground(0, QColor(color))

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
            # NEU: Feature-Kontext-Menü (Edit, Delete)
            feature = data[1]
            body = data[2]

            menu.addAction(tr("Edit"), lambda: self.feature_double_clicked.emit(data))
            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_feature(feature, body))

        menu.exec(self.tree.mapToGlobal(pos))
    
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
        if not self._assembly_enabled or not self.document:
            return

        # Signal emittieren - MainWindow handhabt die Aktivierung
        self.component_activated.emit(component)
        logger.debug(f"[BROWSER] Component aktivieren: {component.name}")

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

