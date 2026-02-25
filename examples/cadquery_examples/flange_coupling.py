"""
MashCad CadQuery Import - Example: Flange Coupling

Mechanical flange with bolt holes.

Demonstrates:
- Circle primitive with extrusion
- Polar array of bolt holes
- Trigonometric positioning
"""

import build123d as b
import math

# Flange parameters
outer_radius = 50
inner_radius = 25
thickness = 15
bolt_radius = 40
hole_radius = 5
num_bolts = 6

# Create flange
with b.BuildPart() as flange:
    # Main disk
    with b.BuildSketch(b.Plane.XY):
        b.Circle(outer_radius)
    b.extrude(amount=thickness)

    # Center bore
    with b.Locations((0, 0, thickness / 2)):
        b.Cylinder(inner_radius, thickness, mode=b.Mode.SUBTRACT)

    # Bolt holes in circular pattern
    angle_step = 360 / num_bolts
    for i in range(num_bolts):
        angle = i * angle_step
        x = bolt_radius * math.cos(math.radians(angle))
        y = bolt_radius * math.sin(math.radians(angle))

        with b.Locations((x, y, thickness / 2)):
            b.Cylinder(hole_radius, thickness, mode=b.Mode.SUBTRACT)
