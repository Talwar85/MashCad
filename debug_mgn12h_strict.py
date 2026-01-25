"""Debug MGN12H_X_Carriage mit strengeren Toleranzen."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import HybridMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)

# Test verschiedene Toleranz-Kombinationen
tests = [
    # (linear_tol, angular_tol, name)
    (0.5, 1.0, "standard"),      # Aktuell
    (0.1, 1.0, "linear_strict"), # Strenger linear
    (0.01, 0.5, "very_strict"),  # Sehr streng
    (0.001, 0.1, "ultra_strict"), # Ultra streng
]

for lin_tol, ang_tol, name in tests:
    print(f"\n=== Test: {name} (linear={lin_tol}mm, angular={ang_tol}°) ===")

    converter = HybridMeshConverter(
        unify_linear_tolerance=lin_tol,
        unify_angular_tolerance=ang_tol
    )
    result = converter.convert(load_result.mesh)

    faces = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))
    print(f"  Status: {result.status.name}")
    print(f"  Faces: {faces}")

    if result.solid and name == "ultra_strict":
        writer = STEPControl_Writer()
        writer.Transfer(result.solid, STEPControl_AsIs)
        writer.Write(f'step_output/MGN12H_X_Carriage_Lite_1_{name}.step')
        print(f"  → Exportiert als MGN12H_X_Carriage_Lite_1_{name}.step")
