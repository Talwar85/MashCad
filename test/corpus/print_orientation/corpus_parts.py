"""
Reference Test Parts for Print Orientation Validation

Each part is constructible in <1 second using Build123d.
All parts serve as test fixtures for orientation recommendation.
"""

from build123d import *
import math
from typing import Any


def make_cube(size: float = 20) -> Part:
    """Simple cube - all orientations equivalent."""
    return Box(size, size, size)


def make_plate(width: float, length: float, height: float) -> Part:
    """Flat plate - flat_down is best, edge_down is worst (tipping)."""
    return Box(width, length, height)


def make_bridge_sample(span: float, width: float, height: float) -> Part:
    """
    Bridge sample - two supports with horizontal connection.

    Bridge should be recognized as bridge, not overhang.
    Best orientation: bridge on top (no support needed).
    """
    support_width = 10
    support_height = height
    support_depth = width

    # Two supports
    support1 = Box(support_width, support_depth, support_height)
    support2 = Box(support_width, support_depth, support_height)

    # Bridge deck
    bridge = Box(span, width, 5)

    # Position using Location
    deck_height = height - 5
    support1_pos = Location((-span/2 - support_width/2, -width/2, 0))
    support2_pos = Location((span/2 - support_width/2, -width/2, 0))
    bridge_pos = Location((0, -width/2, deck_height))

    return Compound(
        support1.located(support1_pos),
        support2.located(support2_pos),
        bridge.located(bridge_pos)
    )


def make_arch(width: float, height: float, thickness: float) -> Part:
    """
    Arch - curved top, no bridge support needed.
    """
    # Simplified arch using half-cylinder extrusion
    arch_half = Cylinder(width, thickness)
    arch_half = arch_half.located(Location((0, 0, height)))

    # Add base plate
    base = Box(width * 2, thickness, 10)

    return base + arch_half


def make_tall_tower(radius: float, height: float) -> Part:
    """
    Tall narrow tower - stability risk when upright.

    Best orientation: lying down (max stability).
    Worst: upright (tipping risk).
    """
    return Cylinder(radius, height)


def make_l_bracket(width: float, depth: float, thickness: float) -> Part:
    """Simple L-bracket for mechanical parts."""
    # Horizontal leg
    h_leg = Box(width, depth, thickness)

    # Vertical leg
    v_leg = Box(thickness, depth, width)

    return Compound(h_leg, v_leg)


def make_holey_part(size: float = 30) -> Part:
    """Part with holes - mechanical part example."""
    base = Box(size, size, 10)

    # Add some holes
    hole1 = Cylinder(5, 15)
    hole2 = Cylinder(8, 10)

    return base - hole1.located(Location((size/3, size/3, 0))) \
                  - hole2.located(Location((2*size/3, 2*size/3, 0)))


def make_fillet_cube(size: float = 15) -> Part:
    """Cube with rounded edges - fillet-heavy part."""
    box = Box(size, size, size)
    return fillet(box.edges(), radius=2)


def get_corpus_parts() -> dict:
    """
    Returns dict of all corpus test parts.

    Returns:
        Dict mapping part_name -> Build123d Model
    """
    return {
        'cube': make_cube(20),
        'flat_plate': make_plate(100, 100, 5),
        'bridge': make_bridge_sample(60, 10, 20),
        'arch': make_arch(50, 25, 5),
        'tall_tower': make_tall_tower(8, 60),
        'l_bracket': make_l_bracket(40, 30, 5),
        'holey_part': make_holey_part(30),
        'fillet_cube': make_fillet_cube(15),
    }


# Expected results for validation

CORPUS_EXPECTATIONS = {
    'cube': {
        'description': 'All orientations are equivalent',
        'best_orientation': 'any',
        'risk_level': 'low',
        'needs_support': False,
    },
    'flat_plate': {
        'description': 'Flat down is best, edge down worst (tipping)',
        'best_orientation': 'flat_down',
        'risk_level': 'medium',
        'needs_support': False,
    },
    'bridge': {
        'description': 'Bridge must be recognized, not treated as overhang',
        'best_orientation': 'bridge_on_top',
        'risk_level': 'low',
        'needs_support': False,
    },
    'arch': {
        'description': 'Curved top is self-supporting',
        'best_orientation': 'arch_upright',
        'risk_level': 'low',
        'needs_support': False,
    },
    'tall_tower': {
        'description': 'Lying down is best for stability',
        'best_orientation': 'lying_down',
        'risk_level': 'high',
        'needs_support': False,
    },
    'l_bracket': {
        'description': 'Mechanical part with internal features',
        'best_orientation': 'depends_on_features',
        'risk_level': 'medium',
        'needs_support': 'possibly',
    },
    'holey_part': {
        'description': 'Part with holes - bridging may occur',
        'best_orientation': 'depends_on_orientation',
        'risk_level': 'medium',
        'needs_support': 'possibly',
    },
    'fillet_cube': {
        'description': 'Rounded edges - no sharp overhangs',
        'best_orientation': 'any',
        'risk_level': 'low',
        'needs_support': False,
    },
}


def get_expected_recommendation(part_name: str) -> str:
    """
    Get expected orientation recommendation for a part.

    Returns a string describing the expected best orientation.
    """
    return CORPUS_EXPECTATIONS[part_name]['best_orientation']


if __name__ == "__main__":
    # Test that all parts can be created
    parts = get_corpus_parts()
    print(f"Created {len(parts)} corpus parts:")

    for name, part in parts.items():
        try:
            part.volume  # Test if valid BRep
            print(f"  ✓ {name}: {CORPUS_EXPECTATIONS[name]['description']}")
        except Exception as e:
            print(f"  ✗ {name}: Failed to create - {e}")
