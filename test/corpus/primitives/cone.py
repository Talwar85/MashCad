"""
Corpus Model: Unit Cone
=======================

Basic unit cone primitive for export regression testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
import math


def create_model() -> TopoDS_Shape:
    """Create and return a unit cone (base_radius=1, top_radius=0, height=2)."""
    # Create a cone along Z-axis, base radius=1, top radius=0, height=2
    axis = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    cone = BRepPrimAPI_MakeCone(axis, 1.0, 0.0, 2.0)
    return cone.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Unit Cone",
        "category": "primitives",
        "description": "Basic cone (base_radius=1, height=2) for tapered surface export testing",
        "expected_issues": [],
        "tags": ["primitive", "cone", "curved", "apex"],
        "bounds": {
            "min": (-1.0, -1.0, 0.0),
            "max": (1.0, 1.0, 2.0),
        },
        "volume": (1.0 / 3.0) * math.pi * 1.0**2 * 2.0,  # ~2.094
        "surface_area": math.pi * 1.0 * (1.0 + math.sqrt(1.0 + 4.0)) + math.pi * 1.0**2,  # ~10.17
    }
