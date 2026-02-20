"""
Corpus Model: Manifold Edge Case
================================

Edge case for manifold validation testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir


def create_model() -> TopoDS_Shape:
    """Create and return a manifold edge case.
    
    Creates two cubes sharing exactly one edge (touching at edge).
    This is a valid manifold but can be challenging for some algorithms.
    """
    # Create first cube: 0,0,0 to 1,1,1
    box1 = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(1, 1, 1))
    
    # Create second cube: 1,0,0 to 2,1,1 (sharing face at x=1)
    # This creates two solids sharing a face - still manifold
    box2 = BRepPrimAPI_MakeBox(gp_Pnt(1, 0, 0), gp_Pnt(2, 1, 1))
    
    # Fuse them together - should create a single manifold solid
    fuse = BRepAlgoAPI_Fuse(box1.Shape(), box2.Shape())
    
    if not fuse.IsDone():
        raise RuntimeError("Boolean fuse failed")
    
    return fuse.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Manifold Edge Case",
        "category": "regression",
        "description": "Two cubes fused at a face - tests manifold validation on shared boundaries",
        "expected_issues": [],
        "tags": ["regression", "manifold", "shared-face", "boundary"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (2.0, 1.0, 1.0),
        },
        "volume": 2.0,  # Two unit cubes
    }
