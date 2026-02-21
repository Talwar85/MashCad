"""Test CurrentConverter with V1.stl"""
import sys
sys.path.insert(0, 'c:/LiteCad')

import pyvista as pv
from meshconverter import CurrentConverter, CurrentMode, convert_v10

def test_current_converter():
    """Test CurrentConverter with V1.stl - both modes"""

    # Lade STL
    print("Lade stl/V1.stl...")
    mesh = pv.read('stl/V1.stl')
    print(f"  Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

    # Test V10 Mode
    print("\n=== Test V10 Mode ===")
    converter_v10 = CurrentConverter(mode=CurrentMode.V10)

    def on_progress(update):
        print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")
        if update.detail:
            print(f"  → {update.detail}")

    result_v10 = converter_v10.convert_async(mesh, on_progress)

    print(f"\n=== V10 Ergebnis ===")
    print(f"Success: {result_v10.success}")
    print(f"Status: {result_v10.status.value if result_v10.status else 'N/A'}")
    print(f"Message: {result_v10.message}")
    print(f"Face-Count: {result_v10.face_count}")

    # Test Final Mode
    print("\n=== Test Final Mode ===")
    converter_final = CurrentConverter(mode=CurrentMode.FINAL)

    result_final = converter_final.convert_async(mesh, on_progress)

    print(f"\n=== Final Ergebnis ===")
    print(f"Success: {result_final.success}")
    print(f"Status: {result_final.status.value if result_final.status else 'N/A'}")
    print(f"Message: {result_final.message}")
    print(f"Face-Count: {result_final.face_count}")

    return result_v10, result_final

if __name__ == "__main__":
    test_current_converter()
