"""Export MGN12H_X_Carriage frisch - ohne UnifySameDomain."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

# Alte Datei löschen falls vorhanden
step_file = 'step_output/MGN12H_X_Carriage_Lite_1.step'
if os.path.exists(step_file):
    os.remove(step_file)
    print(f"Alte Datei gelöscht: {step_file}")

print("\n=== MGN12H_X_Carriage FRISCHER Export ===")

load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)
print(f"STL geladen: {load_result.mesh.n_points} Punkte, {load_result.mesh.n_cells} Faces")

# DirectMeshConverter OHNE UnifySameDomain
converter = DirectMeshConverter(unify_faces=False)
result = converter.convert(load_result.mesh)

print(f"\nKonvertierung:")
print(f"  Status: {result.status.name}")
print(f"  Faces erstellt: {result.stats.get('faces_created', '?')}")
print(f"  Free Edges: {result.stats.get('free_edges', '?')}")
print(f"  Solid valid: {result.stats.get('is_valid', '?')}")

if result.solid:
    print(f"\nSTEP Export...")
    writer = STEPControl_Writer()
    writer.Transfer(result.solid, STEPControl_AsIs)
    status = writer.Write(step_file)

    if status == IFSelect_RetDone:
        file_size = os.path.getsize(step_file) / 1024
        print(f"  ✓ Exportiert: {step_file} ({file_size:.0f} KB)")
    else:
        print(f"  ✗ Export fehlgeschlagen!")
else:
    print("  ✗ Kein Solid erstellt!")
