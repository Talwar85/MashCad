"""
STL zu STEP Konvertierung mit Smart Mesh Converter
==================================================

Verwendet den SmartMeshConverter der erkannte Primitive
durch echte analytische Surfaces ersetzt.
"""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.smart_mesh_converter import SmartMeshConverter
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

# STL-Dateien zum Konvertieren
stl_files = [
    ('stl/V1.stl', 'step_output/V1_smart.step'),
    ('stl/V2.stl', 'step_output/V2_smart.step'),
    ('stl/MGN12H_X_Carriage_Lite (1).stl', 'step_output/MGN12H_smart.step'),
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

    # 2. Smart Konvertierung
    print("\n2. Smart Mesh Konvertierung...")
    try:
        converter = SmartMeshConverter(
            angle_threshold=12.0,
            min_primitive_faces=12,
            cylinder_tolerance=0.5,
            sphere_tolerance=0.5,
            sewing_tolerance=0.1
        )

        # replace_primitives=False: Sicherer Modus, UnifySameDomain optimiert
        # replace_primitives=True: Experimentell, kann Lücken verursachen
        result = converter.convert(mesh, replace_primitives=False)

        print(f"\n   Status: {result.status}")
        print(f"   Statistiken:")
        print(f"     - Mesh Faces: {result.stats.get('mesh_faces', '?')}")
        print(f"     - Zylinder erkannt: {result.stats.get('cylinders_detected', 0)}")
        print(f"     - Kugeln erkannt: {result.stats.get('spheres_detected', 0)}")
        print(f"     - Zylinder-Faces ersetzt: {result.stats.get('cylinder_faces_replaced', 0)}")
        print(f"     - Kugel-Faces ersetzt: {result.stats.get('sphere_faces_replaced', 0)}")
        print(f"     - BREP Faces: {result.stats.get('brep_faces', '?')}")

        if result.solid is None:
            print("   [FEHLER] Keine Solid erstellt")
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
