"""Test BREP Optimizer auf MGN12H."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.brep_optimizer import optimize_brep
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

print("=" * 60)
print("BREP OPTIMIZER TEST - MGN12H")
print("=" * 60)

# 1. Lade und konvertiere STL
print("\n1. Lade STL...")
load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)
print(f"   {load_result.mesh.n_points} Punkte, {load_result.mesh.n_cells} Faces")

print("\n2. Konvertiere zu BREP...")
converter = DirectMeshConverter(unify_faces=False)
result = converter.convert(load_result.mesh)
print(f"   Status: {result.status.name}")
print(f"   BREP Faces: {result.stats.get('faces_created', '?')}")

if result.solid:
    # 2. Optimiere BREP
    print("\n3. Optimiere BREP...")
    optimized, opt_stats = optimize_brep(result.solid)

    print(f"\n   Ergebnis:")
    print(f"   - Faces vorher: {opt_stats.get('faces_before', '?')}")
    print(f"   - Faces nachher: {opt_stats.get('faces_after', '?')}")
    print(f"   - Cluster gefunden: {opt_stats.get('clusters_found', '?')}")
    print(f"   - Planes gemerged: {opt_stats.get('planes_merged', '?')}")
    print(f"   - Zylinder gemerged: {opt_stats.get('cylinders_merged', '?')}")

    reduction = opt_stats.get('faces_before', 0) - opt_stats.get('faces_after', 0)
    if opt_stats.get('faces_before', 0) > 0:
        reduction_pct = 100 * reduction / opt_stats.get('faces_before', 1)
        print(f"   - Reduktion: {reduction} Faces ({reduction_pct:.1f}%)")

    # 3. Exportiere
    print("\n4. Exportiere STEP...")
    step_file = 'step_output/MGN12H_optimized.step'
    writer = STEPControl_Writer()
    writer.Transfer(optimized, STEPControl_AsIs)
    status = writer.Write(step_file)

    if status == IFSelect_RetDone:
        size = os.path.getsize(step_file) / 1024
        print(f"   ✓ {step_file} ({size:.0f} KB)")

print("\n" + "=" * 60)
