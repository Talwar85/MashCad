"""
Test edge_based_fillet_detector mit den neuen Testdaten:
- verrunden.stl (5 Fillets)
- fase.stl (5 Chamfers)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pyvista as pv
from edge_based_fillet_detector import EdgeBasedFeatureDetector


def test_file(stl_path: str, expected_fillets: int, expected_chamfers: int):
    """Testet eine STL-Datei."""
    print("=" * 60)
    print(f"TEST: {Path(stl_path).name}")
    print(f"Erwartet: {expected_fillets} Fillets, {expected_chamfers} Chamfers")
    print("=" * 60)

    if not Path(stl_path).exists():
        print(f"  FEHLER: Datei nicht gefunden!")
        return False

    mesh = pv.read(stl_path)
    print(f"Mesh: {mesh.n_cells} Faces, {mesh.n_points} Vertices")

    detector = EdgeBasedFeatureDetector()
    fillets, chamfers = detector.detect(mesh)

    print(f"\nErgebnis:")
    print(f"  Fillets gefunden: {len(fillets)}")
    print(f"  Chamfers gefunden: {len(chamfers)}")

    if fillets:
        print("\nFillet-Details:")
        for i, f in enumerate(fillets):
            print(f"  [{i+1}] Radius={f.radius:.2f}mm, Faces={len(f.face_ids)}, Confidence={f.confidence:.2f}")

    if chamfers:
        print("\nChamfer-Details:")
        for i, c in enumerate(chamfers):
            print(f"  [{i+1}] Width={c.width:.2f}mm, Angle={c.angle:.1f} deg, Faces={len(c.face_ids)}")

    # Bewertung
    fillet_ok = len(fillets) == expected_fillets
    chamfer_ok = len(chamfers) == expected_chamfers

    print(f"\n{'✓' if fillet_ok else '✗'} Fillets: {len(fillets)}/{expected_fillets}")
    print(f"{'✓' if chamfer_ok else '✗'} Chamfers: {len(chamfers)}/{expected_chamfers}")

    return fillet_ok and chamfer_ok


if __name__ == "__main__":
    stl_dir = Path(__file__).parent.parent / "stl"

    results = []

    # Test verrunden.stl (5 Fillets erwartet)
    r1 = test_file(str(stl_dir / "verrunden.stl"), expected_fillets=5, expected_chamfers=0)
    results.append(("verrunden.stl", r1))

    print("\n")

    # Test fase.stl (5 Chamfers erwartet)
    r2 = test_file(str(stl_dir / "fase.stl"), expected_fillets=0, expected_chamfers=5)
    results.append(("fase.stl", r2))

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    for name, passed in results:
        print(f"  {'✓' if passed else '✗'} {name}")
