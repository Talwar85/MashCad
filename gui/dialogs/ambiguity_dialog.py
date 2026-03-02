"""
TNP v5.0 - Ambiguity Resolution Dialog

Dialog for resolving ambiguous shape selections.
Presents candidates to the user for disambiguation.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QGroupBox,
    QTextEdit, QFrame, QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor
from loguru import logger
from typing import List, Optional

from gui.design_tokens import DesignTokens
from i18n import tr
from modeling.tnp_v5.ambiguity import AmbiguityReport, AmbiguityType


class AmbiguityDialog(QDialog):
    """
    Dialog for resolving ambiguous shape selections.

    Features:
    - Candidate list with descriptions
    - Preview button (signals viewport to highlight shape)
    - Select button to confirm choice
    - Cancel button to abort operation
    - selection_made signal for parent handling

    Signals:
        selection_made(str): Emitted when user selects a candidate
        preview_requested(str): Emitted when user wants to preview a candidate
    """

    selection_made = Signal(str)
    preview_requested = Signal(str)

    def __init__(self, report: AmbiguityReport, parent=None):
        """
        Initialize the ambiguity dialog.

        Args:
            report: AmbiguityReport with candidates and question
            parent: Parent widget
        """
        super().__init__(parent)
        self._report = report
        self._selected_candidate: Optional[str] = None

        self.setWindowTitle(tr("Resolve Ambiguity"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        self._setup_ui()
        self._populate_candidates()

    def _setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)

        # Header with question
        self._create_header(layout)

        # Candidate list
        self._create_candidate_list(layout)

        # Description area
        self._create_description_area(layout)

        # Buttons
        self._create_buttons(layout)

        # Dark theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _create_header(self, layout: QVBoxLayout):
        """Create the header with question."""
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: #2a2a2a;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)

        # Icon and title
        title_layout = QHBoxLayout()

        icon_label = QLabel("⚠")
        icon_label.setStyleSheet("font-size: 24px; color: #f0a500;")
        title_layout.addWidget(icon_label)

        title = QLabel(tr("Ambiguous Selection"))
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        title_layout.addWidget(title)
        title_layout.addStretch()

        header_layout.addLayout(title_layout)

        # Question text
        question_label = QLabel(self._report.question)
        question_label.setWordWrap(True)
        question_label.setStyleSheet("color: #ccc; padding: 8px 0;")
        header_layout.addWidget(question_label)

        layout.addWidget(header_frame)

    def _create_candidate_list(self, layout: QVBoxLayout):
        """Create the candidate list widget."""
        group = QGroupBox(tr("Candidates"))
        group.setStyleSheet("""
            QGroupBox {
                color: #aaa;
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)

        group_layout = QVBoxLayout()

        self._candidate_list = QListWidget()
        self._candidate_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._candidate_list.setIconSize(QSize(16, 16))
        self._candidate_list.itemSelectionChanged.connect(self._on_selection_changed)
        self._candidate_list.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Style the list
        self._candidate_list.setStyleSheet("""
            QListWidget {
                background: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                color: #ddd;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background: #0078d4;
                color: #fff;
            }
            QListWidget::item:hover {
                background: #2a2a2a;
            }
        """)

        group_layout.addWidget(self._candidate_list)
        group.setLayout(group_layout)
        layout.addWidget(group)

    def _create_description_area(self, layout: QVBoxLayout):
        """Create area for showing candidate details."""
        group = QGroupBox(tr("Details"))
        group.setStyleSheet("""
            QGroupBox {
                color: #aaa;
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)

        group_layout = QVBoxLayout()

        self._description_text = QTextEdit()
        self._description_text.setReadOnly(True)
        self._description_text.setMaximumHeight(100)
        self._description_text.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                color: #ccc;
                padding: 8px;
            }
        """)
        self._description_text.setText(tr("Select a candidate to see details."))

        group_layout.addWidget(self._description_text)
        group.setLayout(group_layout)
        layout.addWidget(group)

    def _create_buttons(self, layout: QVBoxLayout):
        """Create the button row."""
        button_layout = QHBoxLayout()

        # Preview button
        self._preview_btn = QPushButton(tr("Preview"))
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self._on_preview)
        self._preview_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #555;
            }
            QPushButton:disabled {
                background: #333;
                color: #666;
            }
        """)
        button_layout.addWidget(self._preview_btn)

        button_layout.addStretch()

        # Cancel button
        self._cancel_btn = QPushButton(tr("Cancel"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background: #444;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: #555;
            }
        """)
        button_layout.addWidget(self._cancel_btn)

        # Select button
        self._select_btn = QPushButton(tr("Select"))
        self._select_btn.setEnabled(False)
        self._select_btn.setDefault(True)
        self._select_btn.clicked.connect(self._on_select)
        self._select_btn.setObjectName("primary")
        self._select_btn.setStyleSheet("""
            QPushButton#primary {
                background: #0078d4;
                color: #fff;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
            }
            QPushButton#primary:hover {
                background: #1084d8;
            }
            QPushButton#primary:disabled {
                background: #333;
                color: #666;
            }
        """)
        button_layout.addWidget(self._select_btn)

        layout.addSpacing(16)
        layout.addLayout(button_layout)

    def _populate_candidates(self):
        """Populate the candidate list with items."""
        self._candidate_list.clear()

        for i, (shape_id, description) in enumerate(zip(
            self._report.candidates,
            self._report.candidate_descriptions
        )):
            item = QListWidgetItem()
            item.setText(f"{i + 1}. {description}")
            item.setData(Qt.UserRole, shape_id)

            # Add icon based on ambiguity type
            if self._report.ambiguity_type == AmbiguityType.SYMMETRIC:
                item.setText(f"↔ {item.text()}")
            elif self._report.ambiguity_type == AmbiguityType.PROXIMATE:
                item.setText(f"≈ {item.text()}")

            self._candidate_list.addItem(item)

        # Set icons for visual distinction
        self._update_list_icons()

    def _update_list_icons(self):
        """Update list item icons based on context."""
        for i in range(self._candidate_list.count()):
            item = self._candidate_list.item(i)
            # Could add shape-type specific icons here
            pass

    def _on_selection_changed(self):
        """Handle selection change in candidate list."""
        selected_items = self._candidate_list.selectedItems()

        if selected_items:
            item = selected_items[0]
            shape_id = item.data(Qt.UserRole)
            self._selected_candidate = shape_id

            # Update description
            idx = self._candidate_list.row(item)
            if idx < len(self._report.candidate_descriptions):
                desc = self._report.candidate_descriptions[idx]
                details = self._format_candidate_details(shape_id, desc)
                self._description_text.setText(details)

            # Enable buttons
            self._select_btn.setEnabled(True)
            self._preview_btn.setEnabled(True)
        else:
            self._selected_candidate = None
            self._description_text.setText(tr("Select a candidate to see details."))
            self._select_btn.setEnabled(False)
            self._preview_btn.setEnabled(False)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on item (select and close)."""
        self._selected_candidate = item.data(Qt.UserRole)
        self.accept()

    def _on_preview(self):
        """Handle preview button click."""
        if self._selected_candidate:
            self.preview_requested.emit(self._selected_candidate)

    def _on_select(self):
        """Handle select button click."""
        if self._selected_candidate:
            self.selection_made.emit(self._selected_candidate)
            self.accept()

    def _on_cancel(self):
        """Handle cancel button click."""
        self._selected_candidate = None
        self.reject()

    def _format_candidate_details(self, shape_id: str, description: str) -> str:
        """Format detailed information about a candidate."""
        lines = [
            f"<b>{tr('Shape ID')}:</b> {shape_id}",
            f"<b>{tr('Description')}:</b> {description}",
        ]

        # Add ambiguity-specific info
        if self._report.ambiguity_type == AmbiguityType.SYMMETRIC:
            lines.append(f"<br><i>{tr('This candidate is in a symmetric position.')}</i>")
        elif self._report.ambiguity_type == AmbiguityType.PROXIMATE:
            lines.append(f"<br><i>{tr('This candidate is very close to other candidates.')}</i>")
        elif self._report.ambiguity_type == AmbiguityType.MULTIPLE_FEATURES:
            lines.append(f"<br><i>{tr('This candidate belongs to a different feature.')}</i>")

        # Add metadata if available
        if self._report.metadata:
            lines.append(f"<br><b>{tr('Additional Info')}:</b>")
            for key, value in self._report.metadata.items():
                if key not in ('symmetric', 'proximity_threshold', 'features'):
                    lines.append(f"  {key}: {value}")

        return "<br>".join(lines)

    def get_selected_candidate(self) -> Optional[str]:
        """
        Get the selected candidate shape ID.

        Returns:
            Selected shape ID or None if cancelled
        """
        return self._selected_candidate


class AmbiguousSelectionDialog(AmbiguityDialog):
    """
    Simplified dialog for quick ambiguity resolution.

    Smaller footprint, optimized for rapid selection.
    """

    def __init__(self, report: AmbiguityReport, parent=None):
        """Initialize with smaller default size."""
        super().__init__(report, parent)
        self.setWindowTitle(tr("Select Shape"))
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)


def resolve_ambiguity_dialog(
    report: AmbiguityReport,
    parent=None,
    compact: bool = False
) -> Optional[str]:
    """
    Convenience function to show ambiguity dialog and get selection.

    Args:
        report: AmbiguityReport with candidates
        parent: Parent widget
        compact: Use compact dialog variant

    Returns:
        Selected shape ID or None if cancelled
    """
    dialog_class = AmbiguousSelectionDialog if compact else AmbiguityDialog
    dialog = dialog_class(report, parent)

    result = dialog.exec()

    if result == QDialog.Accepted:
        return dialog.get_selected_candidate()

    return None
