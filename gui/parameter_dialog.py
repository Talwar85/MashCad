"""
MashCad - Parameter Dialog
CAD-Style Parameterverwaltung

Ermöglicht:
- Variablen definieren (width = 100)
- Formeln verwenden (height = width * 0.5)
- Parameter in Sketches nutzen
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QHeaderView, QMessageBox,
    QMenu, QAbstractItemView, QFrame, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont, QAction

from i18n import tr
from core.parameters import Parameters, get_parameters


class ParameterDialog(QDialog):
    """
    CAD-Style Parameter-Dialog.

    Zeigt alle Parameter in einer Tabelle:
    | Name | Wert | Formel | Einheit | Kommentar |
    """

    parameters_changed = Signal()  # Emittiert wenn Parameter geändert wurden

    def __init__(self, parameters: Parameters = None, parent=None):
        super().__init__(parent)
        self.parameters = parameters or get_parameters()
        self._setup_ui()
        self._load_parameters()

    def _setup_ui(self):
        self.setWindowTitle(tr("Parameters"))
        self.setMinimumSize(600, 400)
        self.setStyleSheet("""
            QDialog { background-color: #2d2d30; color: #e0e0e0; }
            QTableWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                gridline-color: #3e3e42;
                selection-background-color: #094771;
            }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section {
                background-color: #3e3e42;
                color: #e0e0e0;
                padding: 6px;
                border: none;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                padding: 6px 12px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #0d5289; }
            QPushButton#deleteBtn { background-color: #c42b1c; }
            QPushButton#deleteBtn:hover { background-color: #d83b2b; }
            QLineEdit {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Info-Text
        info_label = QLabel(tr("Define parameters to use in sketches. Use formulas like: height = width * 0.5"))
        info_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(info_label)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            tr("Name"), tr("Value"), tr("Formula"), tr("Unit"), tr("Comment")
        ])

        # Spaltenbreiten
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(3, 60)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        # Neue Parameter Eingabe
        new_row = QHBoxLayout()

        new_row.addWidget(QLabel(tr("New") + ":"))

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Name"))
        self.name_edit.setFixedWidth(120)
        new_row.addWidget(self.name_edit)

        new_row.addWidget(QLabel("="))

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText(tr("Value or Formula"))
        new_row.addWidget(self.value_edit)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["mm", "cm", "m", "in", "°", ""])
        self.unit_combo.setFixedWidth(60)
        new_row.addWidget(self.unit_combo)

        add_btn = QPushButton(tr("Add"))
        add_btn.clicked.connect(self._add_parameter)
        new_row.addWidget(add_btn)

        layout.addLayout(new_row)

        # Buttons
        btn_row = QHBoxLayout()

        delete_btn = QPushButton(tr("Delete Selected"))
        delete_btn.setObjectName("deleteBtn")
        delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(delete_btn)

        btn_row.addStretch()

        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        # Enter-Taste zum Hinzufügen
        self.name_edit.returnPressed.connect(lambda: self.value_edit.setFocus())
        self.value_edit.returnPressed.connect(self._add_parameter)

    def _load_parameters(self):
        """Lädt alle Parameter in die Tabelle."""
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        params = self.parameters.list_all()
        self.table.setRowCount(len(params))

        for row, (name, value, formula) in enumerate(params):
            # Name
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, name)  # Original-Name speichern
            self.table.setItem(row, 0, name_item)

            # Wert (berechnet)
            value_item = QTableWidgetItem(f"{value:.6g}")
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)  # Nicht editierbar
            value_item.setForeground(QBrush(QColor("#4EC9B0")))  # Grün für berechnete Werte
            self.table.setItem(row, 1, value_item)

            # Formel (oder direkter Wert)
            formula_text = formula if formula else f"{value:.6g}"
            formula_item = QTableWidgetItem(formula_text)
            if formula:
                formula_item.setForeground(QBrush(QColor("#DCDCAA")))  # Gelb für Formeln
            self.table.setItem(row, 2, formula_item)

            # Einheit (aus Metadaten, falls vorhanden)
            unit_item = QTableWidgetItem("mm")  # Standard
            self.table.setItem(row, 3, unit_item)

            # Kommentar
            comment_item = QTableWidgetItem("")
            self.table.setItem(row, 4, comment_item)

        self.table.blockSignals(False)

    def _on_item_changed(self, item):
        """Reagiert auf Änderungen in der Tabelle."""
        row = item.row()
        col = item.column()

        # Name-Änderung
        if col == 0:
            old_name = item.data(Qt.UserRole)
            new_name = item.text().strip()

            if old_name and new_name and old_name != new_name:
                # Parameter umbenennen
                old_value = self.parameters.get(old_name)
                old_formula = self.parameters.get_formula(old_name)

                self.parameters.delete(old_name)

                try:
                    if old_formula:
                        self.parameters.set(new_name, old_formula)
                    else:
                        self.parameters.set(new_name, old_value)
                    item.setData(Qt.UserRole, new_name)
                    self.parameters_changed.emit()
                except ValueError as e:
                    QMessageBox.warning(self, tr("Error"), str(e))
                    item.setText(old_name)

        # Formel-Änderung
        elif col == 2:
            name_item = self.table.item(row, 0)
            if name_item:
                name = name_item.text()
                formula = item.text().strip()

                try:
                    # Versuche als Zahl
                    try:
                        value = float(formula)
                        self.parameters.set(name, value)
                    except ValueError:
                        # Es ist eine Formel
                        self.parameters.set(name, formula)

                    self._load_parameters()  # Tabelle aktualisieren
                    self.parameters_changed.emit()

                except Exception as e:
                    QMessageBox.warning(self, tr("Error"), f"{tr('Invalid formula')}: {e}")
                    self._load_parameters()

    def _add_parameter(self):
        """Fügt einen neuen Parameter hinzu."""
        name = self.name_edit.text().strip()
        value = self.value_edit.text().strip()

        if not name:
            self.name_edit.setFocus()
            return

        if not value:
            self.value_edit.setFocus()
            return

        try:
            # Versuche als Zahl
            try:
                num_value = float(value)
                self.parameters.set(name, num_value)
            except ValueError:
                # Es ist eine Formel
                self.parameters.set(name, value)

            self._load_parameters()
            self.parameters_changed.emit()

            # Eingabefelder leeren
            self.name_edit.clear()
            self.value_edit.clear()
            self.name_edit.setFocus()

        except ValueError as e:
            QMessageBox.warning(self, tr("Error"), str(e))

    def _delete_selected(self):
        """Löscht den ausgewählten Parameter."""
        row = self.table.currentRow()
        if row < 0:
            return

        name_item = self.table.item(row, 0)
        if name_item:
            name = name_item.text()

            reply = QMessageBox.question(
                self, tr("Delete Parameter"),
                tr("Delete parameter '{name}'?").format(name=name),
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.parameters.delete(name)
                self._load_parameters()
                self.parameters_changed.emit()

    def _show_context_menu(self, pos):
        """Zeigt Kontextmenü für die Tabelle."""
        menu = QMenu(self)

        delete_action = menu.addAction(tr("Delete"))
        delete_action.triggered.connect(self._delete_selected)

        duplicate_action = menu.addAction(tr("Duplicate"))
        duplicate_action.triggered.connect(self._duplicate_selected)

        menu.exec_(self.table.mapToGlobal(pos))

    def _duplicate_selected(self):
        """Dupliziert den ausgewählten Parameter."""
        row = self.table.currentRow()
        if row < 0:
            return

        name_item = self.table.item(row, 0)
        if name_item:
            old_name = name_item.text()
            new_name = f"{old_name}_copy"

            value = self.parameters.get(old_name)
            formula = self.parameters.get_formula(old_name)

            try:
                if formula:
                    self.parameters.set(new_name, formula)
                else:
                    self.parameters.set(new_name, value)

                self._load_parameters()
                self.parameters_changed.emit()
            except ValueError as e:
                QMessageBox.warning(self, tr("Error"), str(e))


class ParameterInputWidget(QLineEdit):
    """
    Erweitertes Eingabefeld das sowohl Zahlen als auch Parameter-Namen akzeptiert.

    Verwendung in Sketch-Dimensionen:
    - Nutzer gibt "100" ein → Wert 100
    - Nutzer gibt "width" ein → Wert aus Parameter "width"
    - Nutzer gibt "width * 2" ein → Berechneter Wert
    """

    value_changed = Signal(float)

    def __init__(self, parameters: Parameters = None, parent=None):
        super().__init__(parent)
        self.parameters = parameters or get_parameters()
        self._last_valid_value = 0.0

        self.setPlaceholderText(tr("Value or parameter name"))
        self.editingFinished.connect(self._on_editing_finished)

    def _on_editing_finished(self):
        """Verarbeitet die Eingabe."""
        text = self.text().strip()
        if not text:
            return

        value = self.evaluate(text)
        if value is not None:
            self._last_valid_value = value
            self.value_changed.emit(value)

    def evaluate(self, expression: str) -> float:
        """
        Evaluiert einen Ausdruck (Zahl, Parameter-Name oder Formel).

        Returns:
            float-Wert oder None bei Fehler
        """
        if not expression:
            return None

        # Versuch 1: Direkte Zahl
        try:
            return float(expression)
        except ValueError:
            pass

        # Versuch 2: Parameter-Name
        if expression in [p[0] for p in self.parameters.list_all()]:
            return self.parameters.get(expression)

        # Versuch 3: Formel evaluieren
        try:
            # Temporär als Parameter setzen und evaluieren
            temp_name = "__temp_eval__"
            self.parameters.set(temp_name, expression)
            result = self.parameters.get(temp_name)
            self.parameters.delete(temp_name)
            return result
        except:
            pass

        return None

    def get_value(self) -> float:
        """Gibt den aktuellen Wert zurück."""
        value = self.evaluate(self.text())
        return value if value is not None else self._last_valid_value

    def set_value(self, value: float):
        """Setzt einen numerischen Wert."""
        self._last_valid_value = value
        self.setText(f"{value:.6g}")
