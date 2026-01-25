"""Exportiert alle STL-Dateien zu STEP."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import convert_hybrid_mesh
from meshconverter.direct_mesh_converter import convert_direct_mesh
from meshconverter.mesh_converter_v10 import ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

# Alle STL-Dateien
stl_files = [
    # Basis-Dateien
    'stl/rechteck.stl',
    'stl/V1.stl',
    'stl/V2.stl',
    # Komplexe Dateien
    'stl/housing_V4.STL',
    'stl/Bohradapter (1).stl',
    'stl/Dragon_Mount (2).stl',
    'stl/MGN12H_X_Carriage_Lite (1).stl',
    'stl/Ewald_block v10.stl',
    'stl/Beacon_RevH_Module.stl',
]

# Output-Ordner sicherstellen
os.makedirs('step_output', exist_ok=True)

print("=" * 70)
print("ALLE STL → STEP EXPORT")
print("=" * 70)

results = []

for stl_file in stl_files:
    if not os.path.exists(stl_file):
        print(f"\n{stl_file}: NICHT GEFUNDEN")
        continue

    basename = os.path.splitext(os.path.basename(stl_file))[0]
    # Sonderzeichen entfernen für Dateinamen
    safe_name = basename.replace(' ', '_').replace('(', '').replace(')', '')
    step_file = f'step_output/{safe_name}.step'

    size_kb = os.path.getsize(stl_file) / 1024
    print(f"\n--- {basename} ({size_kb:.0f} KB) ---")

    try:
        # Hybrid-Converter für alle (erkennt Zylinder wo möglich)
        result = convert_hybrid_mesh(stl_file)

        status_str = result.status.name
        cylinders = result.stats.get('cylinders_detected', 0)
        faces = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))

        print(f"  Status: {status_str}")
        print(f"  Zylinder: {cylinders}")
        print(f"  Faces: {faces}")

        if result.solid:
            writer = STEPControl_Writer()
            writer.Transfer(result.solid, STEPControl_AsIs)
            write_status = writer.Write(step_file)

            if write_status == IFSelect_RetDone:
                print(f"  → Exportiert: {step_file}")
                results.append({
                    'file': basename,
                    'status': status_str,
                    'faces': faces,
                    'cylinders': cylinders,
                    'step': step_file,
                    'success': True
                })
            else:
                print(f"  ✗ STEP-Export fehlgeschlagen")
                results.append({
                    'file': basename,
                    'status': 'EXPORT_FAILED',
                    'success': False
                })
        else:
            print(f"  ✗ Kein Solid erstellt")
            results.append({
                'file': basename,
                'status': status_str,
                'success': False
            })

    except Exception as e:
        print(f"  ✗ FEHLER: {e}")
        results.append({
            'file': basename,
            'status': 'ERROR',
            'error': str(e),
            'success': False
        })

print("\n" + "=" * 70)
print("ZUSAMMENFASSUNG")
print("=" * 70)

success_count = sum(1 for r in results if r.get('success', False))
print(f"\n{success_count}/{len(results)} erfolgreich exportiert\n")

for r in results:
    icon = "✓" if r.get('success', False) else "✗"
    faces = r.get('faces', '-')
    cyls = r.get('cylinders', '-')
    step = r.get('step', '-')
    print(f"  {icon} {r['file']}: {faces} Faces, {cyls} Zyl → {os.path.basename(step) if step != '-' else 'FEHLER'}")
