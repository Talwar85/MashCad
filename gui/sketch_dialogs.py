"""
MashCad - Sketch Dialogs
DimensionInput and ToolOptionsPopup for the 2D sketch editor
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QGraphicsDropShadowEffect, QWidget
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPalette, QBrush


class DimensionInput(QFrame):
    """Fusion360-style Eingabefeld mit Lock-Funktionalität und Options-Support"""
    value_changed = Signal(str, float)
    choice_changed = Signal(str, str) # Neu: Signal für Text-Auswahl
    confirmed = Signal()
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Modernes Styling: Dunkel, abgerundet, schwebend
        self.setAttribute(Qt.WA_ShowWithoutActivating) # Fokus nicht stehlen, wenn nicht nötig
        
        # Schatten für Tiefenwirkung
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self.setStyleSheet("""
            QFrame { 
                background-color: rgba(35, 35, 35, 245); 
                border: 1px solid rgba(80, 80, 80, 150); 
                border-radius: 8px; 
            }
            QLineEdit { 
                background: rgba(20, 20, 20, 100); 
                border: 1px solid #444; 
                border-radius: 4px;
                color: #fff; 
                font-size: 13px; 
                font-family: 'Segoe UI', sans-serif; 
                font-weight: 600;
                padding: 4px 6px; 
                selection-background-color: #0078d4;
            }
            QLineEdit:focus { 
                border: 1px solid #0078d4; 
                background: rgba(0, 0, 0, 80); 
            }
            QComboBox {
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                color: white;
                padding: 3px;
            }
            QLabel { 
                color: #ccc; 
                font-size: 12px; 
                font-weight: normal;
                background: transparent;
                border: none;
            }
            /* Label für den Feldnamen (L, R, Angle) */
            QLabel#NameLabel {
                color: #0078d4;
                font-weight: bold;
            }
            /* Label für die Einheit */
            QLabel#UnitLabel {
                color: #777;
                font-size: 11px;
            }
        """)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 8, 10, 8)
        self.layout.setSpacing(12)
        
        self.fields = {}
        self.field_order = []
        self.field_types = {} 
        self.active_field = 0
        self.locked_fields = set()
        
        self.hide()
    
    def setup(self, fields):
        """
        Erstellt die Eingabefelder dynamisch.
        fields: Liste von Tupeln (Label, Key, DefaultValue, Suffix/Options)
        """
        # Layout bereinigen
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            elif child.layout(): 
                # Rekursives Löschen für verschachtelte Layouts
                while child.layout().count():
                    sub = child.layout().takeAt(0)
                    if sub.widget(): sub.widget().deleteLater()
                child.layout().deleteLater()

        self.fields.clear()
        self.field_order.clear()
        self.field_types.clear()
        self.locked_fields.clear()
        
        for item in fields:
            label_text, key = item[0], item[1]
            val = item[2]
            
            # Container für ein Feld-Paar (Label + Input + Einheit)
            field_container = QVBoxLayout()
            field_container.setSpacing(2)
            field_container.setContentsMargins(0, 0, 0, 0)
            
            # Zeile für Input + Einheit
            input_row = QHBoxLayout()
            input_row.setSpacing(4)
            
            # Name Label (klein über dem Feld oder links davor - hier links davor für Kompaktheit)
            lbl = QLabel(label_text)
            lbl.setObjectName("NameLabel")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setFixedWidth(15) # Feste Breite für Ausrichtung
            
            widget = None
            is_combo = isinstance(item[3], list)
            
            if is_combo:
                self.field_types[key] = 'choice'
                options = item[3]
                widget = QComboBox()
                widget.addItems(options)
                if isinstance(val, int) and 0 <= val < len(options):
                    widget.setCurrentIndex(val)
                elif isinstance(val, str) and val in options:
                    widget.setCurrentText(val)
                
                widget.setMinimumWidth(90)
                widget.currentTextChanged.connect(lambda t, k=key: self.choice_changed.emit(k, t))
                # Combo Styling
                widget.setStyleSheet("QComboBox { min-height: 22px; }")
                
                input_row.addWidget(lbl)
                input_row.addWidget(widget)
                
            else: # Float Input
                self.field_types[key] = 'float'
                suffix = item[3]
                
                widget = QLineEdit()
                widget.setMinimumWidth(60)
                widget.setMaximumWidth(80)
                widget.setText(f"{val:.2f}")
                
                # Events verbinden
                widget.returnPressed.connect(self._on_confirm)
                widget.textEdited.connect(lambda t, k=key: self._on_user_edit(k, t))
                widget.textChanged.connect(lambda t, k=key: self._on_text_changed(k, t))
                
                unit_lbl = QLabel(suffix)
                unit_lbl.setObjectName("UnitLabel")
                
                input_row.addWidget(lbl)
                input_row.addWidget(widget)
                input_row.addWidget(unit_lbl)

            # Das Input-Widget speichern
            self.fields[key] = widget
            self.field_order.append(key)
            
            # Zum Hauptlayout hinzufügen
            self.layout.addLayout(input_row)
            
            # Kleiner vertikaler Separator wenn nicht das letzte Element
            if item != fields[-1]:
                line = QFrame()
                line.setFrameShape(QFrame.VLine)
                line.setFrameShadow(QFrame.Sunken)
                line.setStyleSheet("background: rgba(255,255,255,0.1); border: none; max-height: 20px;")
                self.layout.addWidget(line)
            
        self.active_field = 0
        self.adjustSize()
    
    def _on_user_edit(self, key, text):
        """Markiert ein Feld als vom User 'gelockt' (manuell überschrieben)"""
        self.locked_fields.add(key)
        if key in self.fields:
            # Visuelles Feedback für Locked State (Fusion Style: dunkleres Feld, goldener/weißer Text)
            self.fields[key].setStyleSheet("""
                QLineEdit {
                    background: rgba(0, 0, 0, 150);
                    border: 1px solid #dba600;
                    color: #fff;
                    font-weight: bold;
                }
            """)

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
        
        # Schatten hinzufügen
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        self.setStyleSheet("""
            ToolOptionsPopup {
                background: rgba(40, 40, 45, 240);
                border: 1px solid rgba(80, 80, 80, 180);
                border-radius: 6px;
            }
            QPushButton {
                background: transparent;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 40px;
                min-height: 40px;
                color: #ddd;
                font-size: 11px;
                text-align: center;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255,255,255,0.3);
            }
            QPushButton:checked {
                background: rgba(0, 120, 212, 0.3); /* Accent Color Background */
                border: 1px solid #0078d4;
                color: #fff;
            }
            QLabel {
                color: #aaa;
                font-size: 11px;
                font-weight: bold;
                padding-bottom: 4px;
                background: transparent;
                border: none;
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(4)
        
        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title_label)
        
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(6)
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
