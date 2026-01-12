"""
MashCad - Notification Widgets
Toast-style notifications and logging integration
"""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer, QPoint, QObject, Signal
from PySide6.QtGui import QColor
from PySide6.QtCore import QPropertyAnimation, QEasingCurve
from loguru import logger


class NotificationWidget(QFrame):
    """Modernes Overlay für Nachrichten (Robust über PyVista)"""
    
    def __init__(self, text, level="info", parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        
        # Wichtige Flags für Sichtbarkeit über OpenGL
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_StyledBackground, True)
        
        # Farben basierend auf Level
        colors = {
            "info": "#0078d4",      # Blau
            "success": "#107c10",   # Grün
            "warning": "#ffb900",   # Gelb/Orange
            "error": "#d13438"      # Rot
        }
        accent = colors.get(level, "#0078d4")
        bg_color = "#252526"
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid #454545;
                border-left: 5px solid {accent};
                border-radius: 4px;
            }}
            QLabel {{ 
                border: none; 
                background: transparent; 
                color: #f0f0f0; 
                font-family: Segoe UI, sans-serif;
                font-size: 13px;
            }}
            QPushButton {{
                color: #aaa;
                background: transparent;
                border: none;
                font-weight: bold;
            }}
            QPushButton:hover {{ color: white; }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Icon
        icons = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✕"}
        lbl_icon = QLabel(icons.get(level, "ℹ"))
        lbl_icon.setStyleSheet(f"font-size: 18px; color: {accent}; font-weight: bold; border: none;")
        layout.addWidget(lbl_icon)
        
        # Text
        lbl_text = QLabel(text)
        lbl_text.setWordWrap(True)
        lbl_text.setStyleSheet("background-color: transparent; border: none;") 
        layout.addWidget(lbl_text, 1)
        
        # Close Button
        btn_close = QPushButton("✕")
        btn_close.setFlat(True)
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.close_anim)
        layout.addWidget(btn_close)
        
        # Animation Setup
        self.anim = QPropertyAnimation(self, b"pos")
        self.target_pos = None 
        
        # Auto-Close Timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close_anim)
        
        duration = 5000 if level == "error" else 3000
        self.timer.start(duration)
        
    def show_anim(self, target_pos):
        """Startet Slide-In Animation"""
        self.target_pos = target_pos
        start_pos = QPoint(target_pos.x(), target_pos.y() - 20)
        
        self.move(start_pos)
        self.show()
        self.raise_()
        
        self.anim.setDuration(250)
        self.anim.setStartValue(start_pos)
        self.anim.setEndValue(target_pos)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()
        
    def close_anim(self):
        """Slide-Out Animation"""
        if not self.target_pos:
            self.close()
            return
            
        end_pos = QPoint(self.target_pos.x(), self.target_pos.y() - 20)
        
        self.anim.setDuration(200)
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(end_pos)
        self.anim.finished.connect(self.close)
        self.anim.start()


class QtLogHandler(QObject):
    """Loguru Sink der Messages an Qt weiterleitet"""
    new_message = Signal(str, str)  # level, text
    
    def __init__(self, parent=None):
        super().__init__(parent)

    def write(self, message):
        record = message.record
        level = record["level"].name.lower()
        text = record["message"]
        self.new_message.emit(level, text)


class MessageManager(QObject):
    """
    Zentraler Message Manager - verbindet:
    - StatusBar
    - LogPanel  
    - Toast Notifications
    - Loguru Logger
    """
    message_received = Signal(str, str)  # level, text
    
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.log_panel = None
        self.notifications = []
        self._setup_loguru()
        
    def _setup_loguru(self):
        """Verbindet Loguru mit diesem Manager"""
        # Eigenen Handler hinzufügen
        logger.add(
            lambda msg: self._on_log_message(msg),
            format="{message}",
            level="DEBUG",
            filter=lambda record: True
        )
    
    def _on_log_message(self, message):
        """Callback von Loguru"""
        record = message.record
        level = record["level"].name.lower()
        text = record["message"]
        self.message_received.emit(level, text)
        
    def set_log_panel(self, panel):
        """Verbindet mit LogPanel"""
        self.log_panel = panel
        self.message_received.connect(
            lambda lvl, txt: panel.add_message(lvl, txt)
        )
        
    def info(self, text, toast=False):
        """Info-Nachricht"""
        self._show(text, "info", toast)
        
    def success(self, text, toast=True):
        """Erfolgs-Nachricht (mit Toast)"""
        self._show(text, "success", toast)
        
    def warning(self, text, toast=True):
        """Warnung (mit Toast)"""
        self._show(text, "warning", toast)
        
    def error(self, text, toast=True):
        """Fehler (mit Toast)"""
        self._show(text, "error", toast)
        
    def _show(self, text, level="info", toast=False):
        """Zeigt Nachricht in StatusBar und optional als Toast"""
        # StatusBar
        if self.main_window:
            duration = 5000 if level == "error" else 3000
            self.main_window.statusBar().showMessage(text, duration)
            
        # LogPanel
        if self.log_panel:
            self.log_panel.add_message(level, text)
            
        # Toast Notification
        if toast and self.main_window:
            self._show_toast(text, level)
            
    def _show_toast(self, text, level):
        """Zeigt Toast-Notification"""
        if not self.main_window:
            return
            
        # Alte Notifications aufräumen
        self.notifications = [n for n in self.notifications if n.isVisible()]
        
        notif = NotificationWidget(text, level, self.main_window)
        
        # Position berechnen (oben rechts, gestapelt)
        offset_y = 10 + len(self.notifications) * 70
        global_pos = self.main_window.mapToGlobal(QPoint(
            self.main_window.width() - 320,
            offset_y
        ))
        
        notif.show_anim(global_pos)
        self.notifications.append(notif)

