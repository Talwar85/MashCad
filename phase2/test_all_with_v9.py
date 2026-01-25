"""
Teste V9 Detector auf allen STL-Dateien.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fillet_chamfer_detector_v9 import FilletChamferDetectorV9
import pyvista as pv


def test_file(stl_path: str):
    """Testet eine STL-Datei."""
    print("=" * 60)
    print(f"TEST: {Path(stl_path).name}")
    print("=" * 60)

    if not Path(stl_path).exists():
        print(f"  FEHLER: Datei nicht gefunden!")
        return

    mesh = pv.read(stl_path)
    print(f"Mesh: {mesh.n_cells} Faces, {mesh.n_points} Vertices")

    detector = FilletChamferDetectorV9(
        min_main_area_ratio=0.02,
        plane_tolerance=1.0,
        cylinder_tolerance=3.0
    )

    fillets, chamfers = detector.detect(mesh)

    print(f"\n=== ERGEBNIS ===")
    print(f"Fillets: {len(fillets)}")
    print(f"Chamfers: {len(chamfers)}")

    if fillets:
        print("\nFillet-Details:")
        for i, f in enumerate(fillets):
            print(f"  [{i+1}] r={f.radius:.2f}mm, arc={f.arc_angle*180/3.14159:.1f}°, {len(f.face_ids)} faces")

    if chamfers:
        print("\nChamfer-Details:")
        for i, c in enumerate(chamfers):
            print(f"  [{i+1}] w={c.width:.2f}mm, {len(c.face_ids)} faces")


if __name__ == "__main__":
    stl_dir = Path(__file__).parent.parent / "stl"

    # Teste alle STL-Dateien
    stl_files = [
        "verrunden.stl",
        "fase.stl",
        "V1.stl",
        "V2.stl",
        "rechteck.stl",
        "MGN12H_X_Carriage_Lite (1).stl"
    ]

    for stl_file in stl_files:
        path = stl_dir / stl_file
        if path.exists():
            test_file(str(path))
            print("\n\n")
