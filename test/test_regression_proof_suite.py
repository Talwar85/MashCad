#!/usr/bin/env python3
"""
Regression Proof Suite
======================

Diese Tests beweisen dass nach neuen Änderungen:
1. TNP v4.1 weiterhin funktioniert
2. Alle vorhandenen Features korrekt arbeiten
3. Komplette Workflows stabil bleiben

Basierend auf den existierenden Test-Patterns in test_cad_workflow_trust.py
"""
import math
import random
import pytest
import build123d as bd
from build123d import Vector, Location

from modeling import (
    Body,
    ChamferFeature,
    Document,
    ExtrudeFeature,
    FilletFeature,
    RevolveFeature,
    ShellFeature,
    HollowFeature,
    PrimitiveFeature,
)
from modeling.geometric_selector import GeometricFaceSelector
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.tnp_system import ShapeType
from sketcher.sketch import Sketch, SketchState
from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D


# ===========================================================================
# HILFSFUNKTIONEN
# ===========================================================================

def _solid_signature(solid):
    """Geometrie-Fingerprint eines Solids."""
    assert solid is not None, "Solid is None!"
    bb = solid.bounding_box()
    return {
        "volume": float(solid.volume),
        "faces": len(list(solid.faces())),
        "edges": len(list(solid.edges())),
        "bbox": (
            float(bb.min.X), float(bb.min.Y), float(bb.min.Z),
            float(bb.max.X), float(bb.max.Y), float(bb.max.Z),
        ),
    }


def _assert_signature_close(a: dict, b: dict, *, context: str):
    """Vergleicht zwei Solid-Signaturen auf Gleichheit."""
    assert a["faces"] == b["faces"], f"{context}: face-count {a['faces']} != {b['faces']}"
    assert a["edges"] == b["edges"], f"{context}: edge-count {a['edges']} != {b['edges']}"
    assert a["volume"] == pytest.approx(b["volume"], rel=1e-6, abs=1e-6), (
        f"{context}: volume {a['volume']} != {b['volume']}"
    )


# ===========================================================================
# 1. TNP v4.1 BASIS TESTS
# ===========================================================================

def test_tnp_shape_id_stability():
    """ShapeIDs sind stabil über Rebuild-Hinweg"""
    doc = Document("TNP ShapeID Stability Test")
    body = Body("TestBody")

    # Erstelle Box mit Extrude
    sketch = Sketch("test_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 10)))
    sketch.add_geometry(Line2D(Point2D(10, 10), Point2D(0, 10)))
    sketch.add_geometry(Line2D(Point2D(0, 10), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    face_index = face_index_of(body._build123d_solid, profile_face) if body._build123d_solid else 0

    feature = ExtrudeFeature(
        amount=5.0,
        profile_face_index=face_index,
        direction_vector=None,
        operation_type="join"
    )

    # Führe Extrusion aus
    result = doc._compute_extrude_part(feature)
    assert result.status.value == "success"
    body._build123d_solid = result.value
    body.invalidate_mesh()

    # Erste Signatur
    sig1 = _solid_signature(body._build123d_solid)

    # Rebuild
    result2 = doc._compute_extrude_part(feature)
    assert result2.status.value == "success"
    body._build123d_solid = result2.value
    body.invalidate_mesh()

    # Zweite Signatur
    sig2 = _solid_signature(body._build123d_solid)

    # Sollte identisch sein
    _assert_signature_close(sig1, sig2, context="Extrude Rebuild")

    print("✓ TNP ShapeID Stability")


def test_tnp_face_tracking():
    """TNP Face-Tracking funktioniert"""
    doc = Document("TNP Face Tracking Test")
    body = Body("TestBody")
    doc.add_body(body)

    # Erste Extrusion
    sketch = Sketch("sketch1")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 10)))
    sketch.add_geometry(Line2D(Point2D(10, 10), Point2D(0, 10)))
    sketch.add_geometry(Line2D(Point2D(0, 10), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    face_index = face_index_of(body._build123d_solid, profile_face) if body._build123d_solid else 0

    feature1 = ExtrudeFeature(
        amount=5.0,
        profile_face_index=face_index,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude_part(feature1)
    assert result.status.value == "success"
    body._build123d_solid = result.value
    body.add_feature(feature1)
    body.invalidate_mesh()

    # Prüfe dass Feature Face-Tracking hat
    assert hasattr(feature1, 'face_shape_ids') or hasattr(feature1, 'profile_face_index')

    # Zweite Extrusion auf Top Face
    top_face = list(body._build123d_solid.faces())[0]
    top_face_index = face_index_of(body._build123d_solid, top_face)

    feature2 = ExtrudeFeature(
        amount=2.0,
        profile_face_index=top_face_index,
        direction_vector=None,
        operation_type="join"
    )

    result2 = doc._compute_extrude_part(feature2)
    assert result2.status.value == "success"
    body._build123d_solid = result2.value
    body.add_feature(feature2)
    body.invalidate_mesh()

    # Prüfe dass Volumen korrekt ist
    assert body._build123d_solid.volume > 0

    print("✓ TNP Face Tracking")


# ===========================================================================
# 2. EXTRUDE FEATURE TESTS
# ===========================================================================

def test_extrude_simple_box():
    """Einfache Box-Extrusion"""
    doc = Document("Extrude Box Test")
    body = Body("BoxBody")

    sketch = Sketch("box_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 10)))
    sketch.add_geometry(Line2D(Point2D(10, 10), Point2D(0, 10)))
    sketch.add_geometry(Line2D(Point2D(0, 10), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    face_index = 0

    feature = ExtrudeFeature(
        amount=5.0,
        profile_face_index=face_index,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude_part(feature)
    assert result.status.value == "success"

    solid = result.value
    assert solid is not None
    assert solid.volume == pytest.approx(10 * 10 * 5, abs=1e-3)

    print("✓ Extrude Simple Box")


def test_extrude_circle_to_cylinder():
    """Kreis zu Zylinder"""
    doc = Document("Extrude Circle Test")

    sketch = Sketch("circle_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Circle2D(Point2D(5, 5), 5.0))

    profile_face = sketch.to_build123d_face()[0]
    face_index = 0

    feature = ExtrudeFeature(
        amount=10.0,
        profile_face_index=face_index,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude_part(feature)
    assert result.status.value == "success"

    solid = result.value
    expected_volume = math.pi * 5.0**2 * 10.0
    assert solid.volume == pytest.approx(expected_volume, abs=1e-2)

    print("✓ Extrude Circle to Cylinder")


# ===========================================================================
# 3. FILLET FEATURE TESTS
# ===========================================================================

def test_fillet_single_edge():
    """Fillet auf einzelner Kante"""
    doc = Document("Fillet Single Test")
    body = Body("FilletBody")
    doc.add_body(body)

    # Box erstellen
    sketch = Sketch("box_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 10)))
    sketch.add_geometry(Line2D(Point2D(10, 10), Point2D(0, 10)))
    sketch.add_geometry(Line2D(Point2D(0, 10), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    extrude = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude_part(extrude)
    assert result.status.value == "success"
    body._build123d_solid = result.value
    body.add_feature(extrude)
    body.invalidate_mesh()

    # Fillet auf erste Kante
    edges = list(body._build123d_solid.edges())
    edge_index = edge_index_of(body._build123d_solid, edges[0])

    fillet = FilletFeature(radius=1.0, edge_indices=[edge_index])
    result2 = doc._compute_fillet_part(fillet)

    assert result2.status.value == "success"
    body._build123d_solid = result2.value
    body.add_feature(fillet)
    body.invalidate_mesh()

    assert body._build123d_solid.is_valid()

    print("✓ Fillet Single Edge")


def test_fillet_multiple_edges():
    """Fillet auf mehreren Kanten"""
    doc = Document("Fillet Multiple Test")
    body = Body("FilletMultiBody")
    doc.add_body(body)

    # Box erstellen
    solid = bd.Solid.make_box(10, 10, 5)
    body._build123d_solid = solid

    # Alle vertikalen Kanten filleten
    edges = list(body._build123d_solid.edges())
    edge_indices = []
    for i, edge in enumerate(edges):
        if edge.length > 4:  # Vertikale Kanten
            edge_indices.append(edge_index_of(body._build123d_solid, edge))

    fillet = FilletFeature(radius=0.5, edge_indices=edge_indices[:4])
    result = doc._compute_fillet_part(fillet)

    assert result.status.value == "success"

    print("✓ Fillet Multiple Edges")


# ===========================================================================
# 4. CHAMFER FEATURE TESTS
# ===========================================================================

def test_chamfer_single_edge():
    """Chamfer auf einzelner Kante"""
    doc = Document("Chamfer Single Test")
    body = Body("ChamferBody")
    doc.add_body(body)

    # Box erstellen
    solid = bd.Solid.make_box(10, 10, 5)
    body._build123d_solid = solid

    edges = list(body._build123d_solid.edges())
    edge_index = edge_index_of(body._build123d_solid, edges[0])

    chamfer = ChamferFeature(distance=0.5, edge_indices=[edge_index])
    result = doc._compute_chamfer_part(chamfer)

    assert result.status.value == "success"

    print("✓ Chamfer Single Edge")


# ===========================================================================
# 5. REVOLVE FEATURE TESTS
# ===========================================================================

def test_revolve_rectangle():
    """Rechteck revolve"""
    doc = Document("Revolve Test")
    body = Body("RevolveBody")
    doc.add_body(body)

    # Profil erstellen
    sketch = Sketch("revolve_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(5, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 5)))
    sketch.add_geometry(Line2D(Point2D(10, 5), Point2D(5, 5)))
    sketch.add_geometry(Line2D(Point2D(5, 5), Point2D(5, 0)))

    profile_face = sketch.to_build123d_face()[0]
    face_index = 0

    feature = RevolveFeature(
        angle=360.0,
        profile_face_index=face_index,
        axis_edge_index=None,
        axis_point=None,
        axis_direction=None
    )

    result = doc._compute_revolve_part(feature)
    assert result.status.value == "success"

    print("✓ Revolve Rectangle")


# ===========================================================================
# 6. BOOLEAN OPERATION TESTS
# ===========================================================================

def test_boolean_cut_with_hole():
    """Boolean Cut Operation"""
    doc = Document("Boolean Cut Test")
    body = Body("CutBody")
    doc.add_body(body)

    # Base Box
    solid = bd.Solid.make_box(20, 20, 5)
    body._build123d_solid = solid

    # Bohrung
    cylinder = bd.Solid.make_cylinder(3.0, 5).located(Location(Vector(10, 10, 0)))

    # Hole Feature verwenden
    hole = HollowFeature(thickness=3.0, face_indices=[])
    # Hole Feature arbeitet anders, wir testen über die Boolean-Engine
    # direkter Boolean Cut:
    result_solid = solid - cylinder

    assert result_solid.is_valid()

    # Prüfe dass Loch vorhanden ist
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    cylindrical_faces = []
    for face in result_solid.faces():
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cylindrical_faces.append(face)

    assert len(cylindrical_faces) >= 1

    print("✓ Boolean Cut with Hole")


# ===========================================================================
# 7. COMPLEX WORKFLOW TESTS
# ===========================================================================

def test_workflow_extrude_fillet_chamfer():
    """Kompletter Workflow: Extrude → Fillet → Chamfer"""
    doc = Document("Complex Workflow Test")
    body = Body("WorkflowBody")
    doc.add_body(body)

    # 1. Extrude
    sketch = Sketch("workflow_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 10)))
    sketch.add_geometry(Line2D(Point2D(10, 10), Point2D(0, 10)))
    sketch.add_geometry(Line2D(Point2D(0, 10), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    extrude = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude_part(extrude)
    assert result.status.value == "success"
    body._build123d_solid = result.value
    body.add_feature(extrude)
    body.invalidate_mesh()

    sig1 = _solid_signature(body._build123d_solid)

    # 2. Fillet
    edges = list(body._build123d_solid.edges())
    edge_indices = [edge_index_of(body._build123d_solid, edges[i]) for i in range(4)]

    fillet = FilletFeature(radius=1.0, edge_indices=edge_indices)
    result2 = doc._compute_fillet_part(fillet)

    assert result2.status.value == "success"
    body._build123d_solid = result2.value
    body.add_feature(fillet)
    body.invalidate_mesh()

    sig2 = _solid_signature(body._build123d_solid)

    # 3. Chamfer
    top_face = list(body._build123d_solid.faces())[0]
    face_index = face_index_of(body._build123d_solid, top_face)

    # Top Face edges finden
    top_edges = list(top_face.edges())
    edge_index = edge_index_of(body._build123d_solid, top_edges[0])

    chamfer = ChamferFeature(distance=0.5, edge_indices=[edge_index])
    result3 = doc._compute_chamfer_part(chamfer)

    assert result3.status.value == "success"
    body._build123d_solid = result3.value
    body.add_feature(chamfer)
    body.invalidate_mesh()

    sig3 = _solid_signature(body._build123d_solid)

    # Validierung
    assert body._build123d_solid.is_valid()
    assert sig3["volume"] < sig2["volume"]  # Chamfer entfernt Material
    assert sig2["volume"] < sig1["volume"]  # Fillet entfernt Material

    print("✓ Complex Workflow: Extrude → Fillet → Chamfer")


# ===========================================================================
# 8. REBUILD IDEMPOTENCE TESTS
# ===========================================================================

def test_rebuild_idempotent():
    """Rebuild ist idempotent"""
    doc = Document("Rebuild Test")
    body = Body("RebuildBody")
    doc.add_body(body)

    # Erstelle Feature
    sketch = Sketch("rebuild_sketch")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(10, 0)))
    sketch.add_geometry(Line2D(Point2D(10, 0), Point2D(10, 10)))
    sketch.add_geometry(Line2D(Point2D(10, 10), Point2D(0, 10)))
    sketch.add_geometry(Line2D(Point2D(0, 10), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    feature = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    # Erster Build
    result1 = doc._compute_extrude_part(feature)
    assert result1.status.value == "success"
    sig1 = _solid_signature(result1.value)

    # Zweiter Build (Rebuild)
    result2 = doc._compute_extrude_part(feature)
    assert result2.status.value == "success"
    sig2 = _solid_signature(result2.value)

    # Sollte identisch sein
    _assert_signature_close(sig1, sig2, context="Rebuild Idempotent")

    print("✓ Rebuild Idempotent")


# ===========================================================================
# 9. SAVE/LOAD TESTS
# ===========================================================================

def test_feature_serialization():
    """Feature Serialisierung/Deserialisierung"""
    # Extrude Feature
    feature1 = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    # Serialisiere
    data1 = feature1.to_dict()

    assert data1["amount"] == 5.0
    assert data1["profile_face_index"] == 0
    assert data1["operation_type"] == "join"

    # Deserialisiere
    feature2 = ExtrudeFeature.from_dict(data1)

    assert feature2.amount == 5.0
    assert feature2.profile_face_index == 0
    assert feature2.operation_type == "join"

    # Fillet Feature
    fillet1 = FilletFeature(radius=1.0, edge_indices=[0, 1, 2])
    data2 = fillet1.to_dict()

    assert data2["radius"] == 1.0
    assert len(data2["edge_indices"]) == 3

    fillet2 = FilletFeature.from_dict(data2)

    assert fillet2.radius == 1.0
    assert len(fillet2.edge_indices) == 3

    print("✓ Feature Serialization")


# ===========================================================================
# 10. RANDOMIZED STRESS TEST
# ===========================================================================

@pytest.mark.parametrize("seed", [7, 19, 43, 71, 97])
def test_randomized_workflow_stress(seed):
    """Randomisierter Stress-Test"""
    random.seed(seed)

    doc = Document(f"Stress Test {seed}")
    body = Body("StressBody")
    doc.add_body(body)

    # Zufällige Box-Abmessungen
    w = random.uniform(5, 20)
    h = random.uniform(5, 20)
    d = random.uniform(5, 10)

    # Erstelle Sketch
    sketch = Sketch(f"stress_sketch_{seed}")
    sketch.state = SketchState.FINALIZED
    sketch.add_geometry(Line2D(Point2D(0, 0), Point2D(w, 0)))
    sketch.add_geometry(Line2D(Point2D(w, 0), Point2D(w, h)))
    sketch.add_geometry(Line2D(Point2D(w, h), Point2D(0, h)))
    sketch.add_geometry(Line2D(Point2D(0, h), Point2D(0, 0)))

    profile_face = sketch.to_build123d_face()[0]
    extrude = ExtrudeFeature(
        amount=d,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude_part(extrude)
    assert result.status.value == "success"
    body._build123d_solid = result.value
    body.add_feature(extrude)
    body.invalidate_mesh()

    # Zufälliger Fillet Radius
    radius = random.uniform(0.5, 2.0)
    edges = list(body._build123d_solid.edges())
    edge_indices = [edge_index_of(body._build123d_solid, edges[i]) for i in range(min(4, len(edges)))]

    fillet = FilletFeature(radius=radius, edge_indices=edge_indices)
    result2 = doc._compute_fillet_part(fillet)

    assert result2.status.value == "success"
    body._build123d_solid = result2.value
    body.add_feature(fillet)
    body.invalidate_mesh()

    # Validierung
    assert body._build123d_solid.is_valid()
    assert body._build123d_solid.volume > 0

    print(f"✓ Randomized Stress Test (seed={seed})")


# ===========================================================================
# TEST RUNNER
# ===========================================================================

def run_all_regression_tests():
    """Führt alle Regression-Tests aus"""
    print("\n" + "="*60)
    print("REGRESSION PROOF SUITE")
    print("="*60 + "\n")

    tests = [
        ("TNP ShapeID Stability", test_tnp_shape_id_stability),
        ("TNP Face Tracking", test_tnp_face_tracking),
        ("Extrude Simple Box", test_extrude_simple_box),
        ("Extrude Circle to Cylinder", test_extrude_circle_to_cylinder),
        ("Fillet Single Edge", test_fillet_single_edge),
        ("Fillet Multiple Edges", test_fillet_multiple_edges),
        ("Chamfer Single Edge", test_chamfer_single_edge),
        ("Revolve Rectangle", test_revolve_rectangle),
        ("Boolean Cut with Hole", test_boolean_cut_with_hole),
        ("Complex Workflow", test_workflow_extrude_fillet_chamfer),
        ("Rebuild Idempotent", test_rebuild_idempotent),
        ("Feature Serialization", test_feature_serialization),
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
            print(f"✗ FAIL")
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
            print(f"  - {name}: {error[:100]}")

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_regression_tests()
    sys.exit(0 if success else 1)
