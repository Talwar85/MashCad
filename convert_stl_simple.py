"""
STL zu STEP - Einfache Version OHNE BRepOptimizer.

Nur DirectMeshConverter mit eingebautem UnifySameDomain.
"""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.direct_mesh_converter import DirectMeshConverter
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE

# STL-Dateien
stl_files = [
    ('stl/V1.stl', 'step_output/V1_simple.step'),
    ('stl/V2.stl', 'step_output/V2_simple.step'),
    ('stl/MGN12H_X_Carriage_Lite (1).stl', 'step_output/MGN12H_simple.step'),
]

os.makedirs('step_output', exist_ok=True)

for stl_path, step_path in stl_files:
    if not os.path.exists(stl_path):
        print(f"\n[SKIP] {stl_path} nicht gefunden")
        continue

    print(f"\n{'='*60}")
    print(f"Konvertiere: {stl_path}")
    print('='*60)

    # 1. Lade STL
    print("\n1. Lade STL...")
    try:
        load_result = MeshLoader.load(stl_path, repair=True)
        mesh = load_result.mesh
        print(f"   {mesh.n_points} Punkte, {mesh.n_cells} Faces")
    except Exception as e:
        print(f"   [FEHLER] {e}")
        continue

    # 2. Konvertiere - NUR DirectMeshConverter, KEIN BRepOptimizer
    print("\n2. Konvertiere zu BREP (nur DirectMeshConverter)...")
    try:
        converter = DirectMeshConverter(
            sewing_tolerance=1e-6,
            unify_faces=True,
            unify_linear_tolerance=0.1,
            unify_angular_tolerance=0.5
        )
        result = converter.convert(mesh)

        print(f"   Status: {result.status.name}")

        if result.solid is None:
            print("   [FEHLER] Kein Solid")
            continue

        # Zähle Faces
        face_count = 0
        exp = TopExp_Explorer(result.solid, TopAbs_FACE)
        while exp.More():
            face_count += 1
            exp.Next()
        print(f"   Faces: {face_count}")

    except Exception as e:
        import traceback
        print(f"   [FEHLER] {e}")
        traceback.print_exc()
        continue

    # 3. Exportiere
    print("\n3. Exportiere STEP...")
    try:
        writer = STEPControl_Writer()
        writer.Transfer(result.solid, STEPControl_AsIs)
        status = writer.Write(step_path)

        if status == IFSelect_RetDone:
            size = os.path.getsize(step_path) / 1024
            print(f"   ✓ {step_path} ({size:.0f} KB)")
        else:
            print(f"   [FEHLER] Export fehlgeschlagen")
    except Exception as e:
        print(f"   [FEHLER] {e}")

print(f"\n{'='*60}")
print("FERTIG - Bitte in Fusion 360 prüfen")
print('='*60)
