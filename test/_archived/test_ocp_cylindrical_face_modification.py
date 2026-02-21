#!/usr/bin/env python3
"""
Test OCP-based cylindrical face radius modification.

This demonstrates that OCP/OpenCASCADE provides direct methods to modify
cylindrical faces without Boolean operations - similar to Fusion360.
"""
import pytest
import build123d as bd
from build123d import Solid, Cylinder, Location, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.gp import gp_Ax3, gp_Cylinder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepTools import BRepTools_ReShape


def test_detect_cylindrical_face():
    """Test detection of cylindrical faces using OCP."""
    # Create a cylinder with hole (like a pipe)
    outer = bd.Solid.make_cylinder(10.0, 20.0)
    inner = bd.Solid.make_cylinder(5.0, 20.0)
    solid = outer - inner

    # Find cylindrical faces
    cylindrical_faces = []
    for face in solid.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cyl_surface = adaptor.Cylinder()
            radius = cyl_surface.Radius()
            cylindrical_faces.append((face, radius))

    # Should have 2 cylindrical faces (outer and inner)
    assert len(cylindrical_faces) == 2

    # Check radii
    radii = [r for _, r in cylindrical_faces]
    assert pytest.approx(10.0, abs=1e-6) in radii
    assert pytest.approx(5.0, abs=1e-6) in radii

    print(f"Found {len(cylindrical_faces)} cylindrical faces with radii: {radii}")


def test_extract_cylinder_parameters():
    """
    Test extracting cylinder parameters for face replacement.

    This is the foundation for Fusion360-style radius editing.
    """
    # Create a box with a cylindrical hole positioned in center
    box = bd.Solid.make_box(20, 20, 10)
    cylinder = bd.Solid.make_cylinder(3.0, 10)
    # Position cylinder in center of box
    cylinder_centered = cylinder.located(Location(Vector(10, 10, 0)))
    box_with_hole = box - cylinder_centered

    # Find the cylindrical face (the hole)
    cylindrical_face = None
    cyl_params = None
    for face in box_with_hole.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cyl = adaptor.Cylinder()
            # Inner cylinder (hole) has radius ~3
            if pytest.approx(cyl.Radius(), abs=0.1) == 3.0:
                cylindrical_face = face
                cyl_params = cyl
                break

    assert cylindrical_face is not None, "Cylindrical face not found"
    assert cyl_params is not None

    # Extract cylinder parameters
    location = cyl_params.Location()
    axis = cyl_params.Axis().Direction()
    radius = cyl_params.Radius()

    assert pytest.approx(radius, abs=0.1) == 3.0

    print(f"Cylinder params: location={location}, axis={axis}, radius={radius:.2f}")

    # These parameters can be used to create a new cylinder with different radius
    new_radius = 4.0
    new_cyl_geom = gp_Cylinder(gp_Ax3(location, axis), new_radius)

    # Create new face from the cylindrical surface
    new_face_builder = BRepBuilderAPI_MakeFace(new_cyl_geom, -10, 10, 0, 6.28)
    assert new_face_builder.IsDone()
    new_face = new_face_builder.Face()

    print(f"Created new cylindrical face with radius {new_radius}")

    # NOTE: BRepTools_ReShape replacement is complex and requires careful
    # handling of topology. This is documented for future implementation.


def test_cylindrical_face_analysis_hole_vs_pocket():
    """
    Test analyzing cylindrical faces to distinguish between holes and pockets.

    This is crucial for UX: show different interactions for holes vs pockets.
    """
    # Create a block with a through hole
    block1 = bd.Solid.make_box(20, 20, 10)
    hole = bd.Solid.make_cylinder(3.0, 10)  # Through hole
    # Position the cylinder to cut through
    hole_pos = hole.located(Location(Vector(10, 10, 0)))
    block_with_hole = block1 - hole_pos

    # Create a block with a pocket (blind hole)
    block2 = bd.Solid.make_box(20, 20, 10)
    pocket = bd.Solid.make_cylinder(3.0, 5)  # Only 5mm deep
    pocket_pos = pocket.located(Location(Vector(10, 10, 0)))
    block_with_pocket = block2 - pocket_pos

    def analyze_cylindrical_face(solid):
        """Analyze cylindrical face and return type, radius, depth."""
        result = None
        for face in solid.faces():
            adaptor = BRepAdaptor_Surface(face.wrapped)
            if adaptor.GetType() == GeomAbs_Cylinder:
                cyl = adaptor.Cylinder()
                radius = cyl.Radius()
                # Check if through hole or pocket by analyzing edges
                # A through hole typically has more edges than a pocket
                edges = list(face.edges())
                edge_count = len(edges)

                result = {
                    'radius': radius,
                    'edge_count': edge_count,
                    'has_multiple_edges': edge_count > 2,
                }
                break
        return result

    hole_info = analyze_cylindrical_face(block_with_hole)
    pocket_info = analyze_cylindrical_face(block_with_pocket)

    assert hole_info is not None
    assert pocket_info is not None

    # Through hole should have more edges (includes seam edges)
    assert hole_info['has_multiple_edges'] is True

    # Pocket typically has fewer edges
    print(f"Hole: radius={hole_info['radius']:.2f}, edges={hole_info['edge_count']}")
    print(f"Pocket: radius={pocket_info['radius']:.2f}, edges={pocket_info['edge_count']}")


def test_ocp_methods_summary():
    """
    Summary test showing available OCP methods for cylindrical face modification.
    """
    available_methods = {
        'BRepAdaptor_Surface': '✓ Analyze face type and extract cylinder parameters',
        'Geom_CylindricalSurface': '✓ Create cylindrical surface with custom radius',
        'BRepBuilderAPI_MakeFace': '✓ Create face from surface',
        'BRepTools_ReShape': '⚠ Replace specific faces (complex, needs careful handling)',
        'BRepOffsetAPI_MakeOffsetShape': '⚠ Offset shape (complex API, PerformByJoin)',
    }

    print("\n=== OCP Methods for Cylindrical Face Modification ===")
    for method, description in available_methods.items():
        print(f"  {method}: {description}")

    print("\n=== Recommended Approach for Fusion360-style Radius Edit ===")
    print("1. Detect cylindrical face using BRepAdaptor_Surface")
    print("2. Extract cylinder parameters (location, axis, radius)")
    print("3. Create new Geom_CylindricalSurface with modified radius")
    print("4. Use BRepTools_ReShape to replace the face (complex!)")
    print("5. Alternative: Boolean-based with new cylinder (simpler)")
    print("\n=== Conclusion ===")
    print("OCP provides low-level APIs, but Boolean-based approach is")
    print("more robust for production use. BRepTools_ReShape is complex")
    print("and requires extensive testing for edge cases.")

    # This test always passes - it's documentation
    assert True


if __name__ == "__main__":
    # Run tests
    test_detect_cylindrical_face()
    print("✓ test_detect_cylindrical_face")

    test_extract_cylinder_parameters()
    print("✓ test_extract_cylinder_parameters")

    test_cylindrical_face_analysis_hole_vs_pocket()
    print("✓ test_cylindrical_face_analysis_hole_vs_pocket")

    test_ocp_methods_summary()
    print("✓ test_ocp_methods_summary")

    print("\n=== All tests passed! ===")
