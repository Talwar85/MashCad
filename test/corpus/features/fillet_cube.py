"""
Corpus Model: Fillet Cube
=========================

Cube with edge fillets for fillet feature export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE


def create_model() -> TopoDS_Shape:
    """Create and return a cube with filleted edges.
    
    Creates a unit cube with all 12 edges filleted with radius 0.1.
    """
    from OCP.TopoDS import TopoDS
    
    # Create unit cube
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(1, 1, 1))
    shape = box.Shape()
    
    # Create fillet on all edges
    fillet = BRepFilletAPI_MakeFillet(shape)
    
    # Explore all edges and add them to fillet
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())  # Proper OCP casting
        fillet.Add(0.1, edge)  # 0.1 radius fillet
        explorer.Next()
    
    fillet.Build()
    if not fillet.IsDone():
        raise RuntimeError("Fillet operation failed")
    
    return fillet.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Fillet Cube",
        "category": "features",
        "description": "Unit cube with all edges filleted (radius=0.1)",
        "expected_issues": [],
        "tags": ["feature", "fillet", "blend", "rounded"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (1.0, 1.0, 1.0),
        },
        "volume": None,  # Complex calculation due to fillets
    }
