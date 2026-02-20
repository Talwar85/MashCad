"""
Corpus Model: Boolean Difference
================================

Cube minus sphere for boolean difference export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt
import math


def create_model() -> TopoDS_Shape:
    """Create and return a cube with a spherical hole (cube minus sphere)."""
    # Create cube: 0,0,0 to 2,2,2
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(2, 2, 2))
    
    # Create sphere centered in the cube with radius 0.8
    sphere = BRepPrimAPI_MakeSphere(gp_Pnt(1, 1, 1), 0.8)
    
    # Perform difference (cube - sphere)
    cut = BRepAlgoAPI_Cut(box.Shape(), sphere.Shape())
    
    if not cut.IsDone():
        raise RuntimeError("Boolean difference failed")
    
    return cut.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Boolean Difference",
        "category": "operations",
        "description": "Cube with spherical cavity - tests boolean cut result export",
        "expected_issues": [],
        "tags": ["boolean", "difference", "cut", "cavity"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (2.0, 2.0, 2.0),
        },
        "volume": 8.0 - (4.0 / 3.0) * math.pi * 0.8**3,  # Cube minus sphere
    }
