"""
MashCad - Design System Tokens
Single Source of Truth für Farben, Fonts und visuelle Stile.
"""

from PySide6.QtGui import QColor, QFont, QPen, QBrush
from PySide6.QtCore import Qt

class DesignTokens:
    # --- Palette (Basis-Werte) ---
    # Backgrounds - Abgestuft für Tiefe
    COLOR_BG_CANVAS = QColor("#181818")     # Sehr dunkel, fast schwarz für hohen Kontrast
    COLOR_BG_PANEL = QColor("#252526")      # VS Code Panel Grau
    COLOR_BG_INPUT = QColor("#333337")      # Input Felder
    COLOR_BG_TOOLTIP = QColor("#202020")
    
    # Primärfarben (Accent)
    COLOR_PRIMARY = QColor("#0078D4")       # Fusion Blue
    COLOR_PRIMARY_HOVER = QColor("#2B88D8")
    COLOR_ACCENT = QColor("#005FB8")
    
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
    
    # Text
    COLOR_TEXT_PRIMARY = QColor("#CCCCCC")
    COLOR_TEXT_MUTED = QColor("#858585")
    
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
                background: #1e1e1e;
                color: {txt};
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 7px;
                font-size: 13px;
                selection-background-color: {p};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid {p};
            }}
            QComboBox {{
                background: #1e1e1e;
                color: {txt};
                border: 1px solid #3f3f46;
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
                border-top: 5px solid #999;
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: #1e1e1e;
                color: {txt};
                border: 1px solid #3f3f46;
                selection-background-color: {p};
            }}
            QPushButton {{
                background: #3f3f46;
                color: {txt};
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #505058;
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
                border: 1px solid #3f3f46;
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
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                background: #1e1e1e;
                border: 1px solid #3f3f46;
            }}
            QCheckBox::indicator:checked {{
                background: {p};
                border: 1px solid {p};
            }}
            QTextEdit {{
                background: #1e1e1e;
                color: {txt};
                border: 1px solid #3f3f46;
                border-radius: 6px;
                font-family: 'Consolas', 'Cascadia Code', monospace;
                font-size: 12px;
                padding: 8px;
            }}
            QProgressBar {{
                background: #1e1e1e;
                border: 1px solid #3f3f46;
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