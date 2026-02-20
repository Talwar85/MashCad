"""
Corpus Model: Unit Cube
=======================

Basic unit cube primitive for export regression testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt


def create_model() -> TopoDS_Shape:
    """Create and return a unit cube (1x1x1)."""
    # Create a unit cube from (0,0,0) to (1,1,1)
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(1, 1, 1))
    return box.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Unit Cube",
        "category": "primitives",
        "description": "Basic unit cube (1x1x1) for baseline export testing",
        "expected_issues": [],
        "tags": ["primitive", "cube", "basic"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (1.0, 1.0, 1.0),
        },
        "volume": 1.0,
        "surface_area": 6.0,
    }
