"""
MashCad - Design System Tokens
Single Source of Truth für Farben, Fonts und visuelle Stile.
"""

from PySide6.QtGui import QColor, QFont, QPen, QBrush
from PySide6.QtCore import Qt

class DesignTokens:
    # --- Palette (Figma neutral-Palette) ---
    # Backgrounds - Abgestuft für Tiefe
    COLOR_BG_CANVAS = QColor("#171717")     # neutral-900 (Viewport)
    COLOR_BG_PANEL = QColor("#262626")      # neutral-800 (Panels)
    COLOR_BG_ELEVATED = QColor("#404040")   # neutral-700 (Hover, Cards)
    COLOR_BG_INPUT = QColor("#404040")      # neutral-700 (Input Felder)
    COLOR_BG_TOOLTIP = QColor("#171717")    # neutral-900

    # Primärfarben (Figma blue)
    COLOR_PRIMARY = QColor("#2563eb")       # blue-600
    COLOR_PRIMARY_HOVER = QColor("#3b82f6") # blue-500
    COLOR_ACCENT = QColor("#1d4ed8")        # blue-700

    # Borders
    COLOR_BORDER = QColor("#404040")        # neutral-700

    # Status
    COLOR_SUCCESS = QColor("#22c55e")       # green-500
    COLOR_ERROR = QColor("#ef4444")         # red-500

    # Geometrie
    COLOR_GEO_BODY = QColor("#E0E0E0")          # Helles Grauweiß (Standard Linien)
    COLOR_GEO_CONSTRUCTION = QColor("#FF9900")  # Klassisches Orange
    COLOR_GEO_SELECTED = QColor("#4CC2FF")      # Helles Cyan (leuchtend)
    COLOR_GEO_HOVER = QColor("#4CC2FF")         # Gleiche Farbe, aber transparenter im Pen
    COLOR_GEO_FIXED = QColor("#D040D0")         # Magenta für fixierte Geometrie
    
    # Profile (Geschlossene Flächen)
    COLOR_PROFILE_FILL = QColor(0, 120, 212, 30) # Sehr transparentes Blau
    COLOR_PROFILE_HOVER = QColor(0, 120, 212, 60)
    
    # Constraints & Dimensionen
    COLOR_DIMENSION = QColor("#DCDCAA")     # VS Code Gelb-Beige (gut lesbar)
    COLOR_CONSTRAINT = QColor("#4EC9B0")    # VS Code Mint-Grün (unterscheidet sich gut von Geo)
    COLOR_SNAP = QColor("#FF5500")          # Signal-Orange
    
    # Grid & UI
    COLOR_GRID_MAJOR = QColor("#404040")
    COLOR_GRID_MINOR = QColor("#2A2A2A")
    COLOR_AXIS_X = QColor("#F44336")        # Material Red
    COLOR_AXIS_Y = QColor("#4CAF50")        # Material Green
    
    # Text (Figma neutral-Palette)
    COLOR_TEXT_PRIMARY = QColor("#fafafa")  # neutral-50 (weiß)
    COLOR_TEXT_SECONDARY = QColor("#d4d4d4")# neutral-300 (Labels)
    COLOR_TEXT_MUTED = QColor("#a3a3a3")    # neutral-400 (Hints)
    
    # --- Pens (Vorkonfigurierte Stifte) ---
    @staticmethod
    def pen_geo_normal():
        return QPen(DesignTokens.COLOR_GEO_BODY, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    @staticmethod
    def pen_geo_selected():
        # Dicker für Selektion
        return QPen(DesignTokens.COLOR_GEO_SELECTED, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        
    @staticmethod
    def pen_geo_construction():
        return QPen(DesignTokens.COLOR_GEO_CONSTRUCTION, 1.0, Qt.DashLine)

    @staticmethod
    def pen_grid_minor():
        return QPen(DesignTokens.COLOR_GRID_MINOR, 1.0)
        
    @staticmethod
    def brush_selection_area():
        # Blaues Auswahlrechteck, transparent
        c = QColor(DesignTokens.COLOR_PRIMARY)
        c.setAlpha(40)
        return QBrush(c)
        
    @staticmethod
    def stylesheet_dialog():
        """Zentraler CSS String für Dialoge — Single Source of Truth."""
        p = DesignTokens.COLOR_PRIMARY.name()
        ph = DesignTokens.COLOR_PRIMARY_HOVER.name()
        bg = DesignTokens.COLOR_BG_PANEL.name()
        inp = DesignTokens.COLOR_BG_INPUT.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        return f"""
            QDialog {{
                background: {bg};
                color: {txt};
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 13px;
            }}
            QLabel {{
                color: {txt};
                font-size: 13px;
            }}
            QLineEdit, QSpinBox, QDoubleSpinBox {{
                background: #404040;
                color: {txt};
                border: 1px solid #525252;
                border-radius: 6px;
                padding: 7px;
                font-size: 13px;
                selection-background-color: {p};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid {p};
            }}
            QComboBox {{
                background: #404040;
                color: {txt};
                border: 1px solid #525252;
                border-radius: 6px;
                padding: 7px;
                font-size: 13px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #a3a3a3;
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: #262626;
                color: {txt};
                border: 1px solid #404040;
                selection-background-color: {p};
            }}
            QPushButton {{
                background: #404040;
                color: {txt};
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #525252;
            }}
            QPushButton#primary {{
                background: {p};
                color: white;
                font-weight: bold;
            }}
            QPushButton#primary:hover {{
                background: {ph};
            }}
            QGroupBox {{
                color: {txt};
                border: 1px solid #404040;
                border-radius: 6px;
                margin-top: 14px;
                padding: 16px 10px 10px 10px;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }}
            QCheckBox {{
                color: {txt};
                font-size: 13px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
            }}
            QCheckBox::indicator:unchecked {{
                background: #404040;
                border: 1px solid #525252;
            }}
            QCheckBox::indicator:checked {{
                background: {p};
                border: 1px solid {p};
            }}
            QTextEdit {{
                background: #404040;
                color: {txt};
                border: 1px solid #525252;
                border-radius: 6px;
                font-family: 'Consolas', 'Cascadia Code', monospace;
                font-size: 12px;
                padding: 8px;
            }}
            QProgressBar {{
                background: #404040;
                border: 1px solid #525252;
                border-radius: 4px;
                text-align: center;
                color: {txt};
                height: 16px;
            }}
            QProgressBar::chunk {{
                background: {p};
                border-radius: 3px;
            }}
        """

    @staticmethod
    def stylesheet_panel():
        """Stylesheet für Input-Panels (Fillet, Chamfer, Shell, etc.) — konsistent mit Dialogen."""
        p = DesignTokens.COLOR_PRIMARY.name()
        ph = DesignTokens.COLOR_PRIMARY_HOVER.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        panel_bg = "#20242d"
        panel_bg2 = "#1b1f27"
        panel_border = "#2f3541"
        input_bg = "#1a1e26"
        input_border = "#323846"
        btn_bg = "#2b313c"
        btn_border = "#3a4150"
        danger_bg = "#3a2424"
        danger_border = "#6a2b2b"
        return f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {panel_bg}, stop:1 {panel_bg2});
                border: 1px solid {panel_border};
                border-radius: 10px;
            }}
            QLabel {{
                color: {txt};
                border: none;
                font-size: 12px;
            }}
            QLabel#panelTitle {{
                font-size: 13px;
                font-weight: 600;
            }}
            QComboBox {{
                background: {input_bg};
                color: {txt};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 6px 8px;
                min-width: 120px;
            }}
            QComboBox:hover {{ border-color: {p}; }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {panel_bg};
                color: {txt};
                border: 1px solid {panel_border};
                selection-background-color: {p};
                selection-color: {txt};
            }}
            QDoubleSpinBox, QSpinBox {{
                background: {input_bg};
                color: {txt};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 5px 8px;
            }}
            QLineEdit {{
                background: {input_bg};
                color: {txt};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 6px 8px;
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border: 1px solid {p};
            }}
            QCheckBox {{
                color: {txt};
                border: none;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QPushButton {{
                background: {btn_bg};
                color: {txt};
                border: 1px solid {btn_border};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{ background: #353c48; }}
            QPushButton#primary {{
                background: {p};
                border: 1px solid {p};
                color: white;
            }}
            QPushButton#primary:hover {{ background: {ph}; }}
            QPushButton#danger {{
                background: {danger_bg};
                border: 1px solid {danger_border};
                color: #ffdede;
            }}
            QPushButton#danger:hover {{ background: #4a2a2a; }}
            QPushButton#ghost {{
                background: transparent;
                border: 1px solid {btn_border};
                color: {txt};
            }}
            QPushButton#ghost:hover {{ background: #303744; }}
            QPushButton#toggle:checked {{
                background: {p};
                border: 1px solid {p};
                color: white;
            }}
            QGroupBox {{
                color: {muted};
                border: 1px solid {panel_border};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """

    @staticmethod
    def stylesheet_browser():
        """Stylesheet für Browser (links) — Tree, Header, Slider."""
        p = DesignTokens.COLOR_PRIMARY.name()
        bg = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        border = DesignTokens.COLOR_BORDER.name()
        return f"""
            QFrame {{
                background: {bg};
                border: none;
            }}
            QTreeWidget {{
                background: {bg};
                color: {txt};
                border: none;
                outline: none;
                padding: 5px;
            }}
            QTreeWidget::item {{
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QTreeWidget::item:selected {{
                background: {p};
                color: white;
            }}
            QTreeWidget::item:hover {{
                background: {elevated};
            }}
            QHeaderView::section {{
                background: {bg};
                color: {muted};
                padding: 8px;
                border: none;
                border-bottom: 1px solid {border};
                font-weight: bold;
                font-size: 10px;
                text-transform: uppercase;
            }}
            QSlider {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                background: {border};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {p};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QMenu {{
                background: {elevated};
                color: {txt};
                border: 1px solid {border};
                padding: 5px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {p};
            }}
            QLabel {{
                color: {txt};
            }}
        """

    @staticmethod
    def stylesheet_tool_panel():
        """Stylesheet für Tool Panels (rechts) — Sketch und 3D."""
        p = DesignTokens.COLOR_PRIMARY.name()
        bg = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        border = DesignTokens.COLOR_BORDER.name()
        return f"""
            QFrame {{
                background: {bg};
                border: none;
            }}
            QWidget {{
                background: {bg};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QLabel {{
                color: {txt};
                font-size: 13px;
            }}
            QPushButton {{
                background: {elevated};
                color: {txt};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #525252;
                border-color: {p};
            }}
            QPushButton:pressed {{
                background: {p};
            }}
            QPushButton#finishBtn {{
                background: #4CAF50;
                color: white;
                font-weight: bold;
            }}
            QPushButton#finishBtn:hover {{
                background: #45a049;
            }}
        """

    @staticmethod
    def stylesheet_viewport():
        """Stylesheet für Viewport-Overlays und UI-Elemente."""
        p = DesignTokens.COLOR_PRIMARY.name()
        bg = DesignTokens.COLOR_BG_CANVAS.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        return f"""
            QFrame {{
                background: {elevated};
                border: 1px solid #555;
                border-radius: 6px;
            }}
            QFrame#filterBar {{
                background: #2d2d30;
                border: 1px solid #3f3f46;
                border-radius: 6px;
            }}
            QPushButton {{
                background: transparent;
                color: {muted};
                border: none;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {txt};
                background: rgba(255,255,255,0.1);
            }}
            QPushButton:checked {{
                color: {p};
                background: rgba(37,99,235,0.2);
            }}
            QLabel {{
                color: {txt};
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }}
        """

    @staticmethod
    def stylesheet_sketch():
        """Stylesheet für Sketch-Editor UI-Elemente."""
        p = DesignTokens.COLOR_PRIMARY.name()
        canvas = DesignTokens.COLOR_BG_CANVAS.name()
        panel = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        return f"""
            QWidget {{
                background: {canvas};
            }}
            QMenu {{
                background: {elevated};
                color: {txt};
                border: 1px solid #555;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background: {p};
            }}
        """

    @staticmethod
    def stylesheet_widget():
        """Generisches Stylesheet für kleine Widgets (Notifications, Status, etc.)."""
        p = DesignTokens.COLOR_PRIMARY.name()
        bg = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        success = DesignTokens.COLOR_SUCCESS.name()
        error = DesignTokens.COLOR_ERROR.name()
        return f"""
            QFrame {{
                background: {bg};
                border-radius: 6px;
            }}
            QFrame#notification {{
                background: {elevated};
                border: 1px solid #555;
                border-radius: 8px;
            }}
            QFrame#notification.success {{
                border-left: 4px solid {success};
            }}
            QFrame#notification.error {{
                border-left: 4px solid {error};
            }}
            QLabel {{
                color: {txt};
            }}
            QLabel#muted {{
                color: {muted};
            }}
        """

    @staticmethod
    def stylesheet_main():
        """Stylesheet für MainWindow (Menubar, Toolbar, Splitter, StatusBar)."""
        p = DesignTokens.COLOR_PRIMARY.name()
        ph = DesignTokens.COLOR_PRIMARY_HOVER.name()
        bg = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        border = DesignTokens.COLOR_BORDER.name()
        return f"""
            QMainWindow {{ background: {bg}; }}
            QMenuBar {{ 
                background: {bg}; 
                color: {txt}; 
                padding: 2px; 
                border-bottom: 1px solid {border}; 
            }}
            QMenuBar::item {{ padding: 4px 8px; }}
            QMenuBar::item:selected {{ background: {elevated}; }}
            QMenu {{ 
                background: {bg}; 
                color: {txt}; 
                border: 1px solid {border}; 
            }}
            QMenu::item {{ padding: 6px 20px; }}
            QMenu::item:selected {{ background: {p}; }}
            QToolBar {{
                background: {bg};
                border: none;
                border-bottom: 1px solid {border};
                padding: 0 16px;
                spacing: 4px;
                min-height: 56px;
                max-height: 56px;
            }}
            QToolBar QToolButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                color: {txt};
                padding: 8px;
                font-size: 12px;
            }}
            QToolBar QToolButton:hover {{
                background: {elevated};
            }}
            QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{
                background: {p};
                color: white;
            }}
            QSplitter::handle {{
                background: {border};
            }}
            QSplitter::handle:horizontal {{
                width: 1px;
            }}
            QSplitter::handle:vertical {{
                height: 1px;
            }}
            QSplitter::handle:hover {{
                background: {p};
            }}
            QStatusBar {{ 
                background: {bg}; 
                color: {muted}; 
                border-top: 1px solid {border};
            }}
        """

    @staticmethod
    def color_style(color_attr, **kwargs):
        """Erzeugt inline Style-String für eine einzelne Farbe mit optionalen Properties.
        
        Beispiel: DesignTokens.color_style('COLOR_PRIMARY', font_size='12px', font_weight='bold')
        """
        color = getattr(DesignTokens, color_attr).name()
        props = {'color': color}
        props.update(kwargs)
        return '; '.join(f"{k.replace('_', '-')}: {v}" for k, v in props.items())


# =============================================================================
# Decimal Input Utilities - Für konsistente Zahleingabe mit Komma und Punkt
# =============================================================================

def create_decimal_validator():
    """
    Erstellt einen Validator der sowohl Komma als auch Punkt als Dezimaltrenner akzeptiert.
    Verwenden für alle numerischen Eingabefelder.
    """
    from PySide6.QtGui import QRegularExpressionValidator
    from PySide6.QtCore import QRegularExpression
    # Erlaubt: 0, 1.5, 1,5, 10.25, 10,25, -5.0, -5,0 etc.
    decimal_regex = QRegularExpression(r"^-?\d+([.,]\d*)?$")
    return QRegularExpressionValidator(decimal_regex)


def parse_decimal(text: str, default: float = 0.0) -> float:
    """
    Parst eine Dezimalzahl aus Text, akzeptiert sowohl Komma als auch Punkt.

    Args:
        text: Eingabetext (z.B. "4,5" oder "4.5")
        default: Fallback-Wert bei leerem oder ungültigem Text

    Returns:
        Geparster Float-Wert
    """
    if not text or not text.strip():
        return default
    try:
        # Ersetze Komma durch Punkt für float()
        return float(text.strip().replace(",", "."))
    except ValueError:
        return default


def setup_decimal_input(line_edit, placeholder: str = None):
    """
    Konfiguriert ein QLineEdit für Dezimaleingabe mit Komma/Punkt-Unterstützung.

    Args:
        line_edit: QLineEdit Widget
        placeholder: Optionaler Placeholder-Text (z.B. "0.1 - 10.0")
    """
    line_edit.setValidator(create_decimal_validator())
    if placeholder:
        line_edit.setPlaceholderText(placeholder)
