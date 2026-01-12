"""
MashCad - Input Dialogs
Reusable dialogs for user input
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QDoubleSpinBox, QDialogButtonBox, QFormLayout, QComboBox
)


class VectorInputDialog(QDialog):
    """Dialog für Vektor-Eingabe (X, Y, Z)"""
    
    def __init__(self, title="Eingabe", labels=("X:", "Y:", "Z:"), defaults=(0.0, 0.0, 0.0), parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        self.inputs = []
        
        for label, default in zip(labels, defaults):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(-99999.0, 99999.0)
            spin.setDecimals(2)
            spin.setValue(default)
            row.addWidget(spin)
            layout.addLayout(row)
            self.inputs.append(spin)
            
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self):
        """Gibt Liste der eingegebenen Werte zurück"""
        return [spin.value() for spin in self.inputs]


class BooleanDialog(QDialog):
    """Dialog für Boolesche Operationen: Wähle Target und Tool"""
    
    def __init__(self, bodies, operation="Cut", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Boolean: {operation}")
        self.bodies = bodies
        layout = QFormLayout(self)
        
        self.cb_target = QComboBox()
        self.cb_tool = QComboBox()
        
        for b in bodies:
            self.cb_target.addItem(b.name, b.id)
            self.cb_tool.addItem(b.name, b.id)
            
        # Standard: Letzter ist Tool, Vorletzter ist Target
        if len(bodies) >= 2:
            self.cb_target.setCurrentIndex(len(bodies) - 2)
            self.cb_tool.setCurrentIndex(len(bodies) - 1)
            
        layout.addRow("Ziel-Körper (bleibt):", self.cb_target)
        layout.addRow("Werkzeug-Körper (wird benutzt):", self.cb_tool)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)
        
    def get_ids(self):
        """Gibt (target_id, tool_id) zurück"""
        return self.cb_target.currentData(), self.cb_tool.currentData()
