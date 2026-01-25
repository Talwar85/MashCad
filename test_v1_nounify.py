"""Test V1 OHNE UnifySameDomain."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

load_result = MeshLoader.load('stl/V1.stl', repair=True)

print("=== V1 OHNE UnifySameDomain ===")

converter = DirectMeshConverter(unify_faces=False)
result = converter.convert(load_result.mesh)

faces = result.stats.get('faces_created', '?')
print(f"Status: {result.status.name}, Faces: {faces}")

if result.solid:
    writer = STEPControl_Writer()
    writer.Transfer(result.solid, STEPControl_AsIs)
    writer.Write('step_output/V1_nounify.step')
    print(f"Exportiert: step_output/V1_nounify.step")
