"""Test PerfectConverter with V1.stl"""
import sys
sys.path.insert(0, 'c:/LiteCad')

import pyvista as pv
from meshconverter import PerfectConverter, convert_perfect

def test_perfect_converter():
    """Test PerfectConverter with V1.stl"""

    # Lade STL
    print("Lade stl/V1.stl...")
    mesh = pv.read('stl/V1.stl')
    print(f"  Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

    # Converter
    converter = PerfectConverter()

    def on_progress(update):
        print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")
        if update.detail:
            print(f"  -> {update.detail}")

    # Convert
    print("\nKonvertiere...")
    result = converter.convert_async(mesh, on_progress)

    print(f"\n=== Ergebnis ===")
    print(f"Success: {result.success}")
    print(f"Status: {result.status.value if result.status else 'N/A'}")
    print(f"Message: {result.message}")
    print(f"Face-Count: {result.face_count}")

    if result.solid:
        print(f"Solid: {result.solid}")

    return result

if __name__ == "__main__":
    test_perfect_converter()
