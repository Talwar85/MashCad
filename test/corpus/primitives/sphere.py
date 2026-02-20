"""
Corpus Model: Unit Sphere
=========================

Basic unit sphere primitive for export regression testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt
import math


def create_model() -> TopoDS_Shape:
    """Create and return a unit sphere (radius=1)."""
    # Create a unit sphere centered at origin with radius 1
    sphere = BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, 0), 1.0)
    return sphere.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Unit Sphere",
        "category": "primitives",
        "description": "Basic unit sphere (radius=1) for curved surface export testing",
        "expected_issues": [],
        "tags": ["primitive", "sphere", "curved"],
        "bounds": {
            "min": (-1.0, -1.0, -1.0),
            "max": (1.0, 1.0, 1.0),
        },
        "volume": (4.0 / 3.0) * math.pi,  # ~4.189
        "surface_area": 4.0 * math.pi,     # ~12.566
    }
