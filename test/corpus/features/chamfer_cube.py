"""
Corpus Model: Chamfer Cube
==========================

Cube with edge chamfers for chamfer feature export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE


def create_model() -> TopoDS_Shape:
    """Create and return a cube with chamfered edges.
    
    Creates a unit cube with all 12 edges chamfered with distance 0.1.
    """
    # Create unit cube
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(1, 1, 1))
    shape = box.Shape()
    
    # Create chamfer on all edges
    chamfer = BRepFilletAPI_MakeChamfer(shape)
    
    # Explore all edges and add them to chamfer
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = explorer.Current()
        chamfer.Add(0.1, edge)  # 0.1 distance chamfer
        explorer.Next()
    
    chamfer.Build()
    if not chamfer.IsDone():
        raise RuntimeError("Chamfer operation failed")
    
    return chamfer.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Chamfer Cube",
        "category": "features",
        "description": "Unit cube with all edges chamfered (distance=0.1)",
        "expected_issues": [],
        "tags": ["feature", "chamfer", "bevel", "angled"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (1.0, 1.0, 1.0),
        },
        "volume": None,  # Complex calculation due to chamfers
    }
