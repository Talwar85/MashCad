"""
Konvertiere alle Test-STL-Dateien zu STEP und analysiere die Ergebnisse.
"""
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from loguru import logger
import sys
import glob

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.trimmed_cylinder_converter import TrimmedCylinderConverter
from meshconverter.final_mesh_converter import FinalMeshConverter

from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.Interface import Interface_Static

os.makedirs('step', exist_ok=True)

# Finde alle STL-Dateien
stl_files = glob.glob('stl/*.stl') + glob.glob('stl/*.STL')
print(f"Gefundene STL-Dateien: {len(stl_files)}")
for f in stl_files:
    print(f"  - {f}")

results = []

# Konverter
trimmed_converter = TrimmedCylinderConverter()
final_converter = FinalMeshConverter(preserve_cylinders=True)
solid_converter = FinalMeshConverter(preserve_cylinders=False)

def count_step_entities(filepath):
    """Zählt Entities im STEP-File."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        return {
            'CYLINDRICAL_SURFACE': content.count('CYLINDRICAL_SURFACE'),
            'PLANE': content.count('PLANE('),
            'B_SPLINE_SURFACE': content.count('B_SPLINE_SURFACE'),
            'SPHERICAL_SURFACE': content.count('SPHERICAL_SURFACE'),
            'total_lines': len(content.split('\n'))
        }
    except:
        return {}

print("\n" + "=" * 80)
print("KONVERTIERUNG")
print("=" * 80)

for stl_path in stl_files:
    basename = os.path.splitext(os.path.basename(stl_path))[0]
    print(f"\n{'='*60}")
    print(f"STL: {basename}")
    print('='*60)

    # Lade Mesh
    load_result = MeshLoader.load(stl_path, repair=True)
    if load_result.mesh is None:
        print("  FEHLER: Konnte nicht laden")
        continue

    mesh = load_result.mesh
    print(f"  Mesh: {mesh.n_points} Vertices, {mesh.n_cells} Faces")

    result_info = {
        'name': basename,
        'mesh_faces': mesh.n_cells,
        'conversions': {}
    }

    # 1. Trimmed Converter
    print("\n  [1] Trimmed Converter...")
    result = trimmed_converter.convert(mesh)
    if result.shape is not None:
        step_path = f"step/{basename}_trimmed.step"
        writer = STEPControl_Writer()
        Interface_Static.SetCVal_s("write.step.schema", "AP214")
        writer.Transfer(result.shape, STEPControl_AsIs)
        writer.Write(step_path)

        entities = count_step_entities(step_path)
        result_info['conversions']['trimmed'] = {
            'status': result.status,
            'is_solid': result.is_solid,
            'cylindrical': result.cylindrical_surfaces,
            'step_entities': entities
        }
        print(f"      Status: {result.status}, Solid: {result.is_solid}")
        print(f"      CYLINDRICAL_SURFACE: {result.cylindrical_surfaces}")
        print(f"      -> {step_path}")

    # 2. Final Converter (Cylinder Mode)
    print("\n  [2] Final Converter (Cylinder Mode)...")
    result = final_converter.convert(mesh)
    if result.shape is not None:
        step_path = f"step/{basename}_cylinders.step"
        writer = STEPControl_Writer()
        writer.Transfer(result.shape, STEPControl_AsIs)
        writer.Write(step_path)

        entities = count_step_entities(step_path)
        result_info['conversions']['cylinders'] = {
            'status': result.status,
            'is_solid': result.is_solid,
            'cylindrical': result.cylindrical_surfaces,
            'step_entities': entities
        }
        print(f"      Status: {result.status}, Solid: {result.is_solid}")
        print(f"      CYLINDRICAL_SURFACE: {result.cylindrical_surfaces}")
        print(f"      -> {step_path}")

    # 3. Final Converter (Solid Mode)
    print("\n  [3] Final Converter (Solid Mode)...")
    result = solid_converter.convert(mesh)
    if result.shape is not None:
        step_path = f"step/{basename}_solid.step"
        writer = STEPControl_Writer()
        writer.Transfer(result.shape, STEPControl_AsIs)
        writer.Write(step_path)

        entities = count_step_entities(step_path)
        result_info['conversions']['solid'] = {
            'status': result.status,
            'is_solid': result.is_solid,
            'cylindrical': result.cylindrical_surfaces,
            'step_entities': entities
        }
        print(f"      Status: {result.status}, Solid: {result.is_solid}")
        print(f"      CYLINDRICAL_SURFACE: {result.cylindrical_surfaces}")
        print(f"      -> {step_path}")

    results.append(result_info)

# Zusammenfassung
print("\n" + "=" * 80)
print("ZUSAMMENFASSUNG")
print("=" * 80)

print(f"\n{'Datei':<40} {'Trimmed':<15} {'Cylinders':<15} {'Solid':<15}")
print("-" * 85)

for r in results:
    name = r['name'][:38]

    def fmt(conv_name):
        if conv_name in r['conversions']:
            c = r['conversions'][conv_name]
            cyl = c.get('cylindrical', 0)
            solid = 'S' if c.get('is_solid', False) else '-'
            return f"{cyl} CYL {solid}"
        return "N/A"

    print(f"{name:<40} {fmt('trimmed'):<15} {fmt('cylinders'):<15} {fmt('solid'):<15}")

print("\nLegende: X CYL = Anzahl CYLINDRICAL_SURFACE, S = ist Solid, - = kein Solid")

print("\n" + "=" * 80)
print("STEP-DATEIEN")
print("=" * 80)
step_files = glob.glob('step/*.step')
for f in sorted(step_files):
    entities = count_step_entities(f)
    cyl = entities.get('CYLINDRICAL_SURFACE', 0)
    plane = entities.get('PLANE', 0)
    print(f"  {os.path.basename(f):<45} CYL:{cyl:<3} PLANE:{plane}")
