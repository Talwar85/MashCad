import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QFrame, QToolButton, QLineEdit
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QFont
from i18n import tr

MAX_LOG_ENTRIES = 200
SUPPRESSED_PREFIXES = (
    "SectionCache", "Actor", "♻", "⏭", "🆕", "Edge actor",
    "TNP", "Mesh unchanged", "Cache", "[i18n]", "PERFORMANCE",
)


class LogPanel(QFrame):
    """
    Persistentes Log-Panel unter dem Browser.
    Zeigt Historie aller Aktionen und erlaubt Filterung + Suche.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background: #1e1e1e; border-top: 1px solid #333; }
            QListWidget {
                background: #1e1e1e; border: none;
                font-family: Consolas, monospace; font-size: 10px;
            }
            QListWidget::item { padding: 1px 0px; border-bottom: 1px solid #222; }
            QListWidget::item:selected { background: #094771; }
            QLabel { color: #888; font-weight: bold; font-size: 10px; }
            QToolButton {
                background: transparent; border: 1px solid #333; border-radius: 2px; color: #888;
                padding: 1px 4px; font-size: 9px;
            }
            QToolButton:checked { background: #333; color: white; border-color: #555; }
            QToolButton:hover { border-color: #666; }
            QLineEdit {
                background: #2d2d2d; border: 1px solid #444; border-radius: 2px;
                color: #ccc; font-size: 9px; padding: 1px 4px;
            }
            QLineEdit:focus { border-color: #0078d4; }
        """)

        self._search_text = ""
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
        h_layout.setSpacing(3)

        title = QLabel(tr("Protocol"))
        h_layout.addWidget(title)

        h_layout.addStretch()

        self.btn_info = self._create_filter_btn("I", "info", "#0078d4")
        self.btn_success = self._create_filter_btn("OK", "success", "#107c10")
        self.btn_warn = self._create_filter_btn("W", "warning", "#ffb900")
        self.btn_err = self._create_filter_btn("E", "error", "#d13438")

        h_layout.addWidget(self.btn_info)
        h_layout.addWidget(self.btn_success)
        h_layout.addWidget(self.btn_warn)
        h_layout.addWidget(self.btn_err)

        btn_clear = QToolButton()
        btn_clear.setText("\u2716")
        btn_clear.setFixedSize(18, 18)
        btn_clear.setToolTip(tr("Clear log"))
        btn_clear.clicked.connect(self.clear_log)
        h_layout.addWidget(btn_clear)

        layout.addWidget(header)

        # --- Search Bar (compact, collapsible) ---
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("Search") + "...")
        self._search.setFixedHeight(20)
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        # --- List Widget ---
        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list_widget.setUniformItemSizes(True)
        layout.addWidget(self.list_widget)

        # --- Counter Label ---
        self._counter = QLabel("")
        self._counter.setStyleSheet("color: #555; font-size: 9px; padding: 1px 4px;")
        self._counter.setFixedHeight(14)
        layout.addWidget(self._counter)

    def _create_filter_btn(self, text, level, color_code):
        btn = QToolButton()
        btn.setText(text)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.setFixedSize(22, 18)
        btn.clicked.connect(lambda: self._toggle_filter(level))
        btn.setStyleSheet(f"""
            QToolButton:checked {{ border-bottom: 2px solid {color_code}; color: #ddd; }}
        """)
        return btn

    def _toggle_filter(self, level):
        self.filters[level] = not self.filters[level]
        self._refresh_visibility()

    def _on_search_changed(self, text):
        self._search_text = text.lower()
        self._refresh_visibility()

    def _refresh_visibility(self):
        visible = 0
        total = self.list_widget.count()
        for i in range(total):
            item = self.list_widget.item(i)
            lvl = item.data(Qt.UserRole)
            msg = item.data(Qt.UserRole + 1) or ""

            level_ok = self.filters.get(lvl, True)
            search_ok = not self._search_text or self._search_text in msg.lower()
            show = level_ok and search_ok

            item.setHidden(not show)
            if show:
                visible += 1

        self._counter.setText(f"{visible}/{total}")

    def add_message(self, level, message):
        """Fügt eine Nachricht hinzu. Filtert debug-Spam."""
        if level in ["critical", "fatal"]:
            level = "error"

        # Unterdrücke debug-Spam
        if level == "debug":
            return
        if level == "info" and any(message.startswith(p) for p in SUPPRESSED_PREFIXES):
            return

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        colors = {
            "info": "#0078d4",
            "success": "#107c10",
            "warning": "#ffb900",
            "error": "#d13438"
        }
        color = colors.get(level, "#888")
        icons = {"info": "\u2139", "success": "\u2713", "warning": "\u26A0", "error": "\u2715"}
        icon_text = icons.get(level, "\u2022")

        # Kompakte einzeilige Darstellung statt Custom Widget
        display = f"{timestamp}  {icon_text}  {message}"
        item = QListWidgetItem(display)
        item.setData(Qt.UserRole, level)
        item.setData(Qt.UserRole + 1, message)

        if level == "error":
            item.setForeground(QColor("#ff8888"))
        elif level == "warning":
            item.setForeground(QColor("#e0b020"))
        elif level == "success":
            item.setForeground(QColor("#70c070"))
        else:
            item.setForeground(QColor("#aaa"))

        item.setFont(QFont("Consolas", 9))

        self.list_widget.addItem(item)
        item.setHidden(not self.filters.get(level, True))

        # Limit
        while self.list_widget.count() > MAX_LOG_ENTRIES:
            self.list_widget.takeItem(0)

        self.list_widget.scrollToBottom()
        self._update_counter()

    def _update_counter(self):
        total = self.list_widget.count()
        visible = sum(1 for i in range(total) if not self.list_widget.item(i).isHidden())
        self._counter.setText(f"{visible}/{total}")

    def clear_log(self):
        self.list_widget.clear()
        self._update_counter()
