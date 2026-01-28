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