"""
MashCad CadQuery Import - Example: Workplane API Flange

Cylindrical flange using CadQuery-style chaining.

Note: 'cq' is pre-defined in the MashCad namespace - do NOT use import.
"""

# Create a flange using cylinder primitive
result = cq.Workplane('XY').cylinder(50, 15).edges('|Z').fillet(3)
