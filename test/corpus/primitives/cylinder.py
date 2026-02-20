"""
Corpus Model: Unit Cylinder
===========================

Basic unit cylinder primitive for export regression testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
import math


def create_model() -> TopoDS_Shape:
    """Create and return a unit cylinder (radius=1, height=2)."""
    # Create a cylinder along Z-axis, radius=1, height=2
    axis = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    cylinder = BRepPrimAPI_MakeCylinder(axis, 1.0, 2.0)
    return cylinder.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Unit Cylinder",
        "category": "primitives",
        "description": "Basic cylinder (radius=1, height=2) for mixed surface export testing",
        "expected_issues": [],
        "tags": ["primitive", "cylinder", "curved", "flat"],
        "bounds": {
            "min": (-1.0, -1.0, 0.0),
            "max": (1.0, 1.0, 2.0),
        },
        "volume": 2.0 * math.pi,  # ~6.283
        "surface_area": 2.0 * math.pi * 1.0 * 2.0 + 2.0 * math.pi * 1.0**2,  # ~18.85
    }
