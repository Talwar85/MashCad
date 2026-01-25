"""
STL zu STEP Konvertierung - Zuverlässige Version mit DirectMeshConverter.

Dieser Ansatz funktioniert zuverlässig:
1. Mesh zu BREP (trianguliert, wasserdicht)
2. UnifySameDomain für Face-Merging
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

# STL-Dateien zum Konvertieren
stl_files = [
    ('stl/V1.stl', 'step_output/V1_direct.step'),
    ('stl/V2.stl', 'step_output/V2_direct.step'),
    ('stl/MGN12H_X_Carriage_Lite (1).stl', 'step_output/MGN12H_direct.step'),
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
        print(f"   [FEHLER] Laden fehlgeschlagen: {e}")
        continue

    # 2. Direct Konvertierung
    print("\n2. Konvertiere zu BREP...")
    try:
        converter = DirectMeshConverter(
            sewing_tolerance=1e-6,
            unify_faces=True,
            unify_linear_tolerance=0.1,  # 0.1mm
            unify_angular_tolerance=0.5   # 0.5 Grad
        )

        result = converter.convert(mesh)

        print(f"   Status: {result.status.name}")
        print(f"   Faces erstellt: {result.stats.get('faces_created', '?')}")
        print(f"   Faces nach Unify: {result.stats.get('faces_after_unify', '?')}")
        print(f"   Valid: {result.stats.get('is_valid', '?')}")

        if result.solid is None:
            print("   [FEHLER] Kein Solid erstellt")
            continue

    except Exception as e:
        import traceback
        print(f"   [FEHLER] Konvertierung fehlgeschlagen: {e}")
        traceback.print_exc()
        continue

    # 3. Exportiere STEP
    print("\n3. Exportiere STEP...")
    try:
        writer = STEPControl_Writer()
        writer.Transfer(result.solid, STEPControl_AsIs)
        status = writer.Write(step_path)

        if status == IFSelect_RetDone:
            size = os.path.getsize(step_path) / 1024
            print(f"   ✓ {step_path} ({size:.0f} KB)")
        else:
            print(f"   [FEHLER] STEP-Export fehlgeschlagen")
    except Exception as e:
        print(f"   [FEHLER] Export fehlgeschlagen: {e}")

print(f"\n{'='*60}")
print("FERTIG")
print('='*60)
