"""
Corpus Model: Extrude with Hole
================================

Extruded rectangular profile with a circular hole.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir


def create_model() -> TopoDS_Shape:
    """Create and return an extruded profile with a through hole.
    
    Creates a rectangular block (extruded profile) with a cylindrical
    through hole in the center.
    """
    # Create rectangular block (simulating extruded profile): 0,0,0 to 3,2,1
    block = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(3, 2, 1))
    
    # Create cylindrical hole through the center
    hole_axis = gp_Ax2(gp_Pnt(1.5, 1, 0), gp_Dir(0, 0, 1))
    hole = BRepPrimAPI_MakeCylinder(hole_axis, 0.4, 1.0)
    
    # Cut the hole through the block
    cut = BRepAlgoAPI_Cut(block.Shape(), hole.Shape())
    
    if not cut.IsDone():
        raise RuntimeError("Boolean cut failed")
    
    return cut.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    import math
    return {
        "name": "Extrude with Hole",
        "category": "features",
        "description": "Extruded rectangular profile with central through hole",
        "expected_issues": [],
        "tags": ["feature", "extrude", "hole", "through-hole"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (3.0, 2.0, 1.0),
        },
        "volume": 6.0 - math.pi * 0.4**2 * 1.0,  # Block minus cylinder
    }
