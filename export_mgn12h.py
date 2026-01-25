"""Export MGN12H_X_Carriage ohne UnifySameDomain."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

print("=== MGN12H_X_Carriage Export (ohne UnifySameDomain) ===")

load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)
converter = DirectMeshConverter(unify_faces=False)
result = converter.convert(load_result.mesh)

print(f"Status: {result.status.name}")
print(f"Faces: {result.stats.get('faces_created', '?')}")

if result.solid:
    writer = STEPControl_Writer()
    writer.Transfer(result.solid, STEPControl_AsIs)
    status = writer.Write('step_output/MGN12H_X_Carriage_Lite_1.step')
    if status == IFSelect_RetDone:
        print("Exportiert: step_output/MGN12H_X_Carriage_Lite_1.step")
