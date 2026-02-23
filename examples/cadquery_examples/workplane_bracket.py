"""
MashCad CadQuery Import - Example: Workplane API Bracket

This example shows a simple bracket using the CadQuery Workplane API.

Note: 'cq' is pre-defined in the MashCad namespace - do NOT use import.
"""

# Create a simple bracket with box and filleted edges
result = cq.Workplane('XY').box(100, 50, 10).edges('|Z').fillet(2)
