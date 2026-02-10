"""
Design Library - Vordefinierte Design-Patterns

Bibliothek mit typischen CAD-Formen:
- Shaft: Welle mit Absätzen
- Flange: Flansch mit Bohrungen
- Bracket: Winkelhalter
- Housing: Gehäuse mit Wandstärke

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

import random
import math
from typing import Optional, List, Dict, Any
from loguru import logger


# Design Pattern Definitionen
DESIGN_PATTERNS = {
    "shaft": {
        "base_profile": "circle",
        "operations": [
            {"type": "extrude", "distance": (50, 200)},
            {"type": "fillet", "edges": "end_edges", "radius": (1, 5)},
            {"type": "optional", "op": "add_step", "probability": 0.3},
            {"type": "optional", "op": "add_hole", "probability": 0.2}
        ],
        "parameters": {
            "diameter": (10, 50),
            "length": (50, 200)
        }
    },
    "flange": {
        "base_profile": "circle",
        "operations": [
            {"type": "extrude", "distance": (10, 30)},
            {"type": "add_hole", "pattern": "bolt_circle", "count": (4, 8)},
            {"type": "fillet", "edges": "outer", "radius": (2, 5)}
        ],
        "parameters": {
            "outer_diameter": (50, 150),
            "inner_diameter": (20, 80),
            "hole_diameter": (8, 16)
        }
    },
    "bracket": {
        "base_profile": "l_shape",
        "operations": [
            {"type": "extrude", "distance": (5, 20)},
            {"type": "add_hole", "pattern": "corner", "count": 2},
            {"type": "fillet", "edges": "outer", "radius": (2, 8)}
        ],
        "parameters": {
            "width": (30, 100),
            "height": (50, 150),
            "thickness": (5, 20)
        }
    },
    "housing": {
        "base_profile": "rectangle",
        "operations": [
            {"type": "extrude", "distance": (30, 100)},
            {"type": "shell", "thickness": (2, 10)},
            {"type": "optional", "op": "add_opening", "probability": 0.5},
            {"type": "optional", "op": "add_mounting_holes", "probability": 0.7}
        ],
        "parameters": {
            "width": (50, 200),
            "depth": (50, 200),
            "wall_thickness": (2, 10)
        }
    }
}


class DesignLibrary:
    """
    Bibliothek mit vordefinierten Design-Patterns.

    Erstellt typische CAD-Formen mit parametrisierten Variationen.
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Args:
            seed: Random Seed für Reproduzierbarkeit
        """
        if seed is not None:
            random.seed(seed)

    def get_pattern(self, name: str) -> Dict[str, Any]:
        """
        Gibt Pattern-Definition zurück.

        Args:
            name: Pattern-Name (shaft, flange, bracket, housing)

        Returns:
            Pattern-Definition oder None
        """
        return DESIGN_PATTERNS.get(name)

    def list_patterns(self) -> List[str]:
        """Listet alle verfügbaren Patterns."""
        return list(DESIGN_PATTERNS.keys())

    def generate_from_pattern(
        self,
        name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Generiert Part aus Pattern.

        Args:
            name: Pattern-Name
            params: Parameter-Overrides (optional)

        Returns:
            build123d Solid oder None
        """
        # Lazy Import
        try:
            from sketcher import Sketch
            from modeling import Body, Document, ExtrudeFeature
        except ImportError:
            logger.warning("[DesignLibrary] Modeling nicht verfügbar")
            return None

        pattern = self.get_pattern(name)
        if pattern is None:
            logger.error(f"[DesignLibrary] Unbekanntes Pattern: {name}")
            return None

        logger.info(f"[DesignLibrary] Generiere Pattern: {name}")

        # Pattern-spezifische Generierung
        if name == "shaft":
            return self._generate_shaft(params)
        elif name == "flange":
            return self._generate_flange(params)
        elif name == "bracket":
            return self._generate_bracket(params)
        elif name == "housing":
            return self._generate_housing(params)
        else:
            logger.warning(f"[DesignLibrary] Pattern nicht implementiert: {name}")
            return None

    def _generate_shaft(self, overrides: Optional[Dict] = None) -> Optional[Any]:
        """Generiert eine Welle."""
        from sketcher import Sketch
        from modeling import Body, Document, ExtrudeFeature

        pattern = DESIGN_PATTERNS["shaft"]
        params = self._generate_params(pattern["parameters"], overrides)

        diameter = params.get("diameter", 25)
        length = params.get("length", 100)
        radius = diameter / 2

        try:
            sketch = Sketch("shaft_profile")
            sketch.add_regular_polygon(0, 0, radius, 32)

            doc = Document("ShaftDoc")
            body = Body("ShaftBody", document=doc)
            doc.add_body(body)

            feature = ExtrudeFeature(sketch=sketch, distance=length, operation="New Body")
            body.add_feature(feature)

            solid = body._build123d_solid

            # Optional: Fillets an den Enden
            # TODO: Fix filter_by_axis für ShapeList
            # if random.random() < 0.3:
            #     from build123d import fillet
            #     end_edges = [e for e in solid.edges() if hasattr(e, 'axis')]
            #     if end_edges:
            #         fillet_radius = random.uniform(1, 5)
            #         solid = fillet(end_edges, fillet_radius)

            logger.info(f"[DesignLibrary] Shaft: D={diameter}, L={length}")
            return solid

        except Exception as e:
            logger.error(f"[DesignLibrary] Shaft-Generierung fehlgeschlagen: {e}")
            return None

    def _generate_flange(self, overrides: Optional[Dict] = None) -> Optional[Any]:
        """Generiert einen Flansch mit Bohrungen."""
        from sketcher import Sketch
        from modeling import Body, Document, ExtrudeFeature

        pattern = DESIGN_PATTERNS["flange"]
        params = self._generate_params(pattern["parameters"], overrides)

        outer_d = params.get("outer_diameter", 100)
        inner_d = params.get("inner_diameter", 50)
        hole_d = params.get("hole_diameter", 12)
        thickness = random.uniform(10, 30)

        outer_r = outer_d / 2
        inner_r = inner_d / 2
        hole_r = hole_d / 2

        try:
            sketch = Sketch("flange_profile")

            # Äußerer Kreis (als Polygon)
            sketch.add_regular_polygon(0, 0, outer_r, 32)

            # Innerer Kreis (Bohrung)
            sketch.add_regular_polygon(0, 0, inner_r, 32)

            # Bohrkreis
            bolt_circle_r = (outer_r + inner_r) / 2
            bolt_count = random.choice([4, 6, 8])
            angle_step = 2 * math.pi / bolt_count

            for i in range(bolt_count):
                angle = i * angle_step
                bx = bolt_circle_r * math.cos(angle)
                by = bolt_circle_r * math.sin(angle)
                sketch.add_regular_polygon(bx, by, hole_r, 16)

            doc = Document("FlangeDoc")
            body = Body("FlangeBody", document=doc)
            doc.add_body(body)

            feature = ExtrudeFeature(sketch=sketch, distance=thickness, operation="New Body")
            body.add_feature(feature)

            solid = body._build123d_solid

            logger.info(f"[DesignLibrary] Flange: D={outer_d}, {bolt_count} holes")
            return solid

        except Exception as e:
            logger.error(f"[DesignLibrary] Flange-Generierung fehlgeschlagen: {e}")
            return None

    def _generate_bracket(self, overrides: Optional[Dict] = None) -> Optional[Any]:
        """Generiert einen Winkelhalter (L-Shape)."""
        from sketcher import Sketch
        from modeling import Body, Document, ExtrudeFeature

        pattern = DESIGN_PATTERNS["bracket"]
        params = self._generate_params(pattern["parameters"], overrides)

        width = params.get("width", 60)
        height = params.get("height", 100)
        thickness = params.get("thickness", 10)

        try:
            sketch = Sketch("bracket_profile")

            # L-Form aus zwei Rechtecken
            # Vertikaler Teil
            sketch.add_rectangle(0, 0, thickness, height)
            # Horizontaler Teil
            sketch.add_rectangle(0, height - thickness, width, thickness)

            doc = Document("BracketDoc")
            body = Body("BracketBody", document=doc)
            doc.add_body(body)

            feature = ExtrudeFeature(sketch=sketch, distance=thickness, operation="New Body")
            body.add_feature(feature)

            solid = body._build123d_solid

            logger.info(f"[DesignLibrary] Bracket: {width}x{height}, t={thickness}")
            return solid

        except Exception as e:
            logger.error(f"[DesignLibrary] Bracket-Generierung fehlgeschlagen: {e}")
            return None

    def _generate_housing(self, overrides: Optional[Dict] = None) -> Optional[Any]:
        """Generiert ein Gehäuse (Box mit Wandstärke)."""
        from sketcher import Sketch
        from modeling import Body, Document, ExtrudeFeature

        pattern = DESIGN_PATTERNS["housing"]
        params = self._generate_params(pattern["parameters"], overrides)

        width = params.get("width", 100)
        depth = params.get("depth", 80)
        height = random.uniform(30, 60)
        wall_th = params.get("wall_thickness", 5)

        try:
            sketch = Sketch("housing_profile")
            sketch.add_rectangle(0, 0, width, depth)

            doc = Document("HousingDoc")
            body = Body("HousingBody", document=doc)
            doc.add_body(body)

            # Äußeres Volumen
            feature = ExtrudeFeature(sketch=sketch, distance=height, operation="New Body")
            body.add_feature(feature)
            outer_solid = body._build123d_solid

            # Inneres Volumen (für Hohlraum)
            inner_sketch = Sketch("housing_inner")
            inner_sketch.add_rectangle(wall_th, wall_th, width - 2*wall_th, depth - 2*wall_th)

            # TODO: Boolean Cut für inneren Hohlraum
            # Für jetzt: nur äußerer Solid
            solid = outer_solid

            logger.info(f"[DesignLibrary] Housing: {width}x{depth}x{height}, t={wall_th}")
            return solid

        except Exception as e:
            logger.error(f"[DesignLibrary] Housing-Generierung fehlgeschlagen: {e}")
            return None

    def _generate_params(
        self,
        param_def: Dict[str, tuple],
        overrides: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generiert Parameter aus Definition.

        Args:
            param_def: Parameter-Definition mit (min, max) Tupeln
            overrides: Parameter-Overrides

        Returns:
            Parameter-Dict
        """
        params = {}

        for key, value_range in param_def.items():
            if isinstance(value_range, tuple) and len(value_range) == 2:
                params[key] = random.uniform(value_range[0], value_range[1])
            else:
                params[key] = value_range

        # Overrides anwenden
        if overrides:
            params.update(overrides)

        return params


def create_design_library(seed: Optional[int] = None) -> DesignLibrary:
    """Factory-Funktion für DesignLibrary."""
    return DesignLibrary(seed=seed)


if __name__ == "__main__":
    # Teste alle Patterns
    library = DesignLibrary(seed=42)

    print("Available Patterns:", library.list_patterns())

    for pattern_name in library.list_patterns():
        solid = library.generate_from_pattern(pattern_name)
        if solid:
            print(f"{pattern_name}: ✓ (Volume: {solid.volume:.2f}mm³)")
        else:
            print(f"{pattern_name}: ✗")
