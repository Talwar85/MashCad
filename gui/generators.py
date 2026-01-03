"""
LiteCAD - Spezial-Generatoren
Zahnräder, Sterne, Muster und mehr
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class GearParams:
    """Parameter für Zahnrad-Generierung"""
    module: float = 2.0          # Modul (mm)
    teeth: int = 20              # Anzahl Zähne
    pressure_angle: float = 20   # Eingriffswinkel (Grad)
    clearance: float = 0.25      # Kopfspiel-Faktor
    backlash: float = 0.0        # Flankenspiel (mm)
    center_hole: float = 5.0     # Zentrierbohrung (mm)
    
    @property
    def pitch_diameter(self) -> float:
        """Teilkreisdurchmesser"""
        return self.module * self.teeth
    
    @property
    def addendum(self) -> float:
        """Kopfhöhe"""
        return self.module
    
    @property
    def dedendum(self) -> float:
        """Fußhöhe"""
        return self.module * (1 + self.clearance)
    
    @property
    def outer_diameter(self) -> float:
        """Außendurchmesser"""
        return self.pitch_diameter + 2 * self.addendum
    
    @property
    def root_diameter(self) -> float:
        """Fußkreisdurchmesser"""
        return self.pitch_diameter - 2 * self.dedendum
    
    @property
    def base_diameter(self) -> float:
        """Grundkreisdurchmesser"""
        return self.pitch_diameter * math.cos(math.radians(self.pressure_angle))


def generate_involute_gear(params: GearParams, center: Tuple[float, float] = (0, 0),
                           points_per_tooth: int = 10) -> List[Tuple[float, float]]:
    """
    Generiert Evolventenzahnrad-Profil
    
    Returns: Liste von (x, y) Punkten für das Zahnprofil
    """
    cx, cy = center
    points = []
    
    r_base = params.base_diameter / 2
    r_pitch = params.pitch_diameter / 2
    r_outer = params.outer_diameter / 2
    r_root = params.root_diameter / 2
    
    # Winkel pro Zahn
    tooth_angle = 2 * math.pi / params.teeth
    
    # Evolvente-Funktion
    def involute(base_r: float, r: float) -> float:
        """Berechnet Evolventenwinkel für gegebenen Radius"""
        if r <= base_r:
            return 0
        return math.sqrt((r/base_r)**2 - 1) - math.acos(base_r/r)
    
    # Zahndicke am Teilkreis (halber Winkel)
    tooth_thickness_angle = tooth_angle / 4  # Vereinfacht
    
    for tooth in range(params.teeth):
        base_angle = tooth * tooth_angle
        
        # Zahnflanke links (aufsteigend)
        for i in range(points_per_tooth):
            t = i / (points_per_tooth - 1)
            r = r_root + t * (r_outer - r_root)
            
            if r < r_base:
                # Unterhalb Grundkreis: gerader Fußbereich
                angle = base_angle - tooth_thickness_angle
            else:
                # Evolvente
                inv = involute(r_base, r)
                angle = base_angle - tooth_thickness_angle + inv
            
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))
        
        # Zahnkopf (Bogen)
        for i in range(3):
            t = i / 2
            angle = base_angle - tooth_thickness_angle + involute(r_base, r_outer) + t * (2 * tooth_thickness_angle - 2 * involute(r_base, r_outer))
            x = cx + r_outer * math.cos(angle)
            y = cy + r_outer * math.sin(angle)
            points.append((x, y))
        
        # Zahnflanke rechts (absteigend)
        for i in range(points_per_tooth - 1, -1, -1):
            t = i / (points_per_tooth - 1)
            r = r_root + t * (r_outer - r_root)
            
            if r < r_base:
                angle = base_angle + tooth_thickness_angle
            else:
                inv = involute(r_base, r)
                angle = base_angle + tooth_thickness_angle - inv
            
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            points.append((x, y))
        
        # Zahnlücke (Fußkreis-Bogen)
        next_base = (tooth + 1) * tooth_angle
        for i in range(3):
            t = i / 2
            angle = base_angle + tooth_thickness_angle + t * (next_base - tooth_thickness_angle - (base_angle + tooth_thickness_angle))
            x = cx + r_root * math.cos(angle)
            y = cy + r_root * math.sin(angle)
            points.append((x, y))
    
    return points


def generate_simple_gear(teeth: int, module: float, 
                         center: Tuple[float, float] = (0, 0)) -> List[Tuple[float, float]]:
    """
    Generiert vereinfachtes Zahnrad-Profil (trapezförmige Zähne)
    Einfacher aber schneller als echte Evolvente
    """
    cx, cy = center
    points = []
    
    r_pitch = module * teeth / 2
    r_outer = r_pitch + module
    r_root = r_pitch - 1.25 * module
    
    tooth_angle = 2 * math.pi / teeth
    
    for i in range(teeth):
        base = i * tooth_angle
        
        # Zahnlücke Start
        points.append((
            cx + r_root * math.cos(base),
            cy + r_root * math.sin(base)
        ))
        
        # Flanke hoch links
        points.append((
            cx + r_root * math.cos(base + tooth_angle * 0.15),
            cy + r_root * math.sin(base + tooth_angle * 0.15)
        ))
        
        # Zahnkopf links
        points.append((
            cx + r_outer * math.cos(base + tooth_angle * 0.25),
            cy + r_outer * math.sin(base + tooth_angle * 0.25)
        ))
        
        # Zahnkopf rechts
        points.append((
            cx + r_outer * math.cos(base + tooth_angle * 0.5),
            cy + r_outer * math.sin(base + tooth_angle * 0.5)
        ))
        
        # Flanke runter rechts
        points.append((
            cx + r_root * math.cos(base + tooth_angle * 0.6),
            cy + r_root * math.sin(base + tooth_angle * 0.6)
        ))
        
        # Zahnlücke
        points.append((
            cx + r_root * math.cos(base + tooth_angle * 0.85),
            cy + r_root * math.sin(base + tooth_angle * 0.85)
        ))
    
    return points


def generate_star(points_count: int, outer_radius: float, inner_radius: float,
                  center: Tuple[float, float] = (0, 0), 
                  rotation: float = 0) -> List[Tuple[float, float]]:
    """
    Generiert Stern-Profil
    
    Args:
        points_count: Anzahl der Zacken
        outer_radius: Radius der Spitzen
        inner_radius: Radius der Einbuchtungen
        center: Mittelpunkt
        rotation: Startwinkel in Grad
    """
    cx, cy = center
    points = []
    
    angle_step = math.pi / points_count
    start_angle = math.radians(rotation) - math.pi / 2  # Start oben
    
    for i in range(points_count * 2):
        angle = start_angle + i * angle_step
        r = outer_radius if i % 2 == 0 else inner_radius
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    
    return points


def generate_rounded_rect(width: float, height: float, radius: float,
                          center: Tuple[float, float] = (0, 0),
                          points_per_corner: int = 8) -> List[Tuple[float, float]]:
    """
    Generiert abgerundetes Rechteck
    """
    cx, cy = center
    points = []
    
    # Begrenze Radius
    max_r = min(width, height) / 2
    r = min(radius, max_r)
    
    hw, hh = width / 2, height / 2
    
    # Ecken: oben-rechts, oben-links, unten-links, unten-rechts
    corners = [
        (cx + hw - r, cy + hh - r, 0),
        (cx - hw + r, cy + hh - r, 90),
        (cx - hw + r, cy - hh + r, 180),
        (cx + hw - r, cy - hh + r, 270),
    ]
    
    for corner_x, corner_y, start_deg in corners:
        for i in range(points_per_corner + 1):
            angle = math.radians(start_deg + 90 * i / points_per_corner)
            x = corner_x + r * math.cos(angle)
            y = corner_y + r * math.sin(angle)
            points.append((x, y))
    
    return points


def generate_linear_pattern(base_points: List[Tuple[float, float]],
                           direction: Tuple[float, float],
                           count: int,
                           spacing: float) -> List[List[Tuple[float, float]]]:
    """
    Generiert lineares Muster
    
    Returns: Liste von Punkt-Listen (eine pro Kopie)
    """
    dx, dy = direction
    length = math.hypot(dx, dy)
    if length > 0:
        dx, dy = dx / length * spacing, dy / length * spacing
    
    result = []
    for i in range(count):
        offset_x = dx * i
        offset_y = dy * i
        copied = [(x + offset_x, y + offset_y) for x, y in base_points]
        result.append(copied)
    
    return result


def generate_circular_pattern(base_points: List[Tuple[float, float]],
                             center: Tuple[float, float],
                             count: int,
                             total_angle: float = 360) -> List[List[Tuple[float, float]]]:
    """
    Generiert kreisförmiges Muster
    
    Args:
        base_points: Ursprungspunkte
        center: Drehzentrum
        count: Anzahl Kopien
        total_angle: Gesamtwinkel in Grad (360 = voller Kreis)
    
    Returns: Liste von Punkt-Listen (eine pro Kopie)
    """
    cx, cy = center
    result = []
    
    for i in range(count):
        angle = math.radians(total_angle * i / count)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        
        rotated = []
        for x, y in base_points:
            # Zum Zentrum verschieben
            dx, dy = x - cx, y - cy
            # Rotieren
            rx = dx * cos_a - dy * sin_a
            ry = dx * sin_a + dy * cos_a
            # Zurück verschieben
            rotated.append((cx + rx, cy + ry))
        
        result.append(rotated)
    
    return result


def generate_spline_points(control_points: List[Tuple[float, float]],
                          segments_per_span: int = 10) -> List[Tuple[float, float]]:
    """
    Generiert Catmull-Rom Spline durch Kontrollpunkte
    """
    if len(control_points) < 2:
        return list(control_points)
    
    if len(control_points) == 2:
        # Nur eine Linie
        return list(control_points)
    
    result = []
    n = len(control_points)
    
    for i in range(n - 1):
        p0 = control_points[max(0, i - 1)]
        p1 = control_points[i]
        p2 = control_points[min(n - 1, i + 1)]
        p3 = control_points[min(n - 1, i + 2)]
        
        for j in range(segments_per_span):
            t = j / segments_per_span
            t2 = t * t
            t3 = t2 * t
            
            # Catmull-Rom Koeffizienten
            x = 0.5 * ((2 * p1[0]) +
                       (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            
            y = 0.5 * ((2 * p1[1]) +
                       (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            
            result.append((x, y))
    
    # Letzten Punkt hinzufügen
    result.append(control_points[-1])
    
    return result


# === Dialog-Klassen für Qt ===

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton,
    QDialogButtonBox, QGroupBox, QComboBox, QCheckBox
)
from PySide6.QtCore import Qt


class GearDialog(QDialog):
    """Dialog für Zahnrad-Parameter"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zahnrad Generator")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        
        # Parameter
        form = QFormLayout()
        
        self.teeth_spin = QSpinBox()
        self.teeth_spin.setRange(6, 200)
        self.teeth_spin.setValue(20)
        form.addRow("Zähnezahl:", self.teeth_spin)
        
        self.module_spin = QDoubleSpinBox()
        self.module_spin.setRange(0.5, 20)
        self.module_spin.setValue(2.0)
        self.module_spin.setSuffix(" mm")
        form.addRow("Modul:", self.module_spin)
        
        self.hole_spin = QDoubleSpinBox()
        self.hole_spin.setRange(0, 100)
        self.hole_spin.setValue(5.0)
        self.hole_spin.setSuffix(" mm")
        form.addRow("Bohrung ⌀:", self.hole_spin)
        
        self.pressure_spin = QDoubleSpinBox()
        self.pressure_spin.setRange(14.5, 25)
        self.pressure_spin.setValue(20.0)
        self.pressure_spin.setSuffix("°")
        form.addRow("Eingriffswinkel:", self.pressure_spin)
        
        layout.addLayout(form)
        
        # Info
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #888; font-size: 10px;")
        self._update_info()
        layout.addWidget(self.info_label)
        
        self.teeth_spin.valueChanged.connect(self._update_info)
        self.module_spin.valueChanged.connect(self._update_info)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _update_info(self):
        m = self.module_spin.value()
        z = self.teeth_spin.value()
        d_pitch = m * z
        d_outer = d_pitch + 2 * m
        self.info_label.setText(
            f"Teilkreis-⌀: {d_pitch:.1f} mm\n"
            f"Außen-⌀: {d_outer:.1f} mm"
        )
    
    def get_params(self) -> GearParams:
        return GearParams(
            module=self.module_spin.value(),
            teeth=self.teeth_spin.value(),
            pressure_angle=self.pressure_spin.value(),
            center_hole=self.hole_spin.value()
        )


class StarDialog(QDialog):
    """Dialog für Stern-Parameter"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stern Generator")
        self.setMinimumWidth(280)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.points_spin = QSpinBox()
        self.points_spin.setRange(3, 32)
        self.points_spin.setValue(5)
        form.addRow("Zacken:", self.points_spin)
        
        self.outer_spin = QDoubleSpinBox()
        self.outer_spin.setRange(1, 1000)
        self.outer_spin.setValue(30)
        self.outer_spin.setSuffix(" mm")
        form.addRow("Außenradius:", self.outer_spin)
        
        self.inner_spin = QDoubleSpinBox()
        self.inner_spin.setRange(1, 1000)
        self.inner_spin.setValue(15)
        self.inner_spin.setSuffix(" mm")
        form.addRow("Innenradius:", self.inner_spin)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_params(self) -> Tuple[int, float, float]:
        return (
            self.points_spin.value(),
            self.outer_spin.value(),
            self.inner_spin.value()
        )


class PatternDialog(QDialog):
    """Dialog für Muster-Parameter"""
    
    def __init__(self, pattern_type: str = "linear", parent=None):
        super().__init__(parent)
        self.pattern_type = pattern_type
        self.setWindowTitle(f"{'Lineares' if pattern_type == 'linear' else 'Kreisförmiges'} Muster")
        self.setMinimumWidth(280)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 100)
        self.count_spin.setValue(5)
        form.addRow("Anzahl:", self.count_spin)
        
        if pattern_type == "linear":
            self.spacing_spin = QDoubleSpinBox()
            self.spacing_spin.setRange(0.1, 1000)
            self.spacing_spin.setValue(20)
            self.spacing_spin.setSuffix(" mm")
            form.addRow("Abstand:", self.spacing_spin)
            
            self.angle_spin = QDoubleSpinBox()
            self.angle_spin.setRange(-180, 180)
            self.angle_spin.setValue(0)
            self.angle_spin.setSuffix("°")
            form.addRow("Richtung:", self.angle_spin)
        else:
            self.total_angle_spin = QDoubleSpinBox()
            self.total_angle_spin.setRange(10, 360)
            self.total_angle_spin.setValue(360)
            self.total_angle_spin.setSuffix("°")
            form.addRow("Gesamtwinkel:", self.total_angle_spin)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_params(self) -> dict:
        if self.pattern_type == "linear":
            return {
                "count": self.count_spin.value(),
                "spacing": self.spacing_spin.value(),
                "angle": self.angle_spin.value()
            }
        else:
            return {
                "count": self.count_spin.value(),
                "total_angle": self.total_angle_spin.value()
            }
