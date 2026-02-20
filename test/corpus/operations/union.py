"""
Corpus Model: Boolean Union
===========================

Union of two overlapping cubes for boolean operation export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt


def create_model() -> TopoDS_Shape:
    """Create and return a union of two overlapping cubes."""
    # Create first cube: 0,0,0 to 1,1,1
    box1 = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(1, 1, 1))
    
    # Create second cube: 0.5,0.5,0.5 to 1.5,1.5,1.5 (overlapping)
    box2 = BRepPrimAPI_MakeBox(gp_Pnt(0.5, 0.5, 0.5), gp_Pnt(1.5, 1.5, 1.5))
    
    # Perform union
    fuse = BRepAlgoAPI_Fuse(box1.Shape(), box2.Shape())
    
    if not fuse.IsDone():
        raise RuntimeError("Boolean union failed")
    
    return fuse.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Boolean Union",
        "category": "operations",
        "description": "Union of two overlapping cubes - tests boolean operation result export",
        "expected_issues": [],
        "tags": ["boolean", "union", "overlap"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (1.5, 1.5, 1.5),
        },
        "volume": 1.0 + 1.0 - 0.125,  # Two cubes minus overlap (0.5^3)
    }
