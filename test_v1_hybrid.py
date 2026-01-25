"""Test V1 mit HybridMeshConverter."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import convert_hybrid_mesh
from meshconverter.mesh_converter_v10 import ConversionStatus

print("=" * 60)
print("V1 mit HybridMeshConverter")
print("=" * 60)

result = convert_hybrid_mesh('stl/V1.stl')

print(f"Status: {result.status.name}")
print(f"Stats: {result.stats}")

if result.status == ConversionStatus.SUCCESS and result.solid:
    # STEP Export
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone

    writer = STEPControl_Writer()
    writer.Transfer(result.solid, STEPControl_AsIs)
    status = writer.Write('step_output/V1_1deg.step')

    if status == IFSelect_RetDone:
        print(f"\nExportiert: step_output/V1_1deg.step")
        print(f"Faces: {result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))}")
