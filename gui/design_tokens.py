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
        """Zentraler CSS String für Dialoge"""
        return f"""
            QFrame, QDialog, QWidget {{ 
                background-color: {DesignTokens.COLOR_BG_PANEL.name()}; 
                color: {DesignTokens.COLOR_TEXT_PRIMARY.name()}; 
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 11px;
            }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {DesignTokens.COLOR_BG_INPUT.name()};
                border: 1px solid #454545;
                border-radius: 4px;
                padding: 4px;
                color: white;
                selection-background-color: {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border: 1px solid {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QLabel {{ color: {DesignTokens.COLOR_TEXT_PRIMARY.name()}; }}
            QPushButton {{
                background-color: #333337;
                border: 1px solid #454545;
                border-radius: 4px;
                padding: 5px 12px;
                color: white;
            }}
            QPushButton:hover {{ background-color: #3E3E42; }}
            QPushButton:pressed {{ background-color: {DesignTokens.COLOR_PRIMARY.name()}; }}
        """