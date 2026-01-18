"""
MashCad - Sketch Dialogs
DimensionInput and ToolOptionsPopup for the 2D sketch editor
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QGraphicsDropShadowEffect, QWidget,
    QSizePolicy, QLayout, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QRectF
from PySide6.QtGui import QColor, QPalette, QPainter, QBrush, QPen, QFont


class DimensionInput(QFrame):
    """
    Fusion360-style Floating Input.
    Dunkel, Semi-Transparent, mit Schatten und direktem Feedback.
    """
    value_changed = Signal(str, float)
    choice_changed = Signal(str, str)
    confirmed = Signal()
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Wichtig: Frameless und Tool-Flag, damit es über dem Canvas schwebt
        # aber keine eigenen Fensterrahmen hat.
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground) 
        
        # Schatten für Tiefenwirkung (Pop-out Effekt)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 4)
        self.layout.setSpacing(8)
        
        self.fields = {}
        self.field_order = []
        self.field_types = {} 
        self.active_field = 0
        self.locked_fields = set()
        
        self.hide()

    def paintEvent(self, event):
        """Custom Paint für abgerundeten, dunklen Hintergrund"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Hintergrund (Dunkelgrau, leicht transparent)
        bg_color = QColor(35, 35, 35, 240)
        border_color = QColor(60, 60, 60)
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 6, 6)

    def setup(self, fields):
        # Altes Layout leeren
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            elif child.layout(): child.layout().deleteLater()

        self.fields.clear()
        self.field_order.clear()
        self.field_types.clear()
        self.locked_fields.clear()
        
        for i, item in enumerate(fields):
            label_text, key = item[0], item[1]
            val = item[2]
            
            # Container für Label + Input
            vbox = QVBoxLayout()
            vbox.setSpacing(1)
            vbox.setContentsMargins(0,0,0,0)
            
            # Label (Klein über dem Feld, wie Fusion)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #aaa; font-size: 10px; font-weight: bold; margin-left: 2px;")
            vbox.addWidget(lbl)
            
            # Input Widget
            if isinstance(item[3], list): # Dropdown
                self.field_types[key] = 'choice'
                widget = QComboBox()
                widget.addItems(item[3])
                if isinstance(val, int) and val < len(item[3]):
                    widget.setCurrentIndex(val)
                elif isinstance(val, str):
                    widget.setCurrentText(val)
                
                # Styling für ComboBox
                widget.setStyleSheet("""
                    QComboBox {
                        background: #2d2d30; border: 1px solid #444; border-radius: 3px;
                        color: white; padding: 2px 4px; min-width: 70px;
                    }
                    QComboBox::drop-down { border: none; }
                """)
                widget.currentTextChanged.connect(lambda t, k=key: self.choice_changed.emit(k, t))
                
            else: # Float/Text Input
                self.field_types[key] = 'float'
                widget = QLineEdit()
                widget.setText(f"{val:.2f}")
                widget.setFixedWidth(70)
                
                # Styling für LineEdit
                widget.setStyleSheet("""
                    QLineEdit {
                        background: #252526; border: 1px solid #444; border-radius: 3px;
                        color: white; font-family: Consolas, monospace; font-weight: bold;
                        padding: 3px; selection-background-color: #0078d4;
                    }
                    QLineEdit:focus { border: 1px solid #0078d4; background: #1e1e1e; }
                """)
                
                widget.returnPressed.connect(self._on_confirm)
                widget.textEdited.connect(lambda t, k=key: self._on_user_edit(k, t))
                widget.textChanged.connect(lambda t, k=key: self._on_text_changed(k, t))
            
            vbox.addWidget(widget)
            self.layout.addLayout(vbox)
            
            self.fields[key] = widget
            self.field_order.append(key)
            
            # Separator (außer beim letzten)
            if i < len(fields) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.VLine)
                line.setStyleSheet("color: #444;")
                self.layout.addWidget(line)

        self.adjustSize()

    def _on_user_edit(self, key, text):
        self.locked_fields.add(key)
        # Visuelles Feedback: Schloss-Symbol oder Farbe ändern
        if key in self.fields:
            self.fields[key].setStyleSheet("""
                QLineEdit {
                    background: #1e1e1e; border: 1px solid #dcdcaa; 
                    color: #dcdcaa; font-weight: bold;
                }
            """)

    def _on_text_changed(self, key, text):
        try:
            val = float(text.replace(',', '.'))
            self.value_changed.emit(key, val)
        except ValueError:
            pass

    def _on_confirm(self):
        self.confirmed.emit()

    def get_values(self):
        result = {}
        for key, widget in self.fields.items():
            if self.field_types[key] == 'float':
                try: 
                    result[key] = float(widget.text().replace(',', '.'))
                except: 
                    result[key] = 0.0
            elif self.field_types[key] == 'choice':
                result[key] = widget.currentText()
        return result

    def set_value(self, key, value):
        if key in self.fields and key not in self.locked_fields:
            if self.field_types[key] == 'float':
                self.fields[key].setText(f"{value:.2f}")

    def focus_field(self, index=0):
        if 0 <= index < len(self.field_order):
            self.active_field = index
            widget = self.fields[self.field_order[index]]
            widget.setFocus()
            if isinstance(widget, QLineEdit):
                widget.selectAll()

    def next_field(self):
        self.active_field = (self.active_field + 1) % len(self.field_order)
        self.focus_field(self.active_field)

    def is_locked(self, key):
        return key in self.locked_fields

    def unlock_all(self):
        self.locked_fields.clear()
        # Reset Styles
        for key, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.setStyleSheet("""
                    QLineEdit {
                        background: #252526; border: 1px solid #444; border-radius: 3px;
                        color: white; font-family: Consolas, monospace; font-weight: bold;
                        padding: 3px; selection-background-color: #0078d4;
                    }
                    QLineEdit:focus { border: 1px solid #0078d4; background: #1e1e1e; }
                """)

class ToolOptionsPopup(QFrame):
    """
    Kleine Kontext-Palette neben dem Mauszeiger (z.B. für Polygon-Seiten, Kreis-Typ).
    """
    option_selected = Signal(str, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Minimale Breite etwas erhöht für Text
        self.setMinimumWidth(140) 
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)
        
        # Größe passt sich Inhalt an
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #ccc; font-size: 10px; font-weight: bold; text-transform: uppercase; margin-bottom: 2px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title_label)
        
        # ÄNDERUNG: Grid statt HBox für mehrreihiges Layout
        self.button_layout = QGridLayout()
        self.button_layout.setSpacing(4)
        self.button_layout.setContentsMargins(0,0,0,0)
        self.layout.addLayout(self.button_layout)
        
        self.buttons = []
        self.current_option = None
        self.option_name = None
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(35, 35, 40, 250)))
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

    def show_options(self, title, option_name, options, current_value=0):
        self.title_label.setText(title)
        self.option_name = option_name
        
        # Buttons aufräumen (Grid Layout Items entfernen)
        while self.button_layout.count():
            item = self.button_layout.takeAt(0)
            if item.widget(): 
                item.widget().deleteLater()
        self.buttons.clear()
        
        # KONFIGURATION: Maximale Spalten bevor umgebrochen wird
        # Bei langen Texten ist 2 gut. Bei kurzen Icons eher 3 oder 4.
        MAX_COLUMNS = 2 
        
        for i, (icon, label) in enumerate(options):
            btn = QPushButton(f" {icon}  {label} ")
            btn.setToolTip(label)
            btn.setCheckable(True)
            
            # Damit Buttons im Grid den Platz füllen
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            is_active = False
            if isinstance(current_value, int) and i == current_value: is_active = True
            
            btn.setChecked(is_active)
            btn.setFixedHeight(32)
            
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.05); 
                    border: 1px solid rgba(255, 255, 255, 0.1); 
                    border-radius: 4px;
                    color: #e0e0e0; 
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0 10px;
                    text-align: left; /* Text linksbündig sieht im Grid oft besser aus */
                }
                QPushButton:hover { background: rgba(255,255,255,0.15); border-color: #aaa; }
                QPushButton:checked { 
                    background: rgba(0, 120, 212, 1.0); 
                    border: 1px solid #0078d4; 
                    color: white; 
                }
            """)
            
            btn.clicked.connect(lambda checked, idx=i: self._on_option_clicked(idx))
            
            # Gitter-Logik: Zeile und Spalte berechnen
            row = i // MAX_COLUMNS
            col = i % MAX_COLUMNS
            self.button_layout.addWidget(btn, row, col)
            
            self.buttons.append(btn)
        
        self.layout.activate()
        self.adjustSize() 
        
        self.show()
        self.raise_()

    def _on_option_clicked(self, index):
        for i, btn in enumerate(self.buttons):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)
        self.option_selected.emit(self.option_name, index)

    def position_smart(self, parent_widget, offset_x=15, offset_y=15):
        # ... (diese Methode bleibt unverändert wie im vorherigen Schritt) ...
        from PySide6.QtGui import QCursor
        
        self.adjustSize()
        mouse_pos = QCursor.pos()
        if parent_widget:
            local_pos = parent_widget.mapFromGlobal(mouse_pos)
        else:
            local_pos = mouse_pos

        x = local_pos.x() + offset_x
        y = local_pos.y() + offset_y
        
        if parent_widget:
            pw = parent_widget.width()
            ph = parent_widget.height()
            w = self.width()
            h = self.height()
            if x + w > pw - 10: x = local_pos.x() - w - offset_x
            if y + h > ph - 10: y = local_pos.y() - h - offset_y
            if x < 10: x = 10
            if y < 10: y = 10

        self.move(int(x), int(y))
        self.raise_()