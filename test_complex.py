"""Test komplexere STL-Dateien."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import convert_hybrid_mesh
from meshconverter.mesh_converter_v10 import ConversionStatus

# Neue Testdateien
test_files = [
    'stl/housing_V4.STL',
    'stl/Bohradapter (1).stl',
    'stl/Dragon_Mount (2).stl',
    'stl/MGN12H_X_Carriage_Lite (1).stl',
    'stl/Ewald_block v10.stl',
    'stl/Beacon_RevH_Module.stl',
]

print("=" * 70)
print("KOMPLEXE STL KONVERTIERUNG")
print("=" * 70)

results = []

for stl_file in test_files:
    if not os.path.exists(stl_file):
        print(f"\n{stl_file}: NICHT GEFUNDEN")
        continue

    size_kb = os.path.getsize(stl_file) / 1024
    print(f"\n--- {os.path.basename(stl_file)} ({size_kb:.0f} KB) ---")

    try:
        result = convert_hybrid_mesh(stl_file)

        status = "SUCCESS" if result.status == ConversionStatus.SUCCESS else result.status.name
        cylinders = result.stats.get('cylinders_detected', 0)
        faces_in = result.stats.get('input_faces', '?')
        faces_out = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))
        free_edges = result.stats.get('free_edges', '?')

        print(f"  Status: {status}")
        print(f"  Input: {faces_in} Dreiecke")
        print(f"  Output: {faces_out} Faces")
        print(f"  Zylinder: {cylinders}")
        print(f"  Free Edges: {free_edges}")

        if result.message:
            print(f"  Message: {result.message}")

        results.append({
            'file': os.path.basename(stl_file),
            'status': status,
            'faces_in': faces_in,
            'faces_out': faces_out,
            'cylinders': cylinders,
            'solid': result.solid
        })

    except Exception as e:
        print(f"  FEHLER: {e}")
        results.append({
            'file': os.path.basename(stl_file),
            'status': 'ERROR',
            'error': str(e)
        })

print("\n" + "=" * 70)
print("ZUSAMMENFASSUNG")
print("=" * 70)

success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
print(f"\n{success_count}/{len(results)} erfolgreich konvertiert")

for r in results:
    status_icon = "✓" if r['status'] == 'SUCCESS' else "✗"
    print(f"  {status_icon} {r['file']}: {r['status']}")
