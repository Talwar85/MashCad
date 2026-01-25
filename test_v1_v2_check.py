"""Prüfe ob V1 und V2 noch funktionieren."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import convert_hybrid_mesh
from meshconverter.mesh_converter_v10 import ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS

def count_faces_and_bounds(solid):
    """Zählt Faces und ermittelt Bounds."""
    face_count = 0
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        face_count += 1
        exp.Next()
    return face_count

for stl_file, name in [('stl/V1.stl', 'V1'), ('stl/V2.stl', 'V2')]:
    print(f"\n{'='*50}")
    print(f"{name}")
    print('='*50)

    result = convert_hybrid_mesh(stl_file)

    print(f"Status: {result.status.name}")
    print(f"Zylinder: {result.stats.get('cylinders_detected', 0)}")
    print(f"Faces: {result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))}")

    if result.solid:
        actual_faces = count_faces_and_bounds(result.solid)
        print(f"Actual BREP Faces: {actual_faces}")

        # Export
        step_file = f'step_output/{name}.step'
        writer = STEPControl_Writer()
        writer.Transfer(result.solid, STEPControl_AsIs)
        status = writer.Write(step_file)

        if status == IFSelect_RetDone:
            import os
            size = os.path.getsize(step_file) / 1024
            print(f"Export: {step_file} ({size:.0f} KB)")
