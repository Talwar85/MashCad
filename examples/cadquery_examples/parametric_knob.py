"""
MashCad CadQuery Import - Example: Parametric Knob

Parametric knob design with grip fins.

Demonstrates:
- Parameter-driven design
- Polar array of features
- Multiple boolean operations
"""

# Parameters
diameter = 50
height = 20
grip_count = 8
grip_depth = 5
hole_radius = 8

import build123d as b
import math

# Create the knob
with b.BuildPart() as knob:
    # Main cylinder
    b.Cylinder(diameter / 2, height)

    # Add grip fins around the perimeter
    angle_step = 360 / grip_count
    for i in range(grip_count):
        angle = i * angle_step
        # Position fin on the surface
        x = (diameter / 2 - grip_depth / 2) * math.cos(math.radians(angle))
        y = (diameter / 2 - grip_depth / 2) * math.sin(math.radians(angle))

        with b.Locations((x, y, height / 2)):
            b.Box(grip_depth, 8, height - 4, align=b.Align.CENTER)

    # Center hole
    with b.Locations((0, 0, 0)):
        b.Cylinder(hole_radius, height, mode=b.Mode.SUBTRACT)
