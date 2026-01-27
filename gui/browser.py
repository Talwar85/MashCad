"""
MashCad - Project Browser (Fusion360-Style)
Collapsible tree with Origin planes, Components, Sketches, Bodies
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTreeWidget, QTreeWidgetItem, QMenu, QSizePolicy,
    QToolButton, QScrollArea, QSlider
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QColor

from i18n import tr


class ProjectBrowser(QFrame):
    """Fusion360-style Project Browser - collapsible"""
    
    feature_selected = Signal(object)
    feature_double_clicked = Signal(object)
    feature_deleted = Signal(object, object)  # NEU: (feature, body)
    visibility_changed = Signal()
    body_vis_changed = Signal(str, bool)
    plane_selected = Signal(str)
    construction_plane_selected = Signal(object)  # ConstructionPlane
    construction_plane_vis_changed = Signal(str, bool)  # (plane_id, visible)
    collapsed_changed = Signal(bool)
    rollback_changed = Signal(object, int)  # (body, rollback_index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._expanded_width = 180
        
        self.setStyleSheet("""
            QFrame { 
                background: #1e1e1e; 
                border: none;
            }
        """)
        
        self.document = None
        self.sketch_visibility = {}
        self.body_visibility = {}
        self.plane_visibility = {}
        
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
        header.setStyleSheet("background: #2d2d30; border-bottom: 1px solid #3f3f46;")
        header.setFixedHeight(28)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        header_layout.setSpacing(4)
        
        title = QLabel("BROWSER")
        title.setStyleSheet("color: #0078d4; font-weight: bold; font-size: 10px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        content_layout.addWidget(header)
        
        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)  # Multi-Select aktivieren
        self.tree.setStyleSheet("""
            QTreeWidget { 
                background: #1e1e1e; 
                border: none; 
                color: #ccc;
                font-size: 11px;
                outline: none;
            }
            QTreeWidget::item { 
                padding: 2px 4px;
                border: none;
            }
            QTreeWidget::item:hover { 
                background: #2a2d2e; 
            }
            QTreeWidget::item:selected { 
                background: #0e4f7d; 
            }
        """)
        self.tree.itemClicked.connect(self._on_click)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        
        content_layout.addWidget(self.tree)

        # === ROLLBACK BAR ===
        self.rollback_frame = QFrame()
        self.rollback_frame.setStyleSheet("background: #2d2d30; border-top: 1px solid #3f3f46;")
        self.rollback_frame.setFixedHeight(40)
        self.rollback_frame.setVisible(False)
        rb_layout = QHBoxLayout(self.rollback_frame)
        rb_layout.setContentsMargins(6, 2, 6, 2)

        rb_label = QLabel("⏪")
        rb_label.setStyleSheet("color: #0078d4; font-size: 12px;")
        rb_layout.addWidget(rb_label)

        self.rollback_slider = QSlider(Qt.Horizontal)
        self.rollback_slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #3f3f46; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #0078d4; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::sub-page:horizontal { background: #0078d4; border-radius: 2px; }
        """)
        self.rollback_slider.valueChanged.connect(self._on_rollback_changed)
        rb_layout.addWidget(self.rollback_slider)

        self.rollback_label = QLabel("")
        self.rollback_label.setStyleSheet("color: #999; font-size: 10px; min-width: 30px;")
        rb_layout.addWidget(self.rollback_label)

        content_layout.addWidget(self.rollback_frame)

        self._rollback_body = None

        self.main_layout.addWidget(self.content)
        
        # === COLLAPSE BAR (rechts vom Content) ===
        self.collapse_bar = QFrame()
        self.collapse_bar.setFixedWidth(16)
        self.collapse_bar.setStyleSheet("""
            QFrame { 
                background: #2d2d30; 
                border-left: 1px solid #3f3f46;
            }
            QFrame:hover {
                background: #3e3e42;
            }
        """)
        self.collapse_bar.setCursor(Qt.PointingHandCursor)
        self.collapse_bar.mousePressEvent = self._toggle_collapse
        
        collapse_layout = QVBoxLayout(self.collapse_bar)
        collapse_layout.setContentsMargins(0, 0, 0, 0)
        collapse_layout.setAlignment(Qt.AlignCenter)
        
        self.collapse_icon = QLabel("◀")
        self.collapse_icon.setStyleSheet("color: #888; font-size: 10px;")
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
            for s in doc.sketches:
                if s.id not in self.sketch_visibility:
                    self.sketch_visibility[s.id] = True
            for b in doc.bodies:
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

        # Components Container
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
            for b in self.document.bodies:
                vis = self.body_visibility.get(b.id, True)
                icon = "●" if vis else "○"
                bi = QTreeWidgetItem(comp, [f"{icon} {b.name}"])
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
    
    def get_visible_sketches(self):
        if not self.document:
            return []
        return [(s, self.sketch_visibility.get(s.id, True)) for s in self.document.sketches]
    
    def get_visible_bodies(self):
        """Gibt Liste von (body, is_visible) Tupeln zurück"""
        if not self.document:
            return []
        return [(b, self.body_visibility.get(b.id, True)) for b in self.document.bodies]
    
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
            self.feature_double_clicked.emit(data)
    
    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2d2d30; color: #ddd; border: 1px solid #3f3f46; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #0078d4; }
            QMenu::separator { height: 1px; background: #3f3f46; margin: 4px 8px; }
        """)
        
        if data[0] == 'sketch':
            menu.addAction(tr("Edit"), lambda: self.feature_double_clicked.emit(data))
            vis = self.sketch_visibility.get(data[1].id, True)
            menu.addAction(tr("Hide") if vis else tr("Show"), lambda: self._toggle_vis(data[1], 'sketch'))
            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_sketch(data[1]))
            
        elif data[0] == 'body':
            vis = self.body_visibility.get(data[1].id, True)
            menu.addAction(tr("Hide") if vis else tr("Show"), lambda: self._toggle_vis(data[1], 'body'))
            menu.addSeparator()
            menu.addAction(tr("Delete"), lambda: self._del_body(data[1]))
            
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
            menu.addAction(tr("New Sketch"), lambda: self.plane_selected.emit('xy'))
            menu.addAction(tr("New Component"), lambda: None)  # TODO

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

