"""Test V2 mit strengerer Winkeltoleranz."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.direct_mesh_converter import DirectMeshConverter, convert_direct_mesh
from meshconverter.mesh_converter_v10 import MeshLoader, LoadStatus, ConversionStatus

print("=" * 60)
print("V2 mit verschiedenen Winkeltoleranzen")
print("=" * 60)

# Mesh laden
load_result = MeshLoader.load('stl/V2.stl', repair=True)
mesh = load_result.mesh

# Teste verschiedene Winkeltoleranzen
tolerances = [1.0, 2.0, 5.0, 10.0, 15.0]

for angle_tol in tolerances:
    print(f"\n--- Winkeltoleranz: {angle_tol}° ---")

    converter = DirectMeshConverter(
        unify_angular_tolerance=angle_tol,
        unify_linear_tolerance=0.1  # Strenger
    )

    result = converter.convert(mesh)

    faces = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))
    print(f"  Faces: {faces}")

    # Exportiere die 5° Version
    if angle_tol == 5.0 and result.solid:
        from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone

        writer = STEPControl_Writer()
        writer.Transfer(result.solid, STEPControl_AsIs)
        writer.Write('step_output/V2_strict.step')
        print(f"  → Exportiert als V2_strict.step")
