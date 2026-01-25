"""Test V1 mit strengerer linearer Toleranz."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import HybridMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

load_result = MeshLoader.load('stl/V1.stl', repair=True)

# Teste verschiedene lineare Toleranzen
tests = [
    (0.5, 1.0, "standard"),         # Aktuell - kaputt
    (0.1, 1.0, "linear_0.1"),       # Strenger
    (0.01, 1.0, "linear_0.01"),     # Sehr streng
    (0.001, 1.0, "linear_0.001"),   # Ultra streng
]

for lin_tol, ang_tol, name in tests:
    print(f"\n=== Linear={lin_tol}mm, Angular={ang_tol}° ===")

    converter = HybridMeshConverter(
        unify_linear_tolerance=lin_tol,
        unify_angular_tolerance=ang_tol
    )
    result = converter.convert(load_result.mesh)

    faces = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))
    print(f"  Status: {result.status.name}, Faces: {faces}")

    # Exportiere die beste Version
    if lin_tol == 0.01 and result.solid:
        writer = STEPControl_Writer()
        writer.Transfer(result.solid, STEPControl_AsIs)
        writer.Write('step_output/V1_strict_linear.step')
        print(f"  → Exportiert als V1_strict_linear.step")
