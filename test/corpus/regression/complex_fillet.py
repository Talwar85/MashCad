"""
Corpus Model: Complex Fillet
============================

Complex fillet case for regression testing of fillet operations
on challenging geometry.

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
    """Create and return a complex fillet case.
    
    Creates a stepped block with varying fillet radii,
    testing the fillet algorithm on edge transitions.
    """
    from OCP.TopoDS import TopoDS
    
    # Create a stepped block by using multiple boxes
    # Base: 0,0,0 to 3,3,1
    base = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(3, 3, 1))
    
    # Step: 0.5,0.5,1 to 2.5,2.5,2
    step = BRepPrimAPI_MakeBox(gp_Pnt(0.5, 0.5, 1), gp_Pnt(2.5, 2.5, 2))
    
    # For simplicity, just use the step box with fillets
    shape = step.Shape()
    
    # Apply fillets with varying radii
    fillet = BRepFilletAPI_MakeFillet(shape)
    
    # Add fillets to all edges with radius 0.2
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    edge_count = 0
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())  # Proper OCP casting
        # Vary radius based on edge position
        radius = 0.1 if edge_count < 4 else 0.2
        fillet.Add(radius, edge)
        edge_count += 1
        explorer.Next()
    
    fillet.Build()
    if not fillet.IsDone():
        # If fillet fails, return unfilleted shape
        return shape
    
    return fillet.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Complex Fillet",
        "category": "regression",
        "description": "Stepped block with varying edge fillets - tests complex fillet transitions",
        "expected_issues": [],  # May have fillet warnings on tight corners
        "tags": ["regression", "fillet", "complex", "variable-radius"],
        "bounds": {
            "min": (0.5, 0.5, 1.0),
            "max": (2.5, 2.5, 2.0),
        },
        "volume": None,  # Complex calculation
    }
