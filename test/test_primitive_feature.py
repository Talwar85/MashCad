"""PrimitiveFeature Test Suite - Native OCP Verification

Tests für das aktualisierte PrimitiveFeature:
- Box: 6 Faces
- Cylinder: 3 Faces (keine Polygon-Approximation!)
- Sphere: 1 Face
- Cone (Frustum, r_top>0): 3 Faces
- Cone (Pointed, r_top=0): 2 Faces
"""

import build123d as bd
from modeling import Body, Document, PrimitiveFeature


def test_primitive_box_6_faces():
    """PrimitiveFeature Box hat 6 Faces."""
    feat = PrimitiveFeature(
        primitive_type="box",
        length=10,
        width=20,
        height=30
    )

    solid = feat.create_solid()
    faces = list(solid.faces())
    face_count = len(faces)

    print(f"Primitive Box Faces: {face_count}")
    assert face_count == 6, f"Box sollte 6 Faces haben, got {face_count}"
    print("✓ Box Test bestanden!")


def test_primitive_cylinder_3_faces():
    """PrimitiveFeature Cylinder hat 3 Faces (NATIVE OCP!)."""
    feat = PrimitiveFeature(
        primitive_type="cylinder",
        radius=10,
        height=20
    )

    solid = feat.create_solid()
    faces = list(solid.faces())
    face_count = len(faces)

    print(f"Primitive Cylinder Faces: {face_count}")
    assert face_count == 3, f"Cylinder sollte 3 Faces haben, got {face_count}"
    print("✓ Cylinder Test bestanden!")


def test_primitive_sphere_1_face():
    """PrimitiveFeature Sphere hat 1 Face."""
    feat = PrimitiveFeature(
        primitive_type="sphere",
        radius=10
    )

    solid = feat.create_solid()
    faces = list(solid.faces())
    face_count = len(faces)

    print(f"Primitive Sphere Faces: {face_count}")
    assert face_count == 1, f"Sphere sollte 1 Face haben, got {face_count}"
    print("✓ Sphere Test bestanden!")


def test_primitive_cone_frustum_3_faces():
    """PrimitiveFeature Cone (Frustum, r_top>0) hat 3 Faces."""
    feat = PrimitiveFeature(
        primitive_type="cone",
        bottom_radius=10,
        top_radius=5,
        height=20
    )

    solid = feat.create_solid()
    faces = list(solid.faces())
    face_count = len(faces)

    print(f"Primitive Cone (Frustum) Faces: {face_count}")
    assert face_count == 3, f"Frustum sollte 3 Faces haben, got {face_count}"
    print("✓ Cone Frustum Test bestanden!")


def test_primitive_cone_pointed_2_faces():
    """PrimitiveFeature Cone (Pointed, r_top=0) hat 2 Faces."""
    feat = PrimitiveFeature(
        primitive_type="cone",
        bottom_radius=10,
        top_radius=0,  # Spitzer Kegel
        height=20
    )

    solid = feat.create_solid()
    faces = list(solid.faces())
    face_count = len(faces)

    print(f"Primitive Cone (Pointed) Faces: {face_count}")
    assert face_count == 2, f"Spitzer Kegel sollte 2 Faces haben, got {face_count}"
    print("✓ Cone Pointed Test bestanden!")


def test_primitive_vs_native_build123d():
    """PrimitiveFeature = native build123d Methoden."""
    # PrimitiveFeature Cylinder
    feat = PrimitiveFeature(
        primitive_type="cylinder",
        radius=10,
        height=20
    )
    feat_solid = feat.create_solid()
    feat_faces = len(list(feat_solid.faces()))

    # Native build123d Cylinder
    native_solid = bd.Solid.make_cylinder(10, 20)
    native_faces = len(list(native_solid.faces()))

    print(f"PrimitiveFeature Cylinder: {feat_faces} Faces")
    print(f"Native make_cylinder: {native_faces} Faces")

    assert feat_faces == native_faces == 3
    print("✓ Native Build123D Vergleich Test bestanden!")


def run_all_primitive_feature_tests():
    """Führt alle PrimitiveFeature Tests aus."""
    print("\n" + "="*60)
    print("PRIMITIVEFEATURE NATIVE OCP TEST SUITE")
    print("="*60 + "\n")

    tests = [
        ("Box 6 Faces", test_primitive_box_6_faces),
        ("Cylinder 3 Faces", test_primitive_cylinder_3_faces),
        ("Sphere 1 Face", test_primitive_sphere_1_face),
        ("Cone Frustum 3 Faces", test_primitive_cone_frustum_3_faces),
        ("Cone Pointed 2 Faces", test_primitive_cone_pointed_2_faces),
        ("Primitive = Native OCP", test_primitive_vs_native_build123d),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        try:
            print(f"Running: {name}...", end=" ")
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {e}")
            failed += 1
            errors.append((name, str(e)[:100]))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
            errors.append((name, str(e)[:100]))

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)

    if errors:
        print("\nFailed Tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_primitive_feature_tests()
    sys.exit(0 if success else 1)
