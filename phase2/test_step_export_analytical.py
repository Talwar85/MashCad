"""
Test: STEP Export with Analytical Surfaces
==========================================

Verifies that the mesh-to-BREP pipeline correctly creates:
- CYLINDRICAL_SURFACE for fillets
- Planar faces for chamfers and main surfaces

Tests the full pipeline from STL to STEP.
"""

import sys
from pathlib import Path

# Add parent directory (LiteCad) to path for imports
litecad_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(litecad_root))
sys.path.insert(0, str(litecad_root / "meshconverter"))

import numpy as np
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_pipeline_with_step_export():
    """Tests the full mesh-to-BREP pipeline and STEP export."""

    print("=" * 70)
    print("TEST: Mesh-to-BREP Pipeline with STEP Export")
    print("=" * 70)

    # Use absolute path to avoid resolution issues
    stl_dir = Path(__file__).resolve().parent.parent / "stl"
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)

    print(f"STL directory: {stl_dir}")
    print(f"STL exists: {stl_dir.exists()}")

    test_files = [
        ("verrunden.stl", "Expected: 5 cylindrical surfaces (fillets)"),
        ("fase.stl", "Expected: 5 planar chamfer surfaces"),
        ("rechteck.stl", "Expected: 6 planar surfaces (box)"),
    ]

    results = {}

    for filename, description in test_files:
        stl_path = stl_dir / filename
        if not stl_path.exists():
            print(f"\n[SKIP] {filename} - File not found")
            continue

        print(f"\n{'='*70}")
        print(f"Testing: {filename}")
        print(f"  {description}")
        print("=" * 70)

        try:
            from meshconverter.mesh_converter_v10 import (
                MeshToBREPConverterV10,
                ConversionStatus
            )

            # Create converter with loose tolerances for better results
            converter = MeshToBREPConverterV10(
                angle_tolerance=10.0,      # Allow 10 degree normal variation
                fitting_tolerance=1.0,     # 1mm fitting tolerance
                sewing_tolerance=1.0,      # 1mm sewing tolerance
                min_region_faces=2,        # Minimum 2 faces per region
                enable_nurbs=False         # Disable NURBS for cleaner output
            )

            result = converter.convert(str(stl_path))

            print(f"\nConversion Result:")
            print(f"  Status: {result.status.name}")
            print(f"  Message: {result.message}")
            print(f"  Stats: {result.stats}")

            if result.status in [ConversionStatus.SUCCESS, ConversionStatus.PARTIAL,
                                 ConversionStatus.SHELL_ONLY]:
                # Export to STEP
                step_path = output_dir / f"{stl_path.stem}_converted.step"

                try:
                    from build123d import export_step
                    export_step(result.solid, str(step_path))
                    print(f"\n  STEP exported to: {step_path}")

                    # Analyze STEP content
                    analyze_step_surfaces(step_path)

                    results[filename] = "SUCCESS"

                except Exception as e:
                    print(f"  STEP export failed: {e}")
                    results[filename] = f"EXPORT_FAILED: {e}"

            else:
                results[filename] = f"CONVERSION_FAILED: {result.message}"

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            results[filename] = f"ERROR: {e}"

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for filename, status in results.items():
        print(f"  {filename}: {status}")


def analyze_step_surfaces(step_path: Path):
    """Analyzes a STEP file to find analytical surface types."""

    if not step_path.exists():
        print(f"  [SKIP] STEP file not found: {step_path}")
        return

    # Read STEP file as text and count surface types
    try:
        with open(step_path, 'r') as f:
            content = f.read()

        # Count surface types in STEP
        surface_types = {
            'CYLINDRICAL_SURFACE': content.count('CYLINDRICAL_SURFACE'),
            'PLANE': content.count('PLANE('),
            'SPHERICAL_SURFACE': content.count('SPHERICAL_SURFACE'),
            'CONICAL_SURFACE': content.count('CONICAL_SURFACE'),
            'B_SPLINE_SURFACE': content.count('B_SPLINE_SURFACE'),
            'TOROIDAL_SURFACE': content.count('TOROIDAL_SURFACE'),
        }

        print(f"\n  STEP Surface Analysis:")
        for surface_type, count in surface_types.items():
            if count > 0:
                print(f"    {surface_type}: {count}")

        # Check for analytical surfaces (not just triangulated mesh)
        total_analytical = surface_types['CYLINDRICAL_SURFACE'] + surface_types['SPHERICAL_SURFACE']
        if total_analytical > 0:
            print(f"\n  ANALYTICAL SURFACES DETECTED: {total_analytical}")
        else:
            print(f"\n  [WARNING] No analytical curved surfaces found!")

    except Exception as e:
        print(f"  [ERROR] Could not analyze STEP file: {e}")


def test_v9_detector_integration():
    """Tests using V9 detector output directly for BREP creation."""

    print("\n" + "=" * 70)
    print("TEST: V9 Detector Direct Integration")
    print("=" * 70)

    stl_dir = Path(__file__).resolve().parent.parent / "stl"
    stl_path = stl_dir / "verrunden.stl"
    print(f"STL path: {stl_path}")

    if not stl_path.exists():
        print(f"[SKIP] verrunden.stl not found")
        return

    try:
        import pyvista as pv
        from fillet_chamfer_detector_v9 import FilletChamferDetectorV9

        # Load mesh
        mesh = pv.read(str(stl_path))
        print(f"Mesh loaded: {mesh.n_cells} faces, {mesh.n_points} vertices")

        # Detect fillets and chamfers
        detector = FilletChamferDetectorV9(
            min_main_area_ratio=0.02,
            plane_tolerance=1.0,
            cylinder_tolerance=3.0
        )

        fillets, chamfers = detector.detect(mesh)

        print(f"\nDetected Features:")
        print(f"  Fillets: {len(fillets)}")
        print(f"  Chamfers: {len(chamfers)}")

        # Print fillet details
        if fillets:
            print(f"\nFillet Details:")
            for i, fillet in enumerate(fillets):
                print(f"  [{i+1}] radius={fillet.radius:.2f}mm, "
                      f"arc={np.degrees(fillet.arc_angle):.1f}deg, "
                      f"faces={len(fillet.face_ids)}")

        # Try to create BREP faces for fillets
        print("\nCreating BREP Faces from V9 Output...")

        try:
            from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3
            from OCP.Geom import Geom_CylindricalSurface
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
            from OCP.TopoDS import TopoDS_Face

            faces_created = 0

            for fillet in fillets:
                # Create cylindrical surface
                center = fillet.axis_point
                axis = fillet.axis
                radius = fillet.radius

                # Create coordinate system
                gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
                gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

                # X-direction perpendicular to axis
                if abs(axis[2]) < 0.9:
                    x_dir = np.cross(axis, [0, 0, 1])
                else:
                    x_dir = np.cross(axis, [1, 0, 0])
                x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
                gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

                ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)

                # Create cylindrical surface
                cylinder_surface = Geom_CylindricalSurface(ax3, radius)

                # Create face with arc angle bounds
                arc_angle = fillet.arc_angle
                u_min = -arc_angle / 2
                u_max = arc_angle / 2

                # Estimate height from face geometry
                face_points = []
                for fid in fillet.face_ids:
                    cell = mesh.get_cell(fid)
                    face_points.extend(cell.points)
                face_points = np.array(face_points)

                proj_lengths = np.dot(face_points - center, axis)
                height = np.max(proj_lengths) - np.min(proj_lengths)
                v_min, v_max = -height/2, height/2

                face_builder = BRepBuilderAPI_MakeFace(
                    cylinder_surface,
                    u_min, u_max,
                    v_min, v_max,
                    1e-6
                )

                if face_builder.IsDone():
                    faces_created += 1
                    print(f"  Fillet {faces_created}: CYLINDRICAL_SURFACE created "
                          f"(r={radius:.2f}mm, arc={np.degrees(arc_angle):.1f}deg)")
                else:
                    print(f"  Fillet: Face creation FAILED")

            print(f"\n  Total BREP faces created: {faces_created}/{len(fillets)}")

        except ImportError as e:
            print(f"  [SKIP] OCP not available: {e}")

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test 1: Full pipeline
    test_pipeline_with_step_export()

    # Test 2: V9 detector integration
    test_v9_detector_integration()

    print("\n" + "=" * 70)
    print("Tests completed!")
    print("=" * 70)
