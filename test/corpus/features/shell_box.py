"""
Corpus Model: Shell Box
=======================

Hollowed box (shell feature) for shell feature export testing.

Author: MashCAD Team
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from typing import Dict, Any
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopTools import TopTools_ListOfShape


def create_model() -> TopoDS_Shape:
    """Create and return a hollowed box (shell).
    
    Creates a 2x2x2 box with the top face removed and walls thickened
    inward by 0.1 to create a hollow shell.
    """
    # Create a 2x2x2 box
    box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(2, 2, 2))
    shape = box.Shape()
    
    # Find the top face (Z=2) to remove
    faces_to_remove = TopTools_ListOfShape()
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    
    # We'll use a simple approach: remove the last face found
    # In practice, you'd identify the face by its geometry
    face_count = 0
    last_face = None
    while explorer.More():
        last_face = explorer.Current()
        face_count += 1
        explorer.Next()
    
    if last_face:
        faces_to_remove.Append(last_face)
    
    # Create thick solid (shell) with wall thickness 0.1
    # Negative offset = inward
    shell = BRepOffsetAPI_MakeThickSolid(shape, faces_to_remove, -0.1)
    
    shell.Build()
    if not shell.IsDone():
        raise RuntimeError("Shell operation failed")
    
    return shell.Shape()


def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Shell Box",
        "category": "features",
        "description": "Hollowed 2x2x2 box with open top (shell thickness=0.1)",
        "expected_issues": [],
        "tags": ["feature", "shell", "hollow", "thin-wall"],
        "bounds": {
            "min": (0.0, 0.0, 0.0),
            "max": (2.0, 2.0, 2.0),
        },
        "volume": None,  # Complex calculation due to shell
    }
