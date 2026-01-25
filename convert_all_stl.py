"""Konvertiert alle STL-Dateien zu optimierten STEP-Dateien."""
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

# STL-Dateien zum Konvertieren
stl_files = [
    ('stl/MGN12H_X_Carriage_Lite (1).stl', 'step_output/MGN12H_optimized.step'),
    ('stl/V1.stl', 'step_output/V1_optimized.step'),
    ('stl/V2.stl', 'step_output/V2_optimized.step'),
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
        print(f"   {load_result.mesh.n_points} Punkte, {load_result.mesh.n_cells} Faces")
    except Exception as e:
        print(f"   [FEHLER] Laden fehlgeschlagen: {e}")
        continue

    # 2. Konvertiere zu BREP
    print("\n2. Konvertiere zu BREP...")
    try:
        converter = DirectMeshConverter(unify_faces=False)
        result = converter.convert(load_result.mesh)
        print(f"   Status: {result.status.name}")
        print(f"   BREP Faces: {result.stats.get('faces_created', '?')}")
    except Exception as e:
        print(f"   [FEHLER] Konvertierung fehlgeschlagen: {e}")
        continue

    if not result.solid:
        print("   [FEHLER] Kein Solid erstellt")
        continue

    # 3. Optimiere BREP
    print("\n3. Optimiere BREP...")
    try:
        optimized, opt_stats = optimize_brep(result.solid)

        faces_before = opt_stats.get('faces_before', 0)
        faces_after = opt_stats.get('faces_after', 0)
        reduction = faces_before - faces_after
        reduction_pct = 100 * reduction / faces_before if faces_before > 0 else 0

        print(f"   Faces: {faces_before} → {faces_after} ({reduction_pct:.1f}% Reduktion)")
        print(f"   Zylinder erkannt: {opt_stats.get('cylinders_detected', 0)}")
        print(f"   Kugeln erkannt: {opt_stats.get('spheres_detected', 0)}")
    except Exception as e:
        print(f"   [FEHLER] Optimierung fehlgeschlagen: {e}")
        optimized = result.solid

    # 4. Exportiere STEP
    print("\n4. Exportiere STEP...")
    try:
        writer = STEPControl_Writer()
        writer.Transfer(optimized, STEPControl_AsIs)
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
