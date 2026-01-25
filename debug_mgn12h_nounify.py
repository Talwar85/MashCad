"""Debug MGN12H_X_Carriage OHNE UnifySameDomain."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)

print("=== Test: OHNE UnifySameDomain ===")

converter = DirectMeshConverter(
    unify_faces=False  # Kein Merging!
)
result = converter.convert(load_result.mesh)

faces = result.stats.get('faces_created', '?')
print(f"Status: {result.status.name}")
print(f"Faces: {faces}")

if result.solid:
    writer = STEPControl_Writer()
    writer.Transfer(result.solid, STEPControl_AsIs)
    writer.Write('step_output/MGN12H_X_Carriage_Lite_1_nounify.step')
    print(f"→ Exportiert als MGN12H_X_Carriage_Lite_1_nounify.step")
