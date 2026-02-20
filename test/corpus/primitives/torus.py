"""
Corpus Model: Unit Torus
========================

Basic unit torus primitive for export regression testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeTorus
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
import math


def create_model() -> TopoDS_Shape:
    """Create and return a unit torus (major_radius=2, minor_radius=0.5)."""
    # Create a torus along Z-axis, major radius=2, minor radius=0.5
    axis = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    torus = BRepPrimAPI_MakeTorus(axis, 2.0, 0.5)
    return torus.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    major_radius = 2.0
    minor_radius = 0.5
    return {
        "name": "Unit Torus",
        "category": "primitives",
        "description": "Basic torus (major_radius=2, minor_radius=0.5) for complex curved surface testing",
        "expected_issues": [],
        "tags": ["primitive", "torus", "curved", "hole"],
        "bounds": {
            "min": (-2.5, -2.5, -0.5),
            "max": (2.5, 2.5, 0.5),
        },
        "volume": 2.0 * math.pi**2 * major_radius * minor_radius**2,  # ~9.87
        "surface_area": 4.0 * math.pi**2 * major_radius * minor_radius,  # ~39.48
    }
