"""
MashCad CadQuery Import - Example: Workplane API Box with Fillet

CadQuery-style chaining example.

Note: 'cq' is pre-defined in the MashCad namespace - do NOT use import.
"""

# Create a box with filleted edges using CadQuery-style syntax
result = cq.Workplane('XY').box(50, 30, 10).faces('>Z').fillet(2)
