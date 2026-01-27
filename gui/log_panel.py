import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QFrame, QToolButton, QLineEdit
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QFont
from i18n import tr

class LogPanel(QFrame):
    """
    Persistentes Log-Panel unter dem Browser.
    Zeigt Historie aller Aktionen und erlaubt Filterung.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background: #1e1e1e; border-top: 1px solid #333; }
            QListWidget { 
                background: #1e1e1e; border: none; font-family: Consolas, monospace; font-size: 10px; 
            }
            QListWidget::item { padding: 2px; border-bottom: 1px solid #252526; }
            QListWidget::item:selected { background: #094771; }
            QLabel { color: #888; font-weight: bold; font-size: 10px; }
            QToolButton { 
                background: transparent; border: 1px solid #333; border-radius: 2px; color: #888; 
                padding: 1px 4px; font-size: 9px;
            }
            QToolButton:checked { background: #333; color: white; border-color: #555; }
            QToolButton:hover { border-color: #666; }
        """)
        
        self._setup_ui()
        self.filters = {"info": True, "success": True, "warning": True, "error": True}

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Header / Filter Bar ---
        header = QFrame()
        header.setFixedHeight(24)
        header.setStyleSheet("background: #252526;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(4, 0, 4, 0)
        h_layout.setSpacing(4)

        title = QLabel(tr("Protocol"))
        h_layout.addWidget(title)
        
        h_layout.addStretch()

        # Filter Buttons
        self.btn_info = self._create_filter_btn("Info", "info", "#0078d4")
        self.btn_success = self._create_filter_btn("OK", "success", "#107c10")
        self.btn_warn = self._create_filter_btn("Warn", "warning", "#ffb900")
        self.btn_err = self._create_filter_btn("Err", "error", "#d13438")
        
        h_layout.addWidget(self.btn_info)
        h_layout.addWidget(self.btn_success)
        h_layout.addWidget(self.btn_warn)
        h_layout.addWidget(self.btn_err)
        
        btn_clear = QToolButton()
        btn_clear.setText("🗑")
        btn_clear.setToolTip(tr("Clear log"))
        btn_clear.clicked.connect(self.clear_log)
        h_layout.addWidget(btn_clear)

        layout.addWidget(header)

        # --- List Widget ---
        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        layout.addWidget(self.list_widget)

    def _create_filter_btn(self, text, level, color_code):
        btn = QToolButton()
        btn.setText(text)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.clicked.connect(lambda: self._toggle_filter(level))
        # Kleiner Farb-Indikator
        btn.setStyleSheet(f"""
            QToolButton:checked {{ border-bottom: 2px solid {color_code}; color: #ddd; }}
        """)
        return btn

    def _toggle_filter(self, level):
        self.filters[level] = not self.filters[level]
        self._refresh_visibility()

    def _refresh_visibility(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            lvl = item.data(Qt.UserRole)
            item.setHidden(not self.filters.get(lvl, True))

    def add_message(self, level, message):
        """Fügt eine Nachricht hinzu"""
        # Mapping auf interne Level-Keys
        if level in ["critical", "fatal"]: level = "error"
        if level == "debug": level = "info"
        
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Icon/Farbe bestimmen
        colors = {
            "info": "#0078d4",
            "success": "#107c10",
            "warning": "#ffb900",
            "error": "#d13438"
        }
        color = colors.get(level, "#888")
        icon_text = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✕"}.get(level, "•")
        
        # Item erstellen
        item = QListWidgetItem()
        item.setData(Qt.UserRole, level)
        
        # Widget für das Item (für mehrspaltiges Layout)
        widget = QWidget()
        w_layout = QHBoxLayout(widget)
        w_layout.setContentsMargins(4, 2, 4, 2)
        w_layout.setSpacing(6)
        
        lbl_time = QLabel(timestamp)
        lbl_time.setStyleSheet("color: #555; font-size: 9px;")
        
        lbl_icon = QLabel(icon_text)
        lbl_icon.setStyleSheet(f"color: {color}; font-weight: bold;")
        lbl_icon.setFixedWidth(12)
        
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet(f"color: {'#ff8888' if level == 'error' else '#ccc'};")
        
        w_layout.addWidget(lbl_time)
        w_layout.addWidget(lbl_icon)
        w_layout.addWidget(lbl_msg, 1)
        
        item.setSizeHint(widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)
        
        # Auto-Scroll
        self.list_widget.scrollToBottom()
        
        # Sichtbarkeit prüfen
        item.setHidden(not self.filters.get(level, True))

    def clear_log(self):
        self.list_widget.clear()