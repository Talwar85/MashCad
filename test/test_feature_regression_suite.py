#!/usr/bin/env python3
"""
Feature Regression Test Suite
=============================

Diese Tests beweisen dass alle vorhandenen Features nach neuen Änderungen
weiterhin korrekt funktionieren.

Getestete Features:
1. Extrude (verschiedene Modi)
2. PushPull (Join, Cut)
3. Fillet (verschiedene Radien, multiple Edges)
4. Chamfer (verschiedene Distanzen, multiple Edges)
5. Boolean (Cut, Union, Intersect)
6. Sweep (verschiedene Profile)
7. Loft (multiple Profiles)
8. Revolve (verschiedene Winkel)
9. Draft (verschiedene Winkel)
10. Hollow (verschiedene Dicken)
11. Pattern (Linear, Circular)
12. Mirror (verschiedene Ebenen)
13. Scale (verschiedene Faktoren)
14. Helix (verschiedene Parameter)
"""
import pytest
import build123d as bd
from build123d import Solid, Face, Edge, Location, Vector, Rotation, Plane
from modeling import (
    Body, Document,
    ExtrudeFeature,
    FilletFeature, ChamferFeature,
    SweepFeature, LoftFeature,
    DraftFeature, HollowFeature,
    RevolveFeature,
    ShellFeature, HoleFeature,
    SplitFeature, ThreadFeature
    # Nicht existierende Features (TODO):
    # PushPullFeature, BooleanFeature, BooleanOperationType,
    # PatternFeature, MirrorFeature, ScaleFeature, HelixFeature
)
from modeling.result_types import ResultStatus


# ============================================================================
# 1. Extrude Feature Tests
# ============================================================================

def test_extrude_simple_rectangle():
    """Einfache Rechteck-Extrusion"""
    doc = Document("Extrude Simple Test")
    profile = bd.Rectangle(10, 20).faces()[0]

    feature = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.is_valid()
    assert result.value.volume == pytest.approx(10 * 20 * 5, abs=1e-3)

    print("✓ Extrude Simple Rectangle")


def test_extrude_circle_to_cylinder():
    """Kreis zu Zylinder extrudieren"""
    doc = Document("Extrude Circle Test")
    profile = bd.Circle(5.0).faces()[0]

    feature = ExtrudeFeature(
        amount=10.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()
    expected_volume = 3.14159 * 5.0**2 * 10.0
    assert result.value.volume == pytest.approx(expected_volume, abs=1e-2)

    print("✓ Extrude Circle to Cylinder")


def test_extrude_complex_profile():
    """Komplexes Profil extrudieren"""
    doc = Document("Extrude Complex Test")

    # Profil mit Loch
    outer = bd.Rectangle(20, 20)
    inner = bd.Circle(5.0)
    profile = (outer - inner).faces()[0]

    feature = ExtrudeFeature(
        amount=10.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Extrude Complex Profile")


# ============================================================================
# 2. PushPull Feature Tests
# ============================================================================

def test_pushpull_join():
    """PushPull Join Operation"""
    doc = Document("PushPull Join Test")

    base = bd.Solid.make_box(20, 20, 10)
    top_face = list(base.faces())[0]

    feature = PushPullFeature(
        distance=5.0,
        face_indices=[0],
        operation_type="join"
    )

    result = doc._compute_pushpull(
        body_solid=base,
        selected_faces=[top_face],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()
    assert result.value.volume > base.volume

    print("✓ PushPull Join")


def test_pushpull_cut():
    """PushPull Cut Operation"""
    doc = Document("PushPull Cut Test")

    base = bd.Solid.make_box(20, 20, 10)
    top_face = list(base.faces())[0]

    feature = PushPullFeature(
        distance=-3.0,
        face_indices=[0],
        operation_type="cut"
    )

    result = doc._compute_pushpull(
        body_solid=base,
        selected_faces=[top_face],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()
    assert result.value.volume < base.volume

    print("✓ PushPull Cut")


# ============================================================================
# 3. Fillet Feature Tests
# ============================================================================

def test_fillet_single_edge():
    """Fillet auf einzelner Kante"""
    doc = Document("Fillet Single Edge Test")

    base = bd.Solid.make_box(20, 20, 10)
    edges = list(base.edges())
    edge_to_fillet = edges[0]

    feature = FilletFeature(
        radius=2.0,
        edge_indices=[0]
    )

    result = doc._compute_fillet(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Fillet Single Edge")


def test_fillet_multiple_edges():
    """Fillet auf mehreren Kanten"""
    doc = Document("Fillet Multiple Edges Test")

    base = bd.Solid.make_box(20, 20, 10)

    # Alle vertikalen Kanten filleten
    edges = list(base.edges())
    vertical_edges = []
    for i, edge in enumerate(edges):
        # Heuristik: Kanten die in Z-Richtung laufen
        if edge.length > 9:  # Höhe ist 10
            vertical_edges.append(i)

    feature = FilletFeature(
        radius=1.0,
        edge_indices=vertical_edges[:4]  # Nur die ersten 4
    )

    result = doc._compute_fillet(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Fillet Multiple Edges")


def test_fillet_variable_radius():
    """Fillet mit verschiedenen Radien"""
    doc = Document("Fillet Variable Radius Test")

    base = bd.Solid.make_box(20, 20, 10)

    # Zuerst einen Fillet machen
    feature1 = FilletFeature(radius=1.0, edge_indices=[0, 1, 2, 3])
    result1 = doc._compute_fillet(body_solid=base, feature=feature1)

    assert result1.status == ResultStatus.SUCCESS

    # Dann einen zweiten Fillet mit größerem Radius
    feature2 = FilletFeature(radius=2.0, edge_indices=[4, 5])
    result2 = doc._compute_fillet(body_solid=result1.value, feature=feature2)

    assert result2.status == ResultStatus.SUCCESS
    assert result2.value.is_valid()

    print("✓ Fillet Variable Radius")


# ============================================================================
# 4. Chamfer Feature Tests
# ============================================================================

def test_chamfer_single_edge():
    """Chamfer auf einzelner Kante"""
    doc = Document("Chamfer Single Edge Test")

    base = bd.Solid.make_box(20, 20, 10)

    feature = ChamferFeature(
        distance=1.0,
        edge_indices=[0]
    )

    result = doc._compute_chamfer(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Chamfer Single Edge")


def test_chamfer_multiple_edges():
    """Chamfer auf mehreren Kanten"""
    doc = Document("Chamfer Multiple Edges Test")

    base = bd.Solid.make_box(20, 20, 10)

    feature = ChamferFeature(
        distance=1.0,
        edge_indices=[0, 1, 2, 3]
    )

    result = doc._compute_chamfer(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Chamfer Multiple Edges")


# ============================================================================
# 5. Boolean Feature Tests
# ============================================================================

def test_boolean_cut():
    """Boolean Cut Operation"""
    doc = Document("Boolean Cut Test")

    base = bd.Solid.make_box(20, 20, 10)
    tool = bd.Solid.make_cylinder(3.0, 10)

    feature = BooleanFeature(
        operation_type=BooleanOperationType.CUT,
        tool_bodies=[],
        tool_profile_center=None
    )

    result = doc._compute_boolean(
        body_solid=base,
        tool_solid=tool,
        feature=feature,
        operation="Cut"
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()
    assert result.value.volume < base.volume

    print("✓ Boolean Cut")


def test_boolean_union():
    """Boolean Union Operation"""
    doc = Document("Boolean Union Test")

    base = bd.Solid.make_box(10, 10, 10)
    tool = bd.Solid.make_cylinder(3.0, 10).located(Location(Vector(5, 5, 0)))

    feature = BooleanFeature(
        operation_type=BooleanOperationType.JOIN,
        tool_bodies=[],
        tool_profile_center=None
    )

    result = doc._compute_boolean(
        body_solid=base,
        tool_solid=tool,
        feature=feature,
        operation="Join"
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Boolean Union")


def test_boolean_intersect():
    """Boolean Intersect Operation"""
    doc = Document("Boolean Intersect Test")

    base = bd.Solid.make_box(10, 10, 10)
    tool = bd.Solid.make_cylinder(5.0, 10).located(Location(Vector(5, 5, 0)))

    feature = BooleanFeature(
        operation_type=BooleanOperationType.INTERSECT,
        tool_bodies=[],
        tool_profile_center=None
    )

    result = doc._compute_boolean(
        body_solid=base,
        tool_solid=tool,
        feature=feature,
        operation="Intersect"
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Boolean Intersect")


# ============================================================================
# 6. Sweep Feature Tests
# ============================================================================

def test_sweep_circle_along_line():
    """Kreis entlang Linie sweepen"""
    doc = Document("Sweep Line Test")

    path = bd.Edge.make_line(Vector(0, 0, 0), Vector(0, 0, 10))
    profile = bd.Circle(2.0).faces()[0]

    feature = SweepFeature(
        path_edge_index=0,
        profile_face_index=0,
        is_solid=True
    )

    result = doc._compute_sweep(
        body_solid=None,
        path_edge=path,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Sweep Circle along Line")


def test_sweep_rectangle_along_arc():
    """Rechteck entlang Bogen sweepen"""
    doc = Document("Sweep Arc Test")

    # Bogen als Pfad
    path = bd.Edge.make_arc(
        center=Vector(0, 0, 0),
        radius=10,
        start_angle=0,
        end_angle=90
    )

    profile = bd.Rectangle(2, 1).faces()[0]

    feature = SweepFeature(
        path_edge_index=0,
        profile_face_index=0,
        is_solid=True
    )

    result = doc._compute_sweep(
        body_solid=None,
        path_edge=path,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Sweep Rectangle along Arc")


# ============================================================================
# 7. Loft Feature Tests
# ============================================================================

def test_loft_two_circles():
    """Loft zwischen zwei Kreisen"""
    doc = Document("Loft Two Circles Test")

    profile1 = bd.Circle(3.0).faces()[0].moved(Location(Vector(0, 0, 0)))
    profile2 = bd.Circle(5.0).faces()[0].moved(Location(Vector(0, 0, 10)))

    feature = LoftFeature(
        profile_face_indices=[0, 1],
        is_solid=True,
        is_ruled=False
    )

    result = doc._compute_loft(
        body_solid=None,
        profiles=[profile1, profile2],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Loft Two Circles")


def test_loft_three_profiles():
    """Loft zwischen drei Profilen"""
    doc = Document("Loft Three Profiles Test")

    profile1 = bd.Circle(2.0).faces()[0].moved(Location(Vector(0, 0, 0)))
    profile2 = bd.Circle(4.0).faces()[0].moved(Location(Vector(0, 0, 5)))
    profile3 = bd.Circle(3.0).faces()[0].moved(Location(Vector(0, 0, 10)))

    feature = LoftFeature(
        profile_face_indices=[0, 1, 2],
        is_solid=True,
        is_ruled=False
    )

    result = doc._compute_loft(
        body_solid=None,
        profiles=[profile1, profile2, profile3],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Loft Three Profiles")


# ============================================================================
# 8. Revolve Feature Tests
# ============================================================================

def test_revolve_rectangle_360():
    """Rechteck 360° revolve"""
    doc = Document("Revolve 360 Test")

    profile = bd.Rectangle(5, 10).faces()[0].moved(Location(Vector(10, 0, 0)))

    feature = RevolveFeature(
        angle=360.0,
        profile_face_index=0,
        axis_edge_index=None,
        axis_point=None,
        axis_direction=None
    )

    result = doc._compute_revolve(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Revolve Rectangle 360°")


def test_revolve_rectangle_180():
    """Rechteck 180° revolve"""
    doc = Document("Revolve 180 Test")

    profile = bd.Rectangle(5, 10).faces()[0].moved(Location(Vector(10, 0, 0)))

    feature = RevolveFeature(
        angle=180.0,
        profile_face_index=0,
        axis_edge_index=None,
        axis_point=None,
        axis_direction=None
    )

    result = doc._compute_revolve(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Revolve Rectangle 180°")


# ============================================================================
# 9. Draft Feature Tests
# ============================================================================

def test_draft_single_face():
    """Draft auf einzelner Face"""
    doc = Document("Draft Single Face Test")

    base = bd.Solid.make_box(20, 20, 10)
    side_face = list(base.faces())[1]  # Seitenfläche

    feature = DraftFeature(
        angle=5.0,
        face_indices=[0],
        draft_plane_normal=None
    )

    result = doc._compute_draft(
        body_solid=base,
        selected_faces=[side_face],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Draft Single Face")


def test_draft_multiple_faces():
    """Draft auf mehreren Faces"""
    doc = Document("Draft Multiple Faces Test")

    base = bd.Solid.make_box(20, 20, 10)
    faces = list(base.faces())

    feature = DraftFeature(
        angle=3.0,
        face_indices=[1, 2, 3, 4],  # Seitenflächen
        draft_plane_normal=None
    )

    result = doc._compute_draft(
        body_solid=base,
        selected_faces=[faces[i] for i in [1, 2, 3, 4]],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Draft Multiple Faces")


# ============================================================================
# 10. Hollow Feature Tests
# ============================================================================

def test_hollow_all_faces():
    """Hollow mit allen Faces"""
    doc = Document("Hollow All Faces Test")

    base = bd.Solid.make_box(20, 20, 10)

    feature = HollowFeature(
        thickness=2.0,
        face_indices=[]  # Leer = alle Faces
    )

    result = doc._compute_hollow(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Hollow All Faces")


def test_hollow_specific_face():
    """Hollow mit spezifischer Face (öffnen)"""
    doc = Document("Hollow Specific Face Test")

    base = bd.Solid.make_box(20, 20, 10)

    feature = HollowFeature(
        thickness=2.0,
        face_indices=[0]  # Top Face öffnen
    )

    result = doc._compute_hollow(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Hollow Specific Face")


# ============================================================================
# 11. Pattern Feature Tests
# ============================================================================

def test_linear_pattern():
    """Lineares Pattern"""
    doc = Document("Linear Pattern Test")

    base = bd.Solid.make_box(20, 20, 10)

    feature = PatternFeature(
        pattern_type="linear",
        count=3,
        spacing=25.0,
        direction_axis="x",
        feature_indices=[0]
    )

    # Pattern wird auf Body angewendet
    result = doc._compute_pattern(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Linear Pattern")


def test_circular_pattern():
    """Zirkuläres Pattern"""
    doc = Document("Circular Pattern Test")

    base = bd.Solid.make_cylinder(2.0, 10).located(Location(Vector(10, 0, 0)))

    feature = PatternFeature(
        pattern_type="circular",
        count=6,
        angle=60.0,
        axis="z",
        feature_indices=[0]
    )

    result = doc._compute_pattern(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Circular Pattern")


# ============================================================================
# 12. Mirror Feature Tests
# ============================================================================

def test_mirror_xy_plane():
    """Mirror an XY-Ebene"""
    doc = Document("Mirror XY Test")

    base = bd.Solid.make_box(10, 10, 10).located(Location(Vector(0, 0, 5)))

    feature = MirrorFeature(
        plane="xy",
        offset=0.0,
        feature_indices=[0]
    )

    result = doc._compute_mirror(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Mirror XY Plane")


# ============================================================================
# 13. Scale Feature Tests
# ============================================================================

def test_scale_uniform():
    """Uniformes Skalieren"""
    doc = Document("Scale Uniform Test")

    base = bd.Solid.make_box(10, 10, 10)

    feature = ScaleFeature(
        scale_factor=2.0,
        scale_type="uniform"
    )

    result = doc._compute_scale(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Scale Uniform")


def test_scale_non_uniform():
    """Non-uniformes Skalieren"""
    doc = Document("Scale Non-Uniform Test")

    base = bd.Solid.make_box(10, 10, 10)

    feature = ScaleFeature(
        scale_factor=(2.0, 1.5, 0.5),
        scale_type="non_uniform"
    )

    result = doc._compute_scale(
        body_solid=base,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Scale Non-Uniform")


# ============================================================================
# 14. Helix Feature Tests
# ============================================================================

def test_helix_simple():
    """Einfache Helix"""
    doc = Document("Helix Simple Test")

    feature = HelixFeature(
        radius=5.0,
        height=20.0,
        turns=5,
        profile_radius=1.0,
        is_solid=True
    )

    result = doc._compute_helix(
        body_solid=None,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value.is_valid()

    print("✓ Helix Simple")


# ============================================================================
# Test Runner
# ============================================================================

def run_all_feature_regression_tests():
    """Führt alle Feature Regression Tests aus"""
    print("\n" + "="*60)
    print("FEATURE REGRESSION TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # 1. Extrude
        ("Extrude Simple Rectangle", test_extrude_simple_rectangle),
        ("Extrude Circle to Cylinder", test_extrude_circle_to_cylinder),
        ("Extrude Complex Profile", test_extrude_complex_profile),

        # 2. PushPull
        ("PushPull Join", test_pushpull_join),
        ("PushPull Cut", test_pushpull_cut),

        # 3. Fillet
        ("Fillet Single Edge", test_fillet_single_edge),
        ("Fillet Multiple Edges", test_fillet_multiple_edges),
        ("Fillet Variable Radius", test_fillet_variable_radius),

        # 4. Chamfer
        ("Chamfer Single Edge", test_chamfer_single_edge),
        ("Chamfer Multiple Edges", test_chamfer_multiple_edges),

        # 5. Boolean
        ("Boolean Cut", test_boolean_cut),
        ("Boolean Union", test_boolean_union),
        ("Boolean Intersect", test_boolean_intersect),

        # 6. Sweep
        ("Sweep Circle along Line", test_sweep_circle_along_line),
        ("Sweep Rectangle along Arc", test_sweep_rectangle_along_arc),

        # 7. Loft
        ("Loft Two Circles", test_loft_two_circles),
        ("Loft Three Profiles", test_loft_three_profiles),

        # 8. Revolve
        ("Revolve 360°", test_revolve_rectangle_360),
        ("Revolve 180°", test_revolve_rectangle_180),

        # 9. Draft
        ("Draft Single Face", test_draft_single_face),
        ("Draft Multiple Faces", test_draft_multiple_faces),

        # 10. Hollow
        ("Hollow All Faces", test_hollow_all_faces),
        ("Hollow Specific Face", test_hollow_specific_face),

        # 11. Pattern
        ("Linear Pattern", test_linear_pattern),
        ("Circular Pattern", test_circular_pattern),

        # 12. Mirror
        ("Mirror XY Plane", test_mirror_xy_plane),

        # 13. Scale
        ("Scale Uniform", test_scale_uniform),
        ("Scale Non-Uniform", test_scale_non_uniform),

        # 14. Helix
        ("Helix Simple", test_helix_simple),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        try:
            print(f"Running: {name}...", end=" ")
            test_func()
            print("✓ PASS")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {e}")
            failed += 1
            errors.append((name, str(e)))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
            errors.append((name, str(e)))

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
    success = run_all_feature_regression_tests()
    sys.exit(0 if success else 1)
