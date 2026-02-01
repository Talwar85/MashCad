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

try:
    from gui.design_tokens import DesignTokens
except ImportError:
    from design_tokens import DesignTokens

# Parameter-System für Variablen in Dimensionen
try:
    from core.parameters import get_parameters
    HAS_PARAMETERS = True
except ImportError:
    HAS_PARAMETERS = False
    def get_parameters():
        return None

class DimensionInput(QFrame):
    """
    Fusion360-style Floating Input.
    Dunkel, Semi-Transparent, mit Schatten und direktem Feedback.

    Phase 8 Features:
    - Per-field enter: Commit single field, move to next
    - Validation with visual error feedback
    - Double-click to reset field to auto
    """
    value_changed = Signal(str, float)
    choice_changed = Signal(str, str)
    confirmed = Signal()
    cancelled = Signal()
    # Phase 8: New signals
    field_committed = Signal(str, float)  # Emitted when single field is committed (key, value)
    field_reset = Signal(str)             # Emitted when field is reset to auto (key)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Wichtig: Frameless und Tool-Flag, damit es über dem Canvas schwebt
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Schatten für Tiefenwirkung (Pop-out Effekt)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100)) # Weicherer Schatten
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 4)
        self.layout.setSpacing(8)

        self.fields = {}
        self.field_order = []
        self.field_types = {}
        self.active_field = 0
        self.locked_fields = set()
        # Phase 8: Error tracking and per-field enter mode
        self.error_fields = set()
        self.committed_values = {}  # Tracks which fields have been committed
        self.per_field_enter = False  # Set by feature flag
        self._last_validation_error = None  # Last validation error message
        self._current_tool = "UNKNOWN"  # For logging

        self.hide()

    def paintEvent(self, event):
        """Custom Paint für abgerundeten, dunklen Hintergrund mit Tokens"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Hintergrund aus DesignTokens mit leichter Transparenz
        bg_color = QColor(DesignTokens.COLOR_BG_PANEL)
        bg_color.setAlpha(245) # Fast undurchsichtig
        
        border_color = QColor(DesignTokens.COLOR_GRID_MAJOR)
        
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
            
            # Label
            lbl = QLabel(label_text)
            # Token: TEXT_MUTED
            lbl.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; font-weight: bold; margin-left: 2px;")
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
                
                # Styling für ComboBox mit Tokens
                widget.setStyleSheet(f"""
                    QComboBox {{
                        background: {DesignTokens.COLOR_BG_INPUT.name()}; 
                        border: 1px solid {DesignTokens.COLOR_GRID_MAJOR.name()}; 
                        border-radius: 3px;
                        color: {DesignTokens.COLOR_TEXT_PRIMARY.name()}; 
                        padding: 2px 4px; min-width: 70px;
                    }}
                    QComboBox::drop-down {{ border: none; }}
                """)
                widget.currentTextChanged.connect(lambda t, k=key: self.choice_changed.emit(k, t))
                
            else: # Float/Text Input
                self.field_types[key] = 'float'
                widget = QLineEdit()
                widget.setText(f"{val:.2f}")
                widget.setFixedWidth(70)

                # Styling für LineEdit mit Tokens
                # Standard-State (unlocked)
                widget.setStyleSheet(self._get_lineedit_style(locked=False))

                # Phase 8: Per-field enter - connect to field-specific handler
                widget.returnPressed.connect(lambda k=key: self._on_field_enter(k))
                widget.textEdited.connect(lambda t, k=key: self._on_user_edit(k, t))
                widget.textChanged.connect(lambda t, k=key: self._on_text_changed(k, t))

                # Phase 8: Double-click to reset field to auto
                widget.mouseDoubleClickEvent = lambda event, k=key: self._on_field_double_click(k, event)
            
            vbox.addWidget(widget)
            self.layout.addLayout(vbox)
            
            self.fields[key] = widget
            self.field_order.append(key)
            
            # Separator (außer beim letzten)
            if i < len(fields) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.VLine)
                line.setStyleSheet(f"color: {DesignTokens.COLOR_GRID_MAJOR.name()};")
                self.layout.addWidget(line)

        # FIX: Force proper size calculation
        self.layout.activate()  # Force layout to calculate
        self.updateGeometry()   # Update geometry hints

        # Calculate minimum size based on fields
        min_width = max(120, len(fields) * 85)  # At least 85px per field
        min_height = 45  # Label + Input + padding
        self.setMinimumSize(min_width, min_height)

        self.adjustSize()

    def _get_lineedit_style(self, locked=False, error=False):
        """
        Helper für konsistentes Styling.

        Args:
            locked: Field is locked by user input (green border)
            error: Field has validation error (red border)
        """
        # Phase 8: Error state takes precedence
        if error:
            bg = DesignTokens.COLOR_BG_INPUT.name()
            border = "#FF4444"  # Red for error
            text = "#FF4444"
        elif locked:
            # Locked state (Benutzer hat editiert)
            bg = DesignTokens.COLOR_BG_INPUT.name()
            border = DesignTokens.COLOR_CONSTRAINT.name()  # Mint/Grün für "Locked"
            text = DesignTokens.COLOR_CONSTRAINT.name()
        else:
            # Default state (Live preview)
            bg = DesignTokens.COLOR_BG_INPUT.name()
            border = DesignTokens.COLOR_GRID_MAJOR.name()
            text = DesignTokens.COLOR_DIMENSION.name()  # Gelb für Dimensionen

        return f"""
            QLineEdit {{
                background: {bg};
                border: 2px solid {border};
                border-radius: 3px;
                color: {text};
                font-family: Consolas, monospace;
                font-weight: bold;
                padding: 3px;
                selection-background-color: {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QLineEdit:focus {{
                border: 2px solid {DesignTokens.COLOR_PRIMARY.name() if not error else border};
                background: {DesignTokens.COLOR_BG_TOOLTIP.name()};
            }}
        """

    def _on_user_edit(self, key, text):
        self.locked_fields.add(key)
        # Visuelles Feedback: Locked Style anwenden, validate first
        if key in self.fields:
            is_valid = self._validate_field(key, text)
            self.fields[key].setStyleSheet(
                self._get_lineedit_style(locked=True, error=not is_valid)
            )

    def _on_text_changed(self, key, text):
        val = self._evaluate_expression(text)
        if val is not None:
            self.value_changed.emit(key, val)
            # Clear error if value is now valid
            if key in self.error_fields:
                if self._validate_field(key, text):
                    self.error_fields.discard(key)
                    locked = key in self.locked_fields
                    self.fields[key].setStyleSheet(self._get_lineedit_style(locked=locked))

    def _validate_field(self, key: str, text: str) -> bool:
        """
        Validates a field value and shows visual feedback.

        Phase 8: Validation with error styling.

        Args:
            key: Field key (length, width, radius, etc.)
            text: Raw text value

        Returns:
            True if valid, False otherwise
        """
        value = self._evaluate_expression(text)

        # Basic validation: Must evaluate to a number
        if value is None:
            self._set_field_error(key, "Ungültiger Ausdruck")
            return False

        # Field-specific validation rules
        validations = {
            "radius": lambda v: v > 0,
            "diameter": lambda v: v > 0,
            "length": lambda v: v > 0,
            "width": lambda v: v > 0,
            "height": lambda v: v != 0,  # Can be negative for direction
            "angle": lambda v: True,     # All angles allowed
            "sides": lambda v: v >= 3,   # Polygon min 3 sides
            "count": lambda v: v >= 1,   # Pattern min 1
            "factor": lambda v: v > 0,   # Scale > 0
            "distance": lambda v: True,  # Offset can be negative
            "spacing": lambda v: v > 0,  # Pattern spacing > 0
        }

        validator = validations.get(key, lambda v: True)
        if not validator(value):
            error_msgs = {
                "radius": "Radius muss > 0 sein",
                "diameter": "Durchmesser muss > 0 sein",
                "length": "Länge muss > 0 sein",
                "width": "Breite muss > 0 sein",
                "height": "Höhe darf nicht 0 sein",
                "sides": "Mindestens 3 Seiten",
                "count": "Mindestens 1",
                "factor": "Faktor muss > 0 sein",
                "spacing": "Abstand muss > 0 sein",
            }
            self._set_field_error(key, error_msgs.get(key, "Ungültiger Wert"))
            return False

        self._clear_field_error(key)
        return True

    def _set_field_error(self, key: str, message: str):
        """Shows error styling for a field."""
        self.error_fields.add(key)
        self._last_validation_error = message
        if key in self.fields:
            self.fields[key].setToolTip(message)
            self.fields[key].setStyleSheet(self._get_lineedit_style(error=True))

    def _clear_field_error(self, key: str):
        """Removes error styling from a field."""
        self.error_fields.discard(key)
        self._last_validation_error = None
        if key in self.fields:
            self.fields[key].setToolTip("")
            locked = key in self.locked_fields
            self.fields[key].setStyleSheet(self._get_lineedit_style(locked=locked))

    def _evaluate_expression(self, text: str):
        """
        Evaluiert einen Ausdruck: Zahl, Parameter-Name oder Formel.

        Beispiele:
            "100" -> 100.0
            "width" -> Wert von Parameter 'width'
            "width * 2" -> Berechneter Wert
        """
        if not text:
            return None

        text = text.strip().replace(',', '.')

        # Versuch 1: Direkte Zahl
        try:
            return float(text)
        except ValueError:
            pass

        # Versuch 2: Parameter-System nutzen
        if HAS_PARAMETERS:
            params = get_parameters()
            if params:
                # Ist es ein Parameter-Name?
                param_names = [p[0] for p in params.list_all()]
                if text in param_names:
                    return params.get(text)

                # Versuche als Formel zu evaluieren
                try:
                    # Temporär evaluieren
                    temp_name = "__dim_eval__"
                    params.set(temp_name, text)
                    result = params.get(temp_name)
                    params.delete(temp_name)
                    return result
                except:
                    pass

        return None

    def _on_confirm(self):
        self.confirmed.emit()

    def _on_field_enter(self, key: str):
        """
        Called when Enter is pressed in a field.

        Phase 8: Per-field enter mode - commits single field and moves to next.
        Classic mode - confirms all fields.

        Args:
            key: The field key where Enter was pressed
        """
        if self.per_field_enter:
            # Validate before committing
            text = self.fields[key].text() if key in self.fields else ""
            if not self._validate_field(key, text):
                return  # Don't commit invalid values

            # Commit this field only
            value = self._evaluate_expression(text)
            if value is not None:
                self.committed_values[key] = value
                self.field_committed.emit(key, value)

            # Move to next unlocked field
            self._move_to_next_uncommitted()
        else:
            # Classic behavior: Confirm all
            self._on_confirm()

    def _move_to_next_uncommitted(self):
        """Moves focus to the next uncommitted field, or confirms if all done."""
        start_idx = self.active_field
        for i in range(len(self.field_order)):
            next_idx = (start_idx + 1 + i) % len(self.field_order)
            next_key = self.field_order[next_idx]

            # Skip already committed and choice fields
            if next_key in self.committed_values:
                continue
            if self.field_types.get(next_key) != 'float':
                continue

            # Found next field
            self.focus_field(next_idx)
            return

        # All fields committed - confirm
        self._on_confirm()

    def _on_field_double_click(self, key: str, event):
        """
        Called on double-click in a field.

        Phase 8: Reset field to auto (mouse-based) value.

        Args:
            key: The field key that was double-clicked
            event: The mouse event
        """
        # Reset the field
        self.locked_fields.discard(key)
        self.error_fields.discard(key)
        self.committed_values.pop(key, None)

        if key in self.fields:
            self.fields[key].setStyleSheet(self._get_lineedit_style(locked=False))
            self.fields[key].setToolTip("")
            self.fields[key].selectAll()

        # Emit signal for sketch editor to update with live value
        self.field_reset.emit(key)

    def set_per_field_enter(self, enabled: bool):
        """
        Enables/disables per-field enter mode.

        Args:
            enabled: True for per-field enter, False for classic behavior
        """
        self.per_field_enter = enabled

    def set_current_tool(self, tool_name: str):
        """Sets the current tool name for logging purposes."""
        self._current_tool = tool_name

    def has_errors(self) -> bool:
        """Returns True if any field has validation errors."""
        return len(self.error_fields) > 0

    def get_values(self):
        result = {}
        for key, widget in self.fields.items():
            if self.field_types[key] == 'float':
                text = widget.text()
                val = self._evaluate_expression(text)
                result[key] = val if val is not None else 0.0
            elif self.field_types[key] == 'choice':
                result[key] = widget.currentText()
        return result

    def get_raw_texts(self) -> dict:
        """Gibt den Rohtext aller Float-Felder zurück (für Parameter-Formeln)."""
        result = {}
        for key, widget in self.fields.items():
            if self.field_types[key] == 'float':
                result[key] = widget.text().strip()
        return result

    def set_value(self, key, value):
        if key in self.fields and key not in self.locked_fields:
            if self.field_types[key] == 'float':
                widget = self.fields[key]
                # Phase 8: Preserve selection when updating live value
                # This allows typing to replace the value
                had_selection = widget.hasSelectedText()
                widget.setText(f"{value:.2f}")
                if had_selection or widget.hasFocus():
                    widget.selectAll()  # Re-select so typing replaces

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
        # Reset Styles to default
        for key, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.setStyleSheet(self._get_lineedit_style(locked=False))

    def forward_key(self, char: str, replace: bool = True) -> bool:
        """
        Phase 8: Forwards a character to the first unlocked field.

        Used for direct number input - when user types numbers while drawing,
        they get forwarded to the dimension input field.

        Args:
            char: Single character to forward (digit, minus, decimal point)
            replace: If True, replace existing text. If False, append.

        Returns:
            True if character was forwarded successfully, False otherwise
        """
        if not self.field_order:
            return False

        # Find first unlocked float field
        for key in self.field_order:
            if key not in self.locked_fields and self.field_types.get(key) == 'float':
                widget = self.fields[key]
                if isinstance(widget, QLineEdit):
                    widget.setFocus()
                    if replace:
                        # Clear and set new character (for first input)
                        widget.setText(char)
                        widget.setCursorPosition(len(char))
                    else:
                        # Append character (for subsequent input)
                        widget.insert(char)
                    # Trigger user edit (locks the field)
                    self._on_user_edit(key, widget.text())
                    return True

        return False

    def select_active_field(self):
        """
        Selects all text in the currently active field.
        Used to prepare for replacing text on first keypress.
        """
        if 0 <= self.active_field < len(self.field_order):
            key = self.field_order[self.active_field]
            if key in self.fields:
                widget = self.fields[key]
                if isinstance(widget, QLineEdit):
                    widget.selectAll()

    def get_active_field_key(self) -> str:
        """Returns the key of the currently active/focused field."""
        if 0 <= self.active_field < len(self.field_order):
            return self.field_order[self.active_field]
        return None


class ToolOptionsPopup(QFrame):
    """
    Kleine Kontext-Palette neben dem Mauszeiger (z.B. für Polygon-Seiten, Kreis-Typ).
    """
    option_selected = Signal(str, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setMinimumWidth(140) 
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        
        self.title_label = QLabel("")
        self.title_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; font-weight: bold; text-transform: uppercase; margin-bottom: 2px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.title_label)
        
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
        
        # Hintergrund aus DesignTokens
        bg = QColor(DesignTokens.COLOR_BG_PANEL)
        bg.setAlpha(250)
        
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(QColor(DesignTokens.COLOR_GRID_MAJOR), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

    def show_options(self, title, option_name, options, current_value=0):
        self.title_label.setText(title)
        self.option_name = option_name
        
        while self.button_layout.count():
            item = self.button_layout.takeAt(0)
            if item.widget(): 
                item.widget().deleteLater()
        self.buttons.clear()
        
        MAX_COLUMNS = 2 
        
        for i, (icon, label) in enumerate(options):
            btn = QPushButton(f" {icon}  {label} ")
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            is_active = False
            if isinstance(current_value, int) and i == current_value: is_active = True
            
            btn.setChecked(is_active)
            btn.setFixedHeight(32)
            
            # Button Style mit Design Tokens
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {DesignTokens.COLOR_BG_INPUT.name()}; 
                    border: 1px solid {DesignTokens.COLOR_GRID_MAJOR.name()}; 
                    border-radius: 4px;
                    color: {DesignTokens.COLOR_TEXT_PRIMARY.name()}; 
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0 10px;
                    text-align: left;
                }}
                QPushButton:hover {{ 
                    background: {DesignTokens.COLOR_BG_TOOLTIP.name()}; 
                    border-color: {DesignTokens.COLOR_TEXT_MUTED.name()}; 
                }}
                QPushButton:checked {{ 
                    background: {DesignTokens.COLOR_PRIMARY.name()}; 
                    border: 1px solid {DesignTokens.COLOR_PRIMARY.name()}; 
                    color: white; 
                }}
            """)
            
            btn.clicked.connect(lambda checked, idx=i: self._on_option_clicked(idx))
            
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