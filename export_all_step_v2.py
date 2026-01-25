"""Exportiert alle STL-Dateien zu STEP - mit intelligenter Unify-Entscheidung."""
from loguru import logger
import sys
import os

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.hybrid_mesh_converter import HybridMeshConverter
from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, LoadStatus, ConversionStatus
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

# Alle STL-Dateien mit spezifischen Einstellungen
# Format: (filepath, use_unify, description)
stl_files = [
    # Basis-Dateien - UnifySameDomain hilft hier
    ('stl/rechteck.stl', True, "Einfaches Rechteck"),
    ('stl/V1.stl', True, "V1 mit Zylindern"),
    ('stl/V2.stl', True, "V2 mit kleinen Zylindern"),
    # Komplexe Dateien
    ('stl/housing_V4.STL', True, "Housing mit Zylindern"),
    ('stl/Bohradapter (1).stl', True, "Bohradapter"),
    ('stl/Dragon_Mount (2).stl', True, "Dragon Mount"),
    # MGN12H: KEIN UnifySameDomain - zerstört Features!
    ('stl/MGN12H_X_Carriage_Lite (1).stl', False, "MGN12H - komplex"),
    ('stl/Ewald_block v10.stl', True, "Ewald Block"),
    ('stl/Beacon_RevH_Module.stl', True, "Beacon Module"),
]

# Output-Ordner sicherstellen
os.makedirs('step_output', exist_ok=True)

print("=" * 70)
print("ALLE STL → STEP EXPORT V2 (intelligentes Unify)")
print("=" * 70)

results = []

for stl_file, use_unify, description in stl_files:
    if not os.path.exists(stl_file):
        print(f"\n{stl_file}: NICHT GEFUNDEN")
        continue

    basename = os.path.splitext(os.path.basename(stl_file))[0]
    safe_name = basename.replace(' ', '_').replace('(', '').replace(')', '')
    step_file = f'step_output/{safe_name}.step'

    size_kb = os.path.getsize(stl_file) / 1024
    unify_str = "MIT" if use_unify else "OHNE"
    print(f"\n--- {basename} ({size_kb:.0f} KB) - {unify_str} Unify ---")

    try:
        load_result = MeshLoader.load(stl_file, repair=True)
        if load_result.status == LoadStatus.FAILED:
            print(f"  ✗ Laden fehlgeschlagen")
            continue

        # Wähle Converter basierend auf Unify-Einstellung
        if use_unify:
            # HybridConverter mit Zylinder-Erkennung und Unify
            converter = HybridMeshConverter(
                unify_linear_tolerance=0.5,
                unify_angular_tolerance=1.0  # 1° streng
            )
            result = converter.convert(load_result.mesh)
        else:
            # DirectConverter OHNE Unify
            converter = DirectMeshConverter(
                unify_faces=False
            )
            result = converter.convert(load_result.mesh)

        status_str = result.status.name
        cylinders = result.stats.get('cylinders_detected', 0)
        faces = result.stats.get('faces_after_unify', result.stats.get('faces_created', '?'))

        print(f"  Status: {status_str}")
        if use_unify:
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
                    'cylinders': cylinders if use_unify else '-',
                    'unify': use_unify,
                    'step': step_file,
                    'success': True
                })
            else:
                print(f"  ✗ STEP-Export fehlgeschlagen")
                results.append({'file': basename, 'status': 'EXPORT_FAILED', 'success': False})
        else:
            print(f"  ✗ Kein Solid erstellt")
            results.append({'file': basename, 'status': status_str, 'success': False})

    except Exception as e:
        print(f"  ✗ FEHLER: {e}")
        import traceback
        traceback.print_exc()
        results.append({'file': basename, 'status': 'ERROR', 'success': False})

print("\n" + "=" * 70)
print("ZUSAMMENFASSUNG V2")
print("=" * 70)

success_count = sum(1 for r in results if r.get('success', False))
print(f"\n{success_count}/{len(results)} erfolgreich exportiert\n")

for r in results:
    icon = "✓" if r.get('success', False) else "✗"
    faces = r.get('faces', '-')
    cyls = r.get('cylinders', '-')
    unify = "Unify" if r.get('unify', False) else "Raw"
    step = os.path.basename(r.get('step', '-')) if r.get('step') else 'FEHLER'
    print(f"  {icon} {r['file']}: {faces} Faces ({unify}) → {step}")
