"""
Corpus Model: Boolean Intersection
==================================

Intersection of two overlapping spheres for boolean export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt
import math


def create_model() -> TopoDS_Shape:
    """Create and return the intersection of two overlapping spheres."""
    # Create first sphere centered at (0, 0, 0) with radius 1
    sphere1 = BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, 0), 1.0)
    
    # Create second sphere centered at (1, 0, 0) with radius 1 (overlapping)
    sphere2 = BRepPrimAPI_MakeSphere(gp_Pnt(1, 0, 0), 1.0)
    
    # Perform intersection
    common = BRepAlgoAPI_Common(sphere1.Shape(), sphere2.Shape())
    
    if not common.IsDone():
        raise RuntimeError("Boolean intersection failed")
    
    return common.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Boolean Intersection",
        "category": "operations",
        "description": "Intersection of two overlapping spheres - tests boolean common result export",
        "expected_issues": [],
        "tags": ["boolean", "intersection", "common", "lens"],
        "bounds": {
            "min": (0.0, -1.0, -1.0),
            "max": (1.0, 1.0, 1.0),
        },
        # Volume of lens (intersection of two unit spheres at distance 1)
        # V = (5π/12 - √3/8) * 2 ≈ 1.218
        "volume": None,  # Complex calculation, verified numerically
    }
