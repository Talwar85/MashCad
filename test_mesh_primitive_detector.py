"""Test Mesh-basierte Primitiv-Erkennung."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.mesh_primitive_detector import MeshPrimitiveDetector

# Test mit allen STL-Dateien
test_files = [
    ('stl/V1.stl', 'V1'),
    ('stl/V2.stl', 'V2'),
    ('stl/MGN12H_X_Carriage_Lite (1).stl', 'MGN12H'),
]

for stl_path, name in test_files:
    if not os.path.exists(stl_path):
        print(f"\n[SKIP] {stl_path} nicht gefunden")
        continue

    print(f"\n{'='*60}")
    print(f"Testing Mesh Primitive Detector: {name}")
    print('='*60)

    # 1. Lade Mesh
    print("\n1. Lade Mesh...")
    try:
        load_result = MeshLoader.load(stl_path, repair=True)
        mesh = load_result.mesh
        print(f"   {mesh.n_points} Punkte, {mesh.n_cells} Faces")
    except Exception as e:
        print(f"   [FEHLER] {e}")
        continue

    # 2. Primitiv-Erkennung
    print("\n2. Mesh-basierte Primitiv-Erkennung...")
    try:
        detector = MeshPrimitiveDetector(
            angle_threshold=12.0,       # 12° für Normalen-Clustering
            min_region_faces=12,        # Min 12 Faces pro Region
            cylinder_tolerance=0.5,     # 0.5mm Toleranz
            sphere_tolerance=0.5,       # 0.5mm Toleranz
            min_inlier_ratio=0.85       # 85% Inlier
        )

        cylinders, spheres = detector.detect_from_mesh(mesh)

        print(f"\n   Ergebnisse:")
        print(f"   - Zylinder gefunden: {len(cylinders)}")
        print(f"   - Kugeln gefunden: {len(spheres)}")

        if cylinders:
            print("\n   Zylinder-Details:")
            for i, cyl in enumerate(cylinders[:15]):  # Max 15 anzeigen
                print(f"     {i+1}. R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm, "
                      f"{len(cyl.face_indices)} Faces, Conf={cyl.confidence:.2f}")
            if len(cylinders) > 15:
                print(f"     ... und {len(cylinders) - 15} weitere")

        if spheres:
            print("\n   Kugel-Details:")
            for i, sph in enumerate(spheres[:10]):  # Max 10 anzeigen
                print(f"     {i+1}. R={sph.radius:.2f}mm, "
                      f"{len(sph.face_indices)} Faces, Conf={sph.confidence:.2f}")
            if len(spheres) > 10:
                print(f"     ... und {len(spheres) - 10} weitere")

    except Exception as e:
        import traceback
        print(f"   [FEHLER] {e}")
        traceback.print_exc()

print(f"\n{'='*60}")
print("FERTIG")
print('='*60)
