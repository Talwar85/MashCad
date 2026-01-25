"""
Vergleich: Baseline (DirectMeshConverter + optimize_brep) vs. nur DirectMeshConverter

Ziel: Verstehen was die Baseline leistet und wo Verbesserungspotential ist.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.brep_optimizer import optimize_brep

from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.Interface import Interface_Static

import pyvista as pv


def count_faces(shape):
    count = 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def analyze_surface_types(shape):
    """Analysiert welche Surface-Typen im Shape sind."""
    types = {}
    type_names = {
        0: 'PLANE', 1: 'CYLINDER', 2: 'CONE', 3: 'SPHERE',
        4: 'TORUS', 5: 'BEZIER', 6: 'BSPLINE', 7: 'REVOLUTION',
        8: 'EXTRUSION', 9: 'OFFSET', 10: 'OTHER'
    }

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()
        type_name = type_names.get(surface_type, f'UNKNOWN_{surface_type}')
        types[type_name] = types.get(type_name, 0) + 1
        explorer.Next()
    return types


def export_step(shape, filepath: str, name: str = "Part"):
    """Exportiert Shape als STEP."""
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.product.name", name)
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(filepath)
    return status == 1


def test_baseline(stl_path: str, output_dir: str = "step"):
    """Testet die Baseline-Konvertierung."""

    print(f"\n{'='*60}")
    print(f"Baseline-Test: {stl_path}")
    print(f"{'='*60}")

    if not Path(stl_path).exists():
        print(f"  Datei nicht gefunden!")
        return

    # Output-Verzeichnis
    Path(output_dir).mkdir(exist_ok=True)
    stem = Path(stl_path).stem.replace(" ", "_").replace("(", "").replace(")", "")

    # Mesh laden
    mesh = pv.read(stl_path)
    print(f"\n  Original Mesh: {mesh.n_cells} Faces")

    # DirectMeshConverter
    print(f"\n  [1] DirectMeshConverter...")
    converter = DirectMeshConverter(unify_faces=False)
    result = converter.convert(mesh)

    if result.solid is None:
        print(f"      FEHLER: {result.message}")
        return

    base_faces = count_faces(result.solid)
    base_types = analyze_surface_types(result.solid)
    base_valid = BRepCheck_Analyzer(result.solid).IsValid()

    print(f"      Faces: {base_faces}")
    print(f"      Types: {base_types}")
    print(f"      Valid: {base_valid}")

    # Export ohne Optimierung
    step_raw = f"{output_dir}/{stem}_raw.step"
    if export_step(result.solid, step_raw, stem):
        print(f"      → {step_raw}")

    # optimize_brep
    print(f"\n  [2] optimize_brep...")
    optimized, stats = optimize_brep(result.solid)

    opt_faces = count_faces(optimized)
    opt_types = analyze_surface_types(optimized)
    opt_valid = BRepCheck_Analyzer(optimized).IsValid()

    print(f"      Faces: {opt_faces} (Reduktion: {100*(base_faces-opt_faces)/base_faces:.1f}%)")
    print(f"      Types: {opt_types}")
    print(f"      Valid: {opt_valid}")

    # Export mit Optimierung
    step_opt = f"{output_dir}/{stem}_optimized.step"
    if export_step(optimized, step_opt, stem):
        print(f"      → {step_opt}")

    print(f"\n  === Zusammenfassung ===")
    print(f"  Mesh:       {mesh.n_cells} Triangles")
    print(f"  Raw BREP:   {base_faces} Faces ({base_types})")
    print(f"  Optimized:  {opt_faces} Faces ({opt_types})")
    print(f"  Reduktion:  {100*(mesh.n_cells-opt_faces)/mesh.n_cells:.1f}%")

    return {
        'mesh_faces': mesh.n_cells,
        'raw_faces': base_faces,
        'opt_faces': opt_faces,
        'raw_valid': base_valid,
        'opt_valid': opt_valid
    }


if __name__ == "__main__":
    print("=" * 60)
    print("Baseline Vergleich - DirectMeshConverter + optimize_brep")
    print("=" * 60)

    # Test mit ausgewählten Dateien
    test_files = [
        'stl/V1.stl',
        'stl/V2.stl',
        'stl/MGN12H_X_Carriage_Lite (1).stl',
        'stl/rechteck.stl',
    ]

    results = []
    for stl_file in test_files:
        if Path(stl_file).exists():
            r = test_baseline(stl_file)
            if r:
                results.append((stl_file, r))

    print("\n" + "=" * 60)
    print("GESAMTERGEBNIS")
    print("=" * 60)
    print(f"{'Datei':<30} {'Mesh':>8} {'Raw':>8} {'Opt':>8} {'Red%':>8}")
    print("-" * 60)
    for stl_file, r in results:
        name = Path(stl_file).stem[:28]
        red = 100 * (r['mesh_faces'] - r['opt_faces']) / r['mesh_faces']
        print(f"{name:<30} {r['mesh_faces']:>8} {r['raw_faces']:>8} {r['opt_faces']:>8} {red:>7.1f}%")
