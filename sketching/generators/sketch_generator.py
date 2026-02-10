"""
Sketch Generator - Generiert zufällige aber plausible Sketches

Erstellt verschiedene Profil-Typen für Extrusion:
- Rectangle
- Circle
- Polygon
- Multi-Circle (Kreis mit Löchern)
- Complex (Kombination)

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import random
import math
from typing import List, Tuple, Optional
from loguru import logger

# Importiere Sketch-Klassen
try:
    from sketcher import Sketch
    from sketcher.geometry import Point2D, Circle2D, Line2D, Arc2D
except ImportError:
    # Fallback für Tests
    Sketch = None


PROFILE_STRATEGIES = {
    "rectangle": {
        "probability": 0.30,
        "params": {
            "width": (10, 100),
            "height": (10, 100),
            "corner_radius": (0, 10)
        }
    },
    "circle": {
        "probability": 0.25,
        "params": {
            "radius": (5, 50),
            "center_x": (-50, 50),
            "center_y": (-50, 50)
        }
    },
    "polygon": {
        "probability": 0.20,
        "params": {
            "sides": (3, 8),
            "radius": (10, 60)
        }
    },
    "multi_circle": {
        "probability": 0.15,
        "params": {
            "main_radius": (20, 50),
            "hole_count": (1, 5),
            "hole_radius": (5, 15)
        }
    },
    "complex": {
        "probability": 0.10,
        "params": {
            "base": "rectangle",
            "features": ["fillet_corners", "add_holes", "add_slots"]
        }
    }
}


class SketchGenerator:
    """
    Generiert zufällige aber plausible Sketches.

    Strategien:
    - rectangle: Rechteck mit optionalen Fillets
    - circle: Einfacher Kreis
    - polygon: 3-8 seitiges Polygon
    - multi_circle: Kreis mit mehreren Löchern
    - complex: Kombination aus mehreren Features
    """

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)

        self._strategies = list(PROFILE_STRATEGIES.keys())
        self._probabilities = [
            PROFILE_STRATEGIES[s]["probability"]
            for s in self._strategies
        ]

    def generate_random_profile(
        self,
        name: str = "Generated Sketch"
    ) -> Optional['Sketch']:
        """
        Generiert ein zufälliges Profil für Extrusion.

        Returns:
            Sketch Objekt oder None wenn Sketch nicht verfügbar
        """
        if Sketch is None:
            logger.warning("[SketchGenerator] Sketch nicht verfügbar")
            return None

        strategy = random.choices(
            self._strategies,
            weights=self._probabilities,
            k=1
        )[0]

        logger.debug(f"[SketchGenerator] Strategy: {strategy}")

        if strategy == "rectangle":
            return self._generate_rectangle(name)
        elif strategy == "circle":
            return self._generate_circle(name)
        elif strategy == "polygon":
            return self._generate_polygon(name)
        elif strategy == "multi_circle":
            return self._generate_multi_circle(name)
        elif strategy == "complex":
            return self._generate_complex(name)
        else:
            return self._generate_rectangle(name)

    def _generate_rectangle(self, name: str) -> 'Sketch':
        """Generiert ein Rechteck."""
        params = PROFILE_STRATEGIES["rectangle"]["params"]
        width = random.uniform(*params["width"])
        height = random.uniform(*params["height"])

        sketch = Sketch(name)
        # Verwende die eingebaute add_rectangle Methode
        sketch.add_rectangle(-width / 2, -height / 2, width, height)

        logger.debug(f"[SketchGenerator] Rectangle: {width:.1f}x{height:.1f}")
        return sketch

    def _generate_circle(self, name: str) -> 'Sketch':
        """Generiert einen Kreis."""
        params = PROFILE_STRATEGIES["circle"]["params"]
        radius = random.uniform(*params["radius"])
        center_x = random.uniform(*params["center_x"])
        center_y = random.uniform(*params["center_y"])

        sketch = Sketch(name)
        sketch.add_circle(center_x, center_y, radius)

        logger.debug(f"[SketchGenerator] Circle: r={radius:.1f} at ({center_x:.1f}, {center_y:.1f})")
        return sketch

    def _generate_polygon(self, name: str) -> 'Sketch':
        """Generiert ein Polygon (3-8 Seiten)."""
        params = PROFILE_STRATEGIES["polygon"]["params"]
        sides = random.randint(*params["sides"])
        radius = random.uniform(*params["radius"])

        sketch = Sketch(name)
        # Verwende die eingebaute add_regular_polygon Methode
        # Diese erstellt automatisch verbundene Linien mit Constraints
        sketch.add_regular_polygon(0, 0, radius, sides)

        logger.debug(f"[SketchGenerator] Polygon: {sides} sides, r={radius:.1f}")
        return sketch

    def _generate_multi_circle(self, name: str) -> 'Sketch':
        """Generiert einen Kreis mit mehreren Löchern."""
        params = PROFILE_STRATEGIES["multi_circle"]["params"]
        main_radius = random.uniform(*params["main_radius"])
        hole_count = random.randint(*params["hole_count"])
        hole_radius = random.uniform(*params["hole_radius"])

        sketch = Sketch(name)

        # Hauptkreis
        sketch.add_circle(0, 0, main_radius)

        # Löcher auf einem Kreis verteilt
        if hole_count > 0:
            hole_radius_offset = main_radius * 0.6
            angle_step = 2 * math.pi / hole_count

            for i in range(hole_count):
                angle = i * angle_step
                hx = hole_radius_offset * math.cos(angle)
                hy = hole_radius_offset * math.sin(angle)
                sketch.add_circle(hx, hy, hole_radius)

        logger.debug(f"[SketchGenerator] Multi-Circle: r={main_radius:.1f}, {hole_count} holes")
        return sketch

    def _generate_complex(self, name: str) -> 'Sketch':
        """Generiert ein komplexes Profil mit mehreren Features."""
        base_type = random.choice(["rectangle", "circle"])

        if base_type == "rectangle":
            sketch = self._generate_rectangle(name)
            # Zusätzliche Features könnten hier hinzugefügt werden
        else:
            sketch = self._generate_circle(name)

        logger.debug(f"[SketchGenerator] Complex profile (base: {base_type})")
        return sketch

    def generate_mechanical_profile(
        self,
        part_type: str,
        name: str = "Mechanical Part"
    ) -> Optional['Sketch']:
        """
        Generiert ein mechanisches Bauteil mit typischen Formen.

        Args:
            part_type: "shaft", "flange", "bracket", oder "housing"

        Returns:
            Sketch Objekt oder None
        """
        if Sketch is None:
            return None

        if part_type == "shaft":
            return self._generate_shaft(name)
        elif part_type == "flange":
            return self._generate_flange(name)
        elif part_type == "bracket":
            return self._generate_bracket(name)
        elif part_type == "housing":
            return self._generate_housing(name)
        else:
            return self._generate_rectangle(name)

    def _generate_shaft(self, name: str) -> 'Sketch':
        """Generiert eine Welle (Kreis für Rotation)."""
        radius = random.uniform(10, 25)
        sketch = Sketch(name)
        sketch.add_circle(0, 0, radius)
        logger.debug(f"[SketchGenerator] Shaft: r={radius:.1f}")
        return sketch

    def _generate_flange(self, name: str) -> 'Sketch':
        """Generiert einen Flansch (Kreis mit Bohrungen)."""
        outer_radius = random.uniform(50, 100)
        inner_radius = random.uniform(20, 40)
        bolt_count = random.choice([4, 6, 8])
        bolt_radius = random.uniform(5, 10)
        bolt_circle_radius = (outer_radius + inner_radius) / 2

        sketch = Sketch(name)

        # Hauptkreis (Aussen)
        sketch.add_circle(0, 0, outer_radius)

        # Innenkreis
        sketch.add_circle(0, 0, inner_radius)

        # Bohrungen
        for i in range(bolt_count):
            angle = i * (2 * math.pi / bolt_count)
            bx = bolt_circle_radius * math.cos(angle)
            by = bolt_circle_radius * math.sin(angle)
            sketch.add_circle(bx, by, bolt_radius)

        logger.debug(f"[SketchGenerator] Flange: r={outer_radius:.1f}, {bolt_count} bolts")
        return sketch

    def _generate_bracket(self, name: str) -> 'Sketch':
        """Generiert einen Winkelhalter (L-Form)."""
        width = random.uniform(30, 80)
        height = random.uniform(50, 120)
        thickness = random.uniform(5, 15)

        sketch = Sketch(name)

        # L-Form als zwei Rechtecke
        # Vertikaler Teil
        sketch.add_rectangle(-width/2, 0, width, height)

        # Horizontaler Teil (würde in Sketch-Tool zu Union führen)
        # Für jetzt einfaches Rechteck als Basis
        logger.debug(f"[SketchGenerator] Bracket: {width:.1f}x{height:.1f}")
        return sketch

    def _generate_housing(self, name: str) -> 'Sketch':
        """Generiert ein Gehäuse (Rechteck)."""
        width = random.uniform(50, 150)
        depth = random.uniform(50, 150)
        wall_thickness = random.uniform(3, 10)

        sketch = Sketch(name)
        sketch.add_rectangle(-width/2, -depth/2, width, depth)

        logger.debug(f"[SketchGenerator] Housing: {width:.1f}x{depth:.1f}")
        return sketch
