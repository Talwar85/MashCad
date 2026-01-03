"""
LiteCAD - Sketch Dialogs
DimensionInput and ToolOptionsPopup for the 2D sketch editor
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt, Signal


class DimensionInput(QFrame):
    """Fusion360-style Eingabefeld mit Lock-Funktionalität und Options-Support"""
    value_changed = Signal(str, float)
    choice_changed = Signal(str, str) # Neu: Signal für Text-Auswahl
    confirmed = Signal()
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background: #1e1e1e; border: 2px solid #0078d4; border-radius: 6px; }
            QLineEdit, QComboBox { 
                background: #2d2d30; border: 1px solid #555; border-radius: 3px;
                color: #fff; font-size: 14px; font-family: Consolas, monospace; font-weight: bold;
                padding: 4px; selection-background-color: #0078d4;
            }
            QLineEdit:focus, QComboBox:focus { border: 2px solid #0078d4; background: #333; }
            QLabel { color: #0af; font-size: 12px; font-weight: bold; }
        """)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(15)
        self.fields = {}
        self.field_order = []
        self.field_types = {} # 'float' oder 'choice'
        self.active_field = 0
        self.locked_fields = set()
        self.hide()
    
    def setup(self, fields):
        """
        fields: Liste von Tupeln.
        Für Zahlen: (Label, Key, DefaultValue, Suffix)
        Für Auswahl: (Label, Key, DefaultIndex, [Option1, Option2, ...])
        """
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.fields.clear()
        self.field_order.clear()
        self.field_types.clear()
        self.locked_fields.clear()
        
        from PySide6.QtWidgets import QComboBox # Import hier oder oben
        
        for item in fields:
            label, key = item[0], item[1]
            val = item[2]
            
            container = QHBoxLayout()
            container.setSpacing(6)
            lbl = QLabel(label)
            lbl.setFixedWidth(20)
            
            if isinstance(item[3], list): # Es ist eine Auswahl-Box
                self.field_types[key] = 'choice'
                options = item[3]
                widget = QComboBox()
                widget.addItems(options)
                widget.setCurrentIndex(int(val))
                widget.setFixedWidth(110)
                # Signal weiterleiten
                widget.currentTextChanged.connect(lambda t, k=key: self.choice_changed.emit(k, t))
                # Enter im Combo triggert Confirm
                # (QComboBox fängt Enter oft ab, wir müssen eventuell keyPressEvent nutzen)
            else: # Es ist ein Zahlenfeld
                self.field_types[key] = 'float'
                suffix = item[3]
                widget = QLineEdit()
                widget.setFixedWidth(90)
                widget.setText(f"{val:.2f}")
                widget.returnPressed.connect(self._on_confirm)
                widget.textEdited.connect(lambda t, k=key: self._on_user_edit(k, t))
                widget.textChanged.connect(lambda t, k=key: self._on_text_changed(k, t))
                
                suf = QLabel(suffix)
                suf.setFixedWidth(25)
                suf.setStyleSheet("color: #888;")
                container.addWidget(lbl)
                container.addWidget(widget)
                container.addWidget(suf)
            
            if self.field_types[key] == 'choice':
                container.addWidget(lbl)
                container.addWidget(widget)

            self.layout.addLayout(container)
            self.fields[key] = widget
            self.field_order.append(key)
            
        self.active_field = 0
        self.adjustSize()
    
    def _on_user_edit(self, key, text):
        self.locked_fields.add(key)
        if key in self.fields:
            self.fields[key].setStyleSheet("border: 2px solid #0a0; background: #1a3a1a; color: #0f0;")

    def _on_text_changed(self, key, text):
        try: self.value_changed.emit(key, float(text.replace(',', '.')))
        except: pass
    
    def _on_confirm(self):
        self.confirmed.emit()
        
    def get_values(self):
        result = {}
        for key, widget in self.fields.items():
            if self.field_types[key] == 'float':
                try: result[key] = float(widget.text().replace(',', '.'))
                except: result[key] = 0.0
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
            if isinstance(widget, QLineEdit): widget.selectAll()
            elif hasattr(widget, 'showPopup'): widget.showPopup() # Optional: Dropdown öffnen
            
    def next_field(self):
        self.active_field = (self.active_field + 1) % len(self.field_order)
        self.focus_field(self.active_field)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit(); self.hide()
        elif event.key() == Qt.Key_Tab:
            self.next_field(); event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_confirm(); event.accept()
        else:
            super().keyPressEvent(event)

    def is_locked(self, key):
        return key in self.locked_fields

    def unlock_all(self):
        """Hebt alle Sperren auf und setzt das Aussehen zurück"""
        self.locked_fields.clear()
        for key, widget in self.fields.items():
            # Style zurücksetzen (auf den Standard aus __init__)
            if isinstance(widget, QLineEdit):
                widget.setStyleSheet("""
                    background: #2d2d30; 
                    border: 1px solid #555; 
                    border-radius: 3px;
                    color: #fff; 
                    font-size: 14px; 
                    font-family: Consolas, monospace; 
                    font-weight: bold;
                    padding: 4px; 
                    selection-background-color: #0078d4;
                """)
                
class ToolOptionsPopup(QFrame):
    """Schwebende Optionen-Palette für Tools (wie Fusion360)"""
    option_selected = Signal(str, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            ToolOptionsPopup {
                background: rgba(45, 45, 48, 240);
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QPushButton {
                background: #3c3c3c;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 6px 4px;
                min-width: 60px;
                min-height: 45px;
                color: #ccc;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #4a4a4a;
                border-color: #0078d4;
            }
            QPushButton:checked {
                background: #0078d4;
                border-color: #0af;
                color: white;
            }
            QLabel {
                color: #888;
                font-size: 11px;
                padding: 2px;
                background: transparent;
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 8, 10, 8)
        self.layout.setSpacing(6)
        
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: #0af; font-weight: bold; font-size: 12px;")
        self.layout.addWidget(self.title_label)
        
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(8)
        self.layout.addLayout(self.button_layout)
        
        self.buttons = []
        self.current_option = None
        self.option_name = None
        self.hide()
    
    def show_options(self, title, option_name, options, current_value=0):
        """
        Zeigt Optionen an.
        options: Liste von (icon_text, label) Tupeln
        """
        self.title_label.setText(title)
        self.option_name = option_name
        
        while self.button_layout.count():
            item = self.button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.clear()
        
        for i, (icon, label) in enumerate(options):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setCheckable(True)
            btn.setChecked(i == current_value)
            btn.setMinimumWidth(55)
            btn.setMaximumWidth(70)
            btn.clicked.connect(lambda checked, idx=i: self._on_option_clicked(idx))
            self.button_layout.addWidget(btn)
            self.buttons.append(btn)
        
        self.button_layout.update()
        self.adjustSize()
        self.updateGeometry()
        self.show()
    
    def _on_option_clicked(self, index):
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)
        self.option_selected.emit(self.option_name, index)
    
    def position_near(self, widget, offset_x=10, offset_y=10):
        self.move(offset_x, offset_y)
        self.raise_()
