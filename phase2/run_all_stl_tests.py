"""
Konvertiert alle STL-Dateien zu STEP mit NURBS-Optimierung.
"""
import sys
from pathlib import Path

# Add phase2 to path
sys.path.insert(0, str(Path(__file__).parent))

from nurbs_fillet_reducer_v1 import convert_to_step

if __name__ == "__main__":
    print("=" * 60)
    print("NURBS Fillet Reducer - Alle STL-Dateien")
    print("=" * 60)

    stl_dir = Path("stl")
    step_dir = Path("step")
    step_dir.mkdir(exist_ok=True)

    stl_files = list(stl_dir.glob("*.stl"))
    print(f"\nGefunden: {len(stl_files)} STL-Dateien")

    results = []

    for stl_file in stl_files:
        # Erzeuge sauberen Namen ohne Sonderzeichen
        clean_name = stl_file.stem.replace(" ", "_").replace("(", "").replace(")", "")
        step_file = step_dir / f"{clean_name}_nurbs.step"

        try:
            success = convert_to_step(str(stl_file), str(step_file))
            results.append((stl_file.name, step_file.name, success))
        except Exception as e:
            print(f"\n  FEHLER bei {stl_file.name}: {e}")
            results.append((stl_file.name, step_file.name, False))

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG ALLER DATEIEN")
    print("=" * 60)

    success_count = 0
    for stl, step, success in results:
        status = "✓" if success else "✗"
        if success:
            success_count += 1
        print(f"  {status} {stl} → {step}")

    print(f"\n  Erfolgreich: {success_count}/{len(results)}")
