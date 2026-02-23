"""
MashCad CadQuery Import - Example: Bracket

Simple mounting bracket with two holes.

Demonstrates:
- BuildSketch with Rectangle and Circle
- Boolean subtraction using Mode.SUBTRACT
- Extrusion
"""

import build123d as b

# Create a bracket with two mounting holes
with b.BuildPart() as bracket:
    with b.BuildSketch(b.Plane.XY):
        # Base plate
        b.Rectangle(100, 50)
        # Mounting holes (subtracted)
        with b.Locations((10, 25, 0)):
            b.Circle(5, mode=b.Mode.SUBTRACT)
        with b.Locations((90, 25, 0)):
            b.Circle(5, mode=b.Mode.SUBTRACT)
    b.extrude(amount=10)

    # Fillet the edges
    b.fillet(bracket.edges(), radius=2)
