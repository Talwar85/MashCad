"""Test Smart Unification V4 gegen aktuelle brep_optimizer."""
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.brep_optimizer import optimize_brep
from phase2.smart_unification_v4 import optimize_brep_v4

stl_files = [
    'stl/V1.stl',
    'stl/V2.stl',
    'stl/MGN12H_X_Carriage_Lite (1).stl',
]

print("=" * 80)
print("VERGLEICH: brep_optimizer vs. Smart Unification V4")
print("=" * 80)

results = []

for stl_path in stl_files:
    if not os.path.exists(stl_path):
        continue

    name = os.path.basename(stl_path)
    print(f"\n{'='*60}")
    print(f"Datei: {name}")
    print('='*60)

    # Lade und konvertiere
    load_result = MeshLoader.load(stl_path, repair=True)
    converter = DirectMeshConverter(unify_faces=False)
    result = converter.convert(load_result.mesh)

    if result.solid is None:
        print("  FEHLER: Kein Solid erstellt")
        continue

    brep_faces = result.stats.get('faces_created', 0)
    print(f"\nBREP Basis: {brep_faces} Faces")

    # Test 1: Aktuelle brep_optimizer
    print("\n--- brep_optimizer (aktuell) ---")
    opt1, stats1 = optimize_brep(result.solid)
    faces1 = stats1.get('faces_after', brep_faces)
    reduction1 = 100 * (brep_faces - faces1) / brep_faces if brep_faces > 0 else 0
    print(f"  Ergebnis: {faces1} Faces ({reduction1:.1f}% Reduktion)")

    # Test 2: Smart Unification V4
    print("\n--- Smart Unification V4 ---")
    opt2, stats2 = optimize_brep_v4(result.solid)
    faces2 = stats2.get('faces_after', brep_faces)
    reduction2 = stats2.get('reduction_percent', 0)
    valid2 = stats2.get('valid', False)
    print(f"  Ergebnis: {faces2} Faces ({reduction2:.1f}% Reduktion), Valid={valid2}")

    results.append({
        'name': name,
        'base': brep_faces,
        'v1_faces': faces1,
        'v1_reduction': reduction1,
        'v4_faces': faces2,
        'v4_reduction': reduction2,
        'v4_valid': valid2
    })

# Zusammenfassung
print("\n" + "=" * 80)
print("ZUSAMMENFASSUNG")
print("=" * 80)
print(f"\n{'Datei':<35} {'Basis':<8} {'V1 (aktuell)':<15} {'V4 (neu)':<15} {'Valid'}")
print("-" * 80)
for r in results:
    v1_str = f"{r['v1_faces']} ({r['v1_reduction']:.0f}%)"
    v4_str = f"{r['v4_faces']} ({r['v4_reduction']:.0f}%)"
    print(f"{r['name']:<35} {r['base']:<8} {v1_str:<15} {v4_str:<15} {r['v4_valid']}")
