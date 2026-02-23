"""
CadQuery Script Editor Dialog

Phase 2: In-App Script Editor with syntax highlighting and live execution.

Features:
- Syntax highlighting for Build123d/CadQuery API
- Execute button with error display
- Parameter panel (Phase 3)
- Load/Save scripts
- Styled with DesignTokens for consistency
"""

import re
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QSplitter, QFileDialog,
    QScrollArea, QWidget, QDoubleSpinBox, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from loguru import logger

try:
    from gui.design_tokens import DesignTokens
    HAS_DESIGN_TOKENS = True
except ImportError:
    HAS_DESIGN_TOKENS = False
    # Fallback colors
    class DesignTokens:
        COLOR_BG_PANEL = QColor("#262626")
        COLOR_BG_INPUT = QColor("#404040")
        COLOR_TEXT_PRIMARY = QColor("#fafafa")
        COLOR_TEXT_MUTED = QColor("#a3a3a3")
        COLOR_PRIMARY = QColor("#2563eb")
        COLOR_PRIMARY_HOVER = QColor("#3b82f6")
        COLOR_SUCCESS = QColor("#22c55e")
        COLOR_ERROR = QColor("#ef4444")
        COLOR_BORDER = QColor("#404040")


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for Python/Build123d code.

    Highlights:
    - Keywords (def, class, with, etc.)
    - Build123d API (Box, Cylinder, BuildPart, etc.)
    - Strings
    - Comments
    - Numbers
    """

    # Python keywords
    KEYWORDS = [
        'and', 'as', 'assert', 'break', 'class', 'continue', 'def',
        'del', 'elif', 'else', 'except', 'exec', 'finally', 'for',
        'from', 'global', 'if', 'import', 'in', 'is', 'lambda',
        'not', 'or', 'pass', 'print', 'raise', 'return', 'try',
        'while', 'with', 'yield', 'True', 'False', 'None'
    ]

    # Build123d API
    BUILD123D_API = [
        'Box', 'Cylinder', 'Sphere', 'Cone', 'Torus',
        'BuildPart', 'BuildSketch', 'BuildLine',
        'extrude', 'revolve', 'loft', 'sweep', 'fillet', 'chamfer',
        'Plane', 'Axis', 'Locations', 'Vector', 'Location',
        'Rectangle', 'Circle', 'Polygon', 'Polyline', 'Ellipse',
        'Mode', 'Align', 'Part', 'Sketch', 'Solid', 'Face', 'Edge',
        'cq', 'Workplane',  # CadQuery compatibility
    ]

    def __init__(self, document):
        super().__init__(document)

        # Keyword format (blue)
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#569CD6"))  # VS Code blue
        self.keyword_format.setFontWeight(QFont.Bold)

        # Build123d format (purple)
        self.api_format = QTextCharFormat()
        self.api_format.setForeground(QColor("#C586C0"))  # VS Code purple

        # String format (orange)
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#CE9178"))  # VS Code orange

        # Comment format (green)
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#6A9955"))  # VS Code green

        # Number format (light blue)
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#B5CEA8"))  # VS Code light blue

        # Compile regex patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for matching."""
        self.keyword_patterns = [
            re.compile(r'\b' + word + r'\b') for word in self.KEYWORDS
        ]
        self.api_patterns = [
            re.compile(r'\b' + word + r'\b') for word in self.BUILD123D_API
        ]
        self.string_pattern = re.compile(r'["\'].*?["\']')
        self.comment_pattern = re.compile(r'#.*$')
        self.number_pattern = re.compile(r'\b\d+\.?\d*\b')

    def highlightBlock(self, text: str):
        """Apply highlighting to a block of text."""
        # Save state
        self.setCurrentBlockState(0)

        # Comments (first priority)
        for match in self.comment_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)

        # Strings
        for match in self.string_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)

        # Keywords
        for pattern in self.keyword_patterns:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)

        # Build123d API
        for pattern in self.api_patterns:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), self.api_format)

        # Numbers
        for match in self.number_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)


class ParameterWidget(QDoubleSpinBox):
    """Widget for editing a numeric parameter."""

    def __init__(self, name: str, value: float, parent=None):
        super().__init__(parent)
        self.param_name = name
        self.setRange(-10000, 10000)
        self.setDecimals(2)
        self.setValue(value)
        self.setSingleStep(1.0)


class CadQueryEditorDialog(QDialog):
    """
    Dialog for editing and executing CadQuery/Build123d scripts.

    Features:
    - Code editor with syntax highlighting
    - Parameter panel (Phase 3)
    - Execute button with error display
    - Load/Save functionality
    - Styled with DesignTokens
    """

    script_executed = Signal(list, str)  # bodies, script_name

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.current_file = None
        self.parameters = []

        self._setup_ui()
        self._connect_signals()
        self._apply_styling()

        # Load default example
        self._load_example_script()

    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("CadQuery Script Editor")
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)

        # Main content (splitter)
        splitter = QSplitter(Qt.Horizontal)

        # Left: Code editor
        editor_widget = self._create_editor_widget()
        splitter.addWidget(editor_widget)

        # Right: Parameters
        params_widget = self._create_parameters_widget()
        splitter.addWidget(params_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        # Error display
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.error_label.setStyleSheet("padding: 12px; border-radius: 6px;")
        layout.addWidget(self.error_label)

    def _create_toolbar(self) -> QHBoxLayout:
        """Create toolbar with action buttons."""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Load button
        self.load_btn = QPushButton("Load")
        self.load_btn.setToolTip("Load script from file")
        toolbar.addWidget(self.load_btn)

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setToolTip("Save script to file")
        toolbar.addWidget(self.save_btn)

        toolbar.addStretch()

        # Execute button
        self.execute_btn = QPushButton("Execute")
        self.execute_btn.setToolTip("Execute script and create geometry")
        self.execute_btn.setProperty("primary", True)
        toolbar.addWidget(self.execute_btn)

        return toolbar

    def _create_editor_widget(self) -> QWidget:
        """Create code editor widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Label
        label = QLabel("Script (Build123d/CadQuery):")
        layout.addWidget(label)

        # Text editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 12px;
            }
            QTextEdit:focus {
                border: 1px solid #2563eb;
            }
        """)

        # Add syntax highlighter
        self.highlighter = PythonSyntaxHighlighter(self.editor.document())

        layout.addWidget(self.editor)

        return widget

    def _create_parameters_widget(self) -> QWidget:
        """Create parameters panel widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Label
        label = QLabel("Parameters:")
        layout.addWidget(label)

        # Scroll area for parameters
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        self.params_container = QWidget()
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setSpacing(8)
        self.params_layout.addStretch()

        scroll.setWidget(self.params_container)
        layout.addWidget(scroll)

        return widget

    def _connect_signals(self):
        """Connect widget signals."""
        self.load_btn.clicked.connect(self._load_script)
        self.save_btn.clicked.connect(self._save_script)
        self.execute_btn.clicked.connect(self._execute_script)
        self.editor.textChanged.connect(self._on_text_changed)

    def _apply_styling(self):
        """Apply DesignTokens styling."""
        if HAS_DESIGN_TOKENS:
            self.setStyleSheet(DesignTokens.stylesheet_dialog())
        else:
            # Fallback styling
            self.setStyleSheet(f"""
                QDialog {{
                    background: {DesignTokens.COLOR_BG_PANEL.name()};
                    color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
                }}
                QPushButton {{
                    background: {DesignTokens.COLOR_BG_INPUT.name()};
                    color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background: #525252;
                }}
                QPushButton[primary="true"] {{
                    background: {DesignTokens.COLOR_PRIMARY.name()};
                    color: white;
                    font-weight: bold;
                }}
                QPushButton[primary="true"]:hover {{
                    background: {DesignTokens.COLOR_PRIMARY_HOVER.name()};
                }}
                QLabel {{
                    color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
                    font-size: 13px;
                }}
            """)

    def _load_example_script(self):
        """Load a simple example script."""
        example = '''# CadQuery/Build123d Example
# Create a simple box with rounded edges

import build123d as b

with b.BuildPart() as part:
    b.Box(50, 30, 10)
    b.fillet(part.edges(), radius=2)
'''
        self.editor.setPlainText(example)

    def _load_script(self):
        """Load script from file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load CadQuery Script",
            "",
            "Python Files (*.py);;All Files (*)"
        )

        if path:
            try:
                self.current_file = Path(path)
                code = self.current_file.read_text(encoding='utf-8')
                self.editor.setPlainText(code)
                self._extract_parameters()
            except Exception as e:
                self._show_error(f"Failed to load file: {e}")

    def _save_script(self):
        """Save script to file."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CadQuery Script",
            self.current_file or "script.py",
            "Python Files (*.py);;All Files (*)"
        )

        if path:
            try:
                self.current_file = Path(path)
                self.current_file.write_text(self.editor.toPlainText(), encoding='utf-8')
            except Exception as e:
                self._show_error(f"Failed to save file: {e}")

    def _execute_script(self):
        """Execute the current script and create bodies with CadQueryFeature."""
        from modeling.cadquery_importer import CadQueryImporter

        code = self.editor.toPlainText()

        # Clear error display
        self.error_label.setVisible(False)
        self.error_label.setText("")
        self.error_label.setStyleSheet("")

        # Execute
        importer = CadQueryImporter(self.document)
        script_source = self.current_file.name if self.current_file else "editor.py"
        result = importer.execute_code(code, source=script_source)

        if result.success and result.solids:
            # Create bodies with CadQueryFeature (editable!)
            bodies = importer.create_bodies_from_solids(
                result.solids,
                name=result.name,
                script_source=script_source,
                script=code  # Store script for editing
            )

            # Add bodies to document
            for body in bodies:
                self.document.add_body(body)

            self.script_executed.emit(bodies, result.name)

            if result.status.value == 3:  # EMPTY
                self._show_warning("No solids were generated from the script")
            else:
                self._show_success(f"Generated {len(bodies)} body(s)")
        elif result.success:
            # Success but no solids
            self._show_warning("No solids were generated from the script")
        else:
            error_text = "\n".join(result.errors)
            self._show_error(f"Execution failed:\n{error_text}")

    def _extract_parameters(self):
        """Extract parameters from the script (Phase 3)."""
        from modeling.cadquery_importer import CadQueryImporter

        code = self.editor.toPlainText()
        importer = CadQueryImporter(self.document)
        self.parameters = importer.extract_parameters(code)

        # Clear existing parameter widgets
        for i in reversed(range(self.params_layout.count())):
            item = self.params_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()

        # Add parameter widgets
        for param in self.parameters:
            row = QHBoxLayout()
            row.setSpacing(8)

            label = QLabel(f"{param.name}:")
            label.setMinimumWidth(80)

            spinbox = ParameterWidget(param.name, param.value)
            spinbox.valueChanged.connect(self._on_parameter_changed)

            row.addWidget(label)
            row.addWidget(spinbox)

            self.params_layout.insertLayout(self.params_layout.count() - 1, row)

    def _on_text_changed(self):
        """Handle text changes in the editor."""
        # Debounce parameter extraction
        self._extract_parameters()

    def _on_parameter_changed(self, value: float):
        """Handle parameter value change."""
        sender = self.sender()
        if isinstance(sender, ParameterWidget):
            # Update script with new parameter value
            self._update_parameter_in_script(sender.param_name, value)

    def _update_parameter_in_script(self, name: str, value: float):
        """Update a parameter value in the script."""
        code = self.editor.toPlainText()

        # Pattern to match: name = value
        pattern = re.compile(rf'^{name}\s*=\s*[\d.]+', re.MULTILINE)

        # Replace with new value
        new_code = pattern.sub(f'{name} = {value}', code)

        if new_code != code:
            self.editor.setPlainText(new_code)

    def _show_success(self, message: str):
        """Show success message."""
        self.error_label.setVisible(True)
        self.error_label.setText(f"✓ {message}")

        if HAS_DESIGN_TOKENS:
            bg = DesignTokens.COLOR_SUCCESS.name()
        else:
            bg = "#22c55e"

        self.error_label.setStyleSheet(f"""
            color: white;
            background-color: {bg};
            padding: 12px;
            border-radius: 6px;
        """)

    def _show_warning(self, message: str):
        """Show warning message."""
        self.error_label.setVisible(True)
        self.error_label.setText(f"⚠ {message}")

        if HAS_DESIGN_TOKENS:
            bg = "#FF9800"
        else:
            bg = "#FF9800"

        self.error_label.setStyleSheet(f"""
            color: white;
            background-color: {bg};
            padding: 12px;
            border-radius: 6px;
        """)

    def _show_error(self, message: str):
        """Show error message."""
        self.error_label.setVisible(True)
        self.error_label.setText(f"✗ {message}")

        if HAS_DESIGN_TOKENS:
            bg = DesignTokens.COLOR_ERROR.name()
        else:
            bg = "#ef4444"

        self.error_label.setStyleSheet(f"""
            color: white;
            background-color: {bg};
            padding: 12px;
            border-radius: 6px;
        """)

    def set_script(self, code: str):
        """Set the script content."""
        self.editor.setPlainText(code)
        self._extract_parameters()

    def get_script(self) -> str:
        """Get the current script content."""
        return self.editor.toPlainText()
