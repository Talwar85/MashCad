"""
STL Reconstruction Panel - UI for STL-to-CAD workflow.

Provides:
- Feature list with checkboxes
- Parameter editor
- Progress tracking
- Reconstruction control

No library modifications - uses standard Qt/PySide6.
"""

import logging
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Qt imports with fallback
try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QTreeWidget, QTreeWidgetItem, QProgressBar, QGroupBox,
        QDoubleSpinBox, QCheckBox, QSplitter, QTextEdit,
        QHeaderView, QMessageBox, QScrollArea, QFrame
    )
    from PySide6.QtCore import Qt, Signal, QThread, QObject
    from PySide6.QtGui import QColor, QBrush, QFont
    QT_AVAILABLE = True
except ImportError:
    logger.warning("PySide6 not available - UI components will not function")
    QT_AVAILABLE = False
    # Dummy classes for type hints
    class QWidget:
        pass
    class Signal:
        pass


@dataclass
class FeatureListItem:
    """Item for feature list display."""
    feature_type: str  # "base_plane", "hole", "pocket", "fillet"
    index: int
    name: str
    confidence: float
    parameters: Dict[str, Any]
    is_selected: bool = True
    is_visible: bool = True


class ReconstructionWorker(QObject):
    """
    Background worker for reconstruction.
    Runs reconstruction in separate thread to keep UI responsive.
    """
    
    step_started = Signal(int, str)  # step_num, description
    step_completed = Signal(int, bool, str)  # step_num, success, message
    progress_updated = Signal(int)  # percent
    reconstruction_finished = Signal(bool, str)  # success, message
    log_message = Signal(str)  # message
    
    def __init__(self, reconstructor, analysis):
        super().__init__()
        self._reconstructor = reconstructor
        self._analysis = analysis
        self._is_cancelled = False
    
    def run(self):
        """Execute reconstruction."""
        try:
            self.log_message.emit("Starting reconstruction...")
            
            # This would call the actual reconstructor
            # For now, just emit signals for testing
            steps = [
                (1, "Creating base sketch"),
                (2, "Extruding base"),
                (3, "Creating hole features"),
                (4, "Finalizing body"),
            ]
            
            total_steps = len(steps)
            
            for i, (step_num, description) in enumerate(steps, 1):
                if self._is_cancelled:
                    self.reconstruction_finished.emit(False, "Cancelled by user")
                    return
                
                self.step_started.emit(step_num, description)
                self.log_message.emit(f"Step {step_num}: {description}")
                
                # Simulate work
                import time
                time.sleep(0.5)
                
                progress = int((i / total_steps) * 100)
                self.progress_updated.emit(progress)
                self.step_completed.emit(step_num, True, f"Completed {description}")
            
            self.reconstruction_finished.emit(True, "Reconstruction complete!")
            
        except Exception as e:
            logger.error(f"Reconstruction failed: {e}")
            self.reconstruction_finished.emit(False, str(e))
    
    def cancel(self):
        """Request cancellation."""
        self._is_cancelled = True
        self.log_message.emit("Cancellation requested...")


class STLReconstructionPanel(QWidget):
    """
    Panel for STL-to-CAD reconstruction workflow.
    
    Sections:
    1. Mesh Quality Status
    2. Feature List (tree with checkboxes)
    3. Feature Details (parameter editor)
    4. Reconstruction Control (progress, buttons)
    5. Log Output
    """
    
    # Signals
    feature_selected = Signal(str, int)  # type, index
    feature_toggled = Signal(str, int, bool)  # type, index, enabled
    feature_modified = Signal(str, int, dict)  # type, index, new_params
    reconstruct_requested = Signal()
    reconstruct_cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        if not QT_AVAILABLE:
            logger.error("Qt not available - panel cannot be created")
            return
        
        self._analysis = None
        self._feature_items: List[FeatureListItem] = []
        self._selected_feature: Optional[FeatureListItem] = None
        self._reconstruction_thread: Optional[QThread] = None
        self._reconstruction_worker: Optional[ReconstructionWorker] = None
        self._is_reconstructing = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("STL to CAD Reconstruction")
        self.setMinimumWidth(400)
        self.setMinimumHeight(600)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. Mesh Quality Section
        self._quality_group = QGroupBox("Mesh Quality")
        self._setup_quality_section()
        layout.addWidget(self._quality_group)
        
        # 2. Feature List Section
        self._features_group = QGroupBox("Detected Features")
        self._setup_features_section()
        layout.addWidget(self._features_group, stretch=2)
        
        # 3. Feature Details Section
        self._details_group = QGroupBox("Feature Details")
        self._setup_details_section()
        layout.addWidget(self._details_group)
        
        # 4. Reconstruction Control Section
        self._control_group = QGroupBox("Reconstruction")
        self._setup_control_section()
        layout.addWidget(self._control_group)
        
        # 5. Log Output
        self._log_group = QGroupBox("Log")
        self._setup_log_section()
        layout.addWidget(self._log_group, stretch=1)
        
        self.setLayout(layout)
    
    def _setup_quality_section(self):
        """Setup mesh quality display."""
        layout = QVBoxLayout()
        
        self._quality_label = QLabel("No mesh loaded")
        self._quality_label.setWordWrap(True)
        layout.addWidget(self._quality_label)
        
        self._quality_details = QLabel("")
        self._quality_details.setStyleSheet("color: gray;")
        layout.addWidget(self._quality_details)
        
        self._quality_group.setLayout(layout)
    
    def _setup_features_section(self):
        """Setup feature tree list."""
        layout = QVBoxLayout()
        
        # Feature tree
        self._feature_tree = QTreeWidget()
        self._feature_tree.setHeaderLabels(["Feature", "Confidence", "Status"])
        self._feature_tree.setColumnWidth(0, 200)
        self._feature_tree.setColumnWidth(1, 100)
        self._feature_tree.setColumnWidth(2, 80)
        self._feature_tree.itemChanged.connect(self._on_feature_item_changed)
        self._feature_tree.itemClicked.connect(self._on_feature_item_clicked)
        
        # Header with check all/none buttons
        header_layout = QHBoxLayout()
        self._check_all_btn = QPushButton("Check All")
        self._check_all_btn.clicked.connect(self._check_all_features)
        self._uncheck_all_btn = QPushButton("Uncheck All")
        self._uncheck_all_btn.clicked.connect(self._uncheck_all_features)
        
        header_layout.addWidget(self._check_all_btn)
        header_layout.addWidget(self._uncheck_all_btn)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        layout.addWidget(self._feature_tree)
        
        self._features_group.setLayout(layout)
    
    def _setup_details_section(self):
        """Setup feature parameter editor."""
        layout = QVBoxLayout()
        
        # Selected feature label
        self._selected_feature_label = QLabel("No feature selected")
        self._selected_feature_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self._selected_feature_label)
        
        # Parameter container
        self._params_container = QFrame()
        self._params_layout = QVBoxLayout()
        self._params_layout.setSpacing(5)
        self._params_container.setLayout(self._params_layout)
        
        layout.addWidget(self._params_container)
        layout.addStretch()
        
        self._details_group.setLayout(layout)
    
    def _setup_control_section(self):
        """Setup reconstruction control buttons and progress."""
        layout = QVBoxLayout()
        
        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)
        
        # Status label
        self._status_label = QLabel("Ready")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self._reconstruct_btn = QPushButton("🚀 Reconstruct CAD")
        self._reconstruct_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 10px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self._reconstruct_btn.clicked.connect(self._on_reconstruct_clicked)
        
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        
        button_layout.addWidget(self._reconstruct_btn)
        button_layout.addWidget(self._cancel_btn)
        
        layout.addLayout(button_layout)
        self._control_group.setLayout(layout)
    
    def _setup_log_section(self):
        """Setup log output text area."""
        layout = QVBoxLayout()
        
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumBlockCount(100)  # Keep last 100 lines
        self._log_text.setStyleSheet("font-family: monospace; font-size: 10px;")
        
        layout.addWidget(self._log_text)
        self._log_group.setLayout(layout)
    
    def set_analysis(self, analysis, quality_report=None):
        """
        Set the feature analysis to display.
        
        Args:
            analysis: STLFeatureAnalysis object
            quality_report: Optional MeshQualityReport
        """
        self._analysis = analysis
        self._feature_items.clear()
        
        # Update quality section
        if quality_report:
            self._update_quality_display(quality_report)
        
        # Update feature list
        self._update_feature_tree()
        
        # Enable reconstruct button if we have features
        has_features = (
            analysis and
            (analysis.base_plane or analysis.holes or analysis.pockets)
        )
        self._reconstruct_btn.setEnabled(has_features and not self._is_reconstructing)
        
        self._log_message(f"Loaded analysis: {len(self._feature_items)} features detected")
    
    def _update_quality_display(self, report):
        """Update quality section with report."""
        if report.is_valid:
            status = "✓ Valid" if report.recommended_action == "proceed" else "⚠ " + report.recommended_action
            color = "green" if report.recommended_action == "proceed" else "orange"
        else:
            status = "✗ Invalid"
            color = "red"
        
        self._quality_label.setText(f"<span style='color: {color};'>{status}</span>")
        self._quality_label.setTextFormat(Qt.RichText)
        
        details = f"Faces: {report.face_count:,} | Vertices: {report.vertex_count:,}"
        if report.is_watertight:
            details += " | Watertight ✓"
        else:
            details += " | Not Watertight ⚠"
        
        self._quality_details.setText(details)
    
    def _update_feature_tree(self):
        """Populate feature tree with analysis data."""
        self._feature_tree.clear()
        
        if not self._analysis:
            return
        
        # Add base plane
        if self._analysis.base_plane:
            item = self._create_tree_item(
                "base_plane", 0, "Base Plane",
                self._analysis.base_plane.confidence,
                {"area": self._analysis.base_plane.area}
            )
            self._feature_tree.addTopLevelItem(item)
        
        # Add holes
        for i, hole in enumerate(self._analysis.holes):
            name = f"Hole #{i+1} (Ø{hole.diameter:.1f}mm)"
            params = {
                "radius": hole.radius,
                "depth": hole.depth,
                "center": hole.center,
            }
            item = self._create_tree_item("hole", i, name, hole.confidence, params)
            self._feature_tree.addTopLevelItem(item)
        
        # Add pockets
        for i, pocket in enumerate(self._analysis.pockets):
            name = f"Pocket #{i+1}"
            params = {"depth": pocket.depth, "center": pocket.center}
            item = self._create_tree_item("pocket", i, name, pocket.confidence, params)
            self._feature_tree.addTopLevelItem(item)
        
        # Add fillets
        for i, fillet in enumerate(self._analysis.fillets):
            name = f"Fillet #{i+1} (R{fillet.radius:.1f}mm)"
            params = {"radius": fillet.radius}
            item = self._create_tree_item("fillet", i, name, fillet.confidence, params)
            self._feature_tree.addTopLevelItem(item)
        
        # Expand all
        self._feature_tree.expandAll()
    
    def _create_tree_item(self, feature_type: str, index: int, 
                         name: str, confidence: float, 
                         parameters: dict) -> QTreeWidgetItem:
        """Create a tree widget item for a feature."""
        # Confidence display
        conf_text = f"{confidence*100:.0f}%"
        
        # Status based on confidence
        if confidence >= 0.9:
            status = "✓ High"
            status_color = QColor(0, 150, 0)
        elif confidence >= 0.7:
            status = "✓ Good"
            status_color = QColor(0, 100, 200)
        elif confidence >= 0.5:
            status = "⚠ Low"
            status_color = QColor(200, 150, 0)
        else:
            status = "⚠ Review"
            status_color = QColor(200, 50, 0)
        
        item = QTreeWidgetItem([name, conf_text, status])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        item.setForeground(2, QBrush(status_color))
        
        # Store feature data
        feature_item = FeatureListItem(
            feature_type=feature_type,
            index=index,
            name=name,
            confidence=confidence,
            parameters=parameters.copy(),
            is_selected=True
        )
        item.setData(0, Qt.UserRole, feature_item)
        self._feature_items.append(feature_item)
        
        return item
    
    def _on_feature_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle feature checkbox change."""
        if column == 0:  # Checkbox column
            feature_item = item.data(0, Qt.UserRole)
            if feature_item:
                feature_item.is_selected = item.checkState(0) == Qt.Checked
                self.feature_toggled.emit(
                    feature_item.feature_type,
                    feature_item.index,
                    feature_item.is_selected
                )
    
    def _on_feature_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle feature selection."""
        feature_item = item.data(0, Qt.UserRole)
        if feature_item:
            self._selected_feature = feature_item
            self._update_details_section(feature_item)
            self.feature_selected.emit(feature_item.feature_type, feature_item.index)
    
    def _update_details_section(self, feature_item: FeatureListItem):
        """Update details section for selected feature."""
        # Update label
        self._selected_feature_label.setText(
            f"{feature_item.name} ({feature_item.feature_type})"
        )
        
        # Clear old parameters
        while self._params_layout.count():
            child = self._params_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add parameter editors
        for param_name, param_value in feature_item.parameters.items():
            param_layout = QHBoxLayout()
            
            label = QLabel(f"{param_name}:")
            label.setMinimumWidth(80)
            param_layout.addWidget(label)
            
            # Create appropriate editor based on type
            if isinstance(param_value, (int, float)):
                spin_box = QDoubleSpinBox()
                spin_box.setDecimals(3)
                spin_box.setRange(0.001, 10000.0)
                spin_box.setValue(float(param_value))
                spin_box.setSuffix(" mm")
                spin_box.valueChanged.connect(
                    lambda v, n=param_name: self._on_param_changed(n, v)
                )
                param_layout.addWidget(spin_box)
            elif isinstance(param_value, tuple) and len(param_value) == 3:
                # Vector (center, etc.)
                coords_text = f"({param_value[0]:.2f}, {param_value[1]:.2f}, {param_value[2]:.2f})"
                coords_label = QLabel(coords_text)
                param_layout.addWidget(coords_label)
            else:
                value_label = QLabel(str(param_value))
                param_layout.addWidget(value_label)
            
            self._params_layout.addLayout(param_layout)
        
        self._params_layout.addStretch()
    
    def _on_param_changed(self, param_name: str, value: float):
        """Handle parameter value change."""
        if self._selected_feature:
            self._selected_feature.parameters[param_name] = value
            self.feature_modified.emit(
                self._selected_feature.feature_type,
                self._selected_feature.index,
                {param_name: value}
            )
            self._log_message(f"Updated {self._selected_feature.name}: {param_name} = {value:.3f}")
    
    def _check_all_features(self):
        """Check all features."""
        for i in range(self._feature_tree.topLevelItemCount()):
            item = self._feature_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
    
    def _uncheck_all_features(self):
        """Uncheck all features."""
        for i in range(self._feature_tree.topLevelItemCount()):
            item = self._feature_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
    
    def _on_reconstruct_clicked(self):
        """Handle reconstruct button click."""
        if self._is_reconstructing:
            return
        
        # Get selected features
        selected_features = [f for f in self._feature_items if f.is_selected]
        if not selected_features:
            QMessageBox.warning(self, "No Features", 
                              "Please select at least one feature to reconstruct.")
            return
        
        self._start_reconstruction()
    
    def _start_reconstruction(self):
        """Start reconstruction process."""
        self._is_reconstructing = True
        self._reconstruct_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._log_text.clear()
        
        self._log_message("Starting reconstruction...")
        self.reconstruct_requested.emit()
        
        # Create and start worker thread
        # Note: In actual implementation, pass real reconstructor
        self._reconstruction_thread = QThread()
        self._reconstruction_worker = ReconstructionWorker(None, self._analysis)
        self._reconstruction_worker.moveToThread(self._reconstruction_thread)
        
        # Connect signals
        self._reconstruction_thread.started.connect(self._reconstruction_worker.run)
        self._reconstruction_worker.step_started.connect(self._on_step_started)
        self._reconstruction_worker.step_completed.connect(self._on_step_completed)
        self._reconstruction_worker.progress_updated.connect(self._progress_bar.setValue)
        self._reconstruction_worker.reconstruction_finished.connect(self._on_reconstruction_finished)
        self._reconstruction_worker.log_message.connect(self._log_message)
        self._reconstruction_worker.finished.connect(self._reconstruction_thread.quit)
        self._reconstruction_worker.finished.connect(self._reconstruction_worker.deleteLater)
        self._reconstruction_thread.finished.connect(self._reconstruction_thread.deleteLater)
        
        self._reconstruction_thread.start()
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        if self._reconstruction_worker:
            self._reconstruction_worker.cancel()
        self.reconstruct_cancelled.emit()
    
    def _on_step_started(self, step_num: int, description: str):
        """Handle reconstruction step start."""
        self._status_label.setText(f"Step {step_num}: {description}")
    
    def _on_step_completed(self, step_num: int, success: bool, message: str):
        """Handle reconstruction step completion."""
        status = "✓" if success else "✗"
        self._log_message(f"{status} Step {step_num}: {message}")
    
    def _on_reconstruction_finished(self, success: bool, message: str):
        """Handle reconstruction completion."""
        self._is_reconstructing = False
        self._reconstruct_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        
        if success:
            self._status_label.setText("✓ Complete")
            self._status_label.setStyleSheet("color: green;")
            self._log_message("✓ Reconstruction completed successfully!")
            QMessageBox.information(self, "Success", message)
        else:
            self._status_label.setText("✗ Failed")
            self._status_label.setStyleSheet("color: red;")
            self._log_message(f"✗ Reconstruction failed: {message}")
            QMessageBox.critical(self, "Error", message)
    
    def _log_message(self, message: str):
        """Add message to log."""
        self._log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self._log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        logger.info(message)
    
    def update_progress(self, percent: int):
        """Update progress bar."""
        self._progress_bar.setValue(percent)
    
    def set_status(self, status: str):
        """Set status text."""
        self._status_label.setText(status)
    
    def is_reconstructing(self) -> bool:
        """Check if reconstruction is in progress."""
        return self._is_reconstructing
    
    def get_selected_features(self) -> List[FeatureListItem]:
        """Get list of selected features."""
        return [f for f in self._feature_items if f.is_selected]
