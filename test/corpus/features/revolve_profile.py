"""
Corpus Model: Revolve Profile
=============================

Revolved profile for revolve feature export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Wire
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Circ, gp_Pln
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
import math


def create_model() -> TopoDS_Shape:
    """Create and return a revolved profile.
    
    Creates a simple vase-like shape by revolving a profile
    consisting of a polyline around the Z-axis.
    """
    # Create a profile (L-shape) to revolve
    # Points: (1,0,0) -> (2,0,0) -> (2,0,3) -> (1.5,0,3) -> (1.5,0,1) -> (1,0,1) -> back to start
    
    p1 = gp_Pnt(1, 0, 0)
    p2 = gp_Pnt(2, 0, 0)
    p3 = gp_Pnt(2, 0, 3)
    p4 = gp_Pnt(1.5, 0, 3)
    p5 = gp_Pnt(1.5, 0, 1)
    p6 = gp_Pnt(1, 0, 1)
    
    # Create edges
    edge1 = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
    edge2 = BRepBuilderAPI_MakeEdge(p2, p3).Edge()
    edge3 = BRepBuilderAPI_MakeEdge(p3, p4).Edge()
    edge4 = BRepBuilderAPI_MakeEdge(p4, p5).Edge()
    edge5 = BRepBuilderAPI_MakeEdge(p5, p6).Edge()
    edge6 = BRepBuilderAPI_MakeEdge(p6, p1).Edge()
    
    # Create wire from edges
    wire_maker = BRepBuilderAPI_MakeWire()
    wire_maker.Add(edge1)
    wire_maker.Add(edge2)
    wire_maker.Add(edge3)
    wire_maker.Add(edge4)
    wire_maker.Add(edge5)
    wire_maker.Add(edge6)
    
    if not wire_maker.IsDone():
        raise RuntimeError("Wire creation failed")
    
    wire = wire_maker.Wire()
    
    # Create face from wire
    face = BRepBuilderAPI_MakeFace(wire).Face()
    
    # Revolve around Z-axis (360 degrees)
    axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    revol = BRepPrimAPI_MakeRevol(face, axis, 2 * math.pi)
    
    if not revol.IsDone():
        raise RuntimeError("Revolve operation failed")
    
    return revol.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Revolve Profile",
        "category": "features",
        "description": "Vase-like shape created by revolving an L-profile around Z-axis",
        "expected_issues": [],
        "tags": ["feature", "revolve", "lathe", "axisymmetric"],
        "bounds": {
            "min": (-2.0, -2.0, 0.0),
            "max": (2.0, 2.0, 3.0),
        },
        "volume": None,  # Complex calculation
    }
