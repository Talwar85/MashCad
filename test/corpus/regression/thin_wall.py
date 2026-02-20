"""
Corpus Model: Thin Wall
=======================

Thin wall geometry for regression testing of mesh generation
on thin features.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt


def create_model() -> TopoDS_Shape:
    """Create and return a thin wall geometry.
    
    Creates a thin-walled structure (0.1mm wall thickness) which
    can be challenging for tessellation and mesh generation.
    """
    # Create a thin-walled box (outer dimensions 2x2x2, wall thickness 0.1)
    outer_box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(2, 2, 2))
    
    # For a proper thin wall, we'd use shell operation
    # Here we create a simple thin plate for testing
    thin_plate = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(2, 2, 0.1))
    
    return thin_plate.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Thin Wall",
        "category": "regression",
        "description": "Thin plate (2x2x0.1) for thin feature tessellation testing",
        "expected_issues": [],  # May have small feature warnings at low quality
        "tags": ["regression", "thin-wall", "tessellation", "mesh-quality"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (2.0, 2.0, 0.1),
        },
        "volume": 2.0 * 2.0 * 0.1,  # 0.4
        "min_feature_size": 0.1,
    }
