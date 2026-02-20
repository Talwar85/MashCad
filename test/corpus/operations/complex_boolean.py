"""
Corpus Model: Complex Boolean
=============================

Multi-body boolean operation for complex export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCP.TopTools import TopTools_ListOfShape


def create_model() -> TopoDS_Shape:
    """Create and return a complex multi-body boolean result.
    
    Creates a base plate with four cylindrical posts and a central hole.
    """
    # Create base plate: 0,0,0 to 4,4,0.5
    base = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(4, 4, 0.5))
    
    # Create four cylindrical posts at corners
    post_positions = [(0.5, 0.5), (0.5, 3.5), (3.5, 0.5), (3.5, 3.5)]
    
    # First post
    axis1 = gp_Ax2(gp_Pnt(post_positions[0][0], post_positions[0][1], 0.5), gp_Dir(0, 0, 1))
    post1 = BRepPrimAPI_MakeCylinder(axis1, 0.3, 1.5)
    
    # Fuse base with first post
    fuse1 = BRepAlgoAPI_Fuse(base.Shape(), post1.Shape())
    if not fuse1.IsDone():
        raise RuntimeError("Boolean fuse 1 failed")
    result = fuse1.Shape()
    
    # Add remaining posts
    for pos in post_positions[1:]:
        axis = gp_Ax2(gp_Pnt(pos[0], pos[1], 0.5), gp_Dir(0, 0, 1))
        post = BRepPrimAPI_MakeCylinder(axis, 0.3, 1.5)
        fuse = BRepAlgoAPI_Fuse(result, post.Shape())
        if not fuse.IsDone():
            raise RuntimeError(f"Boolean fuse failed at position {pos}")
        result = fuse.Shape()
    
    # Create central hole
    center_axis = gp_Ax2(gp_Pnt(2, 2, 0), gp_Dir(0, 0, 1))
    center_hole = BRepPrimAPI_MakeCylinder(center_axis, 0.5, 2.0)
    
    # Cut central hole
    cut = BRepAlgoAPI_Cut(result, center_hole.Shape())
    if not cut.IsDone():
        raise RuntimeError("Boolean cut failed")
    
    return cut.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Complex Boolean",
        "category": "operations",
        "description": "Base plate with four posts and central hole - tests multi-step boolean operations",
        "expected_issues": [],
        "tags": ["boolean", "complex", "multi-body", "fuse", "cut"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (4.0, 4.0, 2.0),
        },
        "volume": None,  # Complex calculation
    }
