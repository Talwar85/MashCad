"""
Profile Strategies - Definitionen für Sketch-Generierungs-Strategien

Enthält alle Profil-Typen mit ihren Parametern und Wahrscheinlichkeiten.

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

from typing import Dict, List, Tuple, Any


PROFILE_STRATEGIES = {
    "rectangle": {
        "probability": 0.30,
        "params": {
            "width": (10, 100),
            "height": (10, 100),
            "corner_radius": (0, 10)
        },
        "description": "Rechteck mit optionalen abgerundeten Ecken"
    },
    "circle": {
        "probability": 0.25,
        "params": {
            "radius": (5, 50),
            "center_x": (-50, 50),
            "center_y": (-50, 50)
        },
        "description": "Einfacher Kreis"
    },
    "polygon": {
        "probability": 0.20,
        "params": {
            "sides": (3, 8),
            "radius": (10, 60)
        },
        "description": "Polygon mit 3-8 Seiten"
    },
    "multi_circle": {
        "probability": 0.15,
        "params": {
            "main_radius": (20, 50),
            "hole_count": (1, 5),
            "hole_radius": (5, 15)
        },
        "description": "Kreis mit mehreren Löchern"
    },
    "complex": {
        "probability": 0.10,
        "params": {
            "base": ["rectangle", "circle"],
            "features": ["fillet_corners", "add_holes", "add_slots"]
        },
        "description": "Komplexes Profil mit mehreren Features"
    }
}


DESIGN_PATTERNS = {
    "shaft": {
        "base_profile": "circle",
        "operations": [
            {"type": "extrude", "distance": (50, 200)},
            {"type": "fillet", "edges": "all", "radius": (1, 5)},
            {"type": "optional", "op": "add_step", "probability": 0.3},
            {"type": "optional", "op": "add_hole", "probability": 0.2}
        ],
        "parameters": {
            "diameter": (10, 50),
            "length": (50, 200)
        },
        "description": "Welle für Rotationsteile"
    },
    "flange": {
        "base_profile": "multi_circle",
        "operations": [
            {"type": "extrude", "distance": (10, 30)},
            {"type": "fillet", "edges": "outer", "radius": (2, 5)}
        ],
        "parameters": {
            "outer_diameter": (50, 150),
            "inner_diameter": (20, 80),
            "hole_diameter": (8, 16)
        },
        "description": "Flansch für Rohrverbindungen"
    },
    "bracket": {
        "base_profile": "rectangle",
        "operations": [
            {"type": "extrude", "distance": (5, 20)},
            {"type": "add_hole", "pattern": "corner", "count": 2},
            {"type": "fillet", "edges": "outer", "radius": (2, 8)}
        ],
        "parameters": {
            "width": (30, 100),
            "height": (50, 150),
            "thickness": (5, 20)
        },
        "description": "Winkelhalter für Montage"
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
        },
        "description": "Gehäuse für Elektronik etc."
    }
}


def get_strategy(name: str) -> Dict[str, Any]:
    """Gibt eine Strategie-Definition zurück."""
    return PROFILE_STRATEGIES.get(name, PROFILE_STRATEGIES["rectangle"])


def get_pattern(name: str) -> Dict[str, Any]:
    """Gibt ein Design-Pattern zurück."""
    return DESIGN_PATTERNS.get(name)


def list_strategies() -> List[str]:
    """Listet alle verfügbaren Strategien."""
    return list(PROFILE_STRATEGIES.keys())


def list_patterns() -> List[str]:
    """Listet alle verfügbaren Design-Patterns."""
    return list(DESIGN_PATTERNS.keys())
