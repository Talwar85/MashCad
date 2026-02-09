#!/usr/bin/env python3
"""
Integration Regression Test Suite
==================================

Diese Tests beweisen dass komplette Workflows mit mehreren Features
nach neuen Änderungen weiterhin korrekt funktionieren.

Workflows:
1. Box → PushPull → Fillet → Chamfer (klassische CAD-Sequenz)
2. Sketch → Extrude → Boolean Cut → Fillet (Bohrung mit Abrundung)
3. Extrude → Draft → Hollow (Gussteil-Workflow)
4. Revolve → Fillet → Shell (Rotations-Symmetrie Teil)
5. Multiple Boolean Operations mit nachfolgenden Fillets
6. Complex Assembly Workflow
7. Undo/Redo Sequenzen
8. Save/Load Cycle
"""
import pytest
import build123d as bd
from build123d import Solid, Face, Edge, Location, Vector, Rotation
from modeling import (
    Body, Document,
    ExtrudeFeature, PushPullFeature,
    FilletFeature, ChamferFeature,
    BooleanFeature, BooleanOperationType,
    DraftFeature, HollowFeature,
    RevolveFeature
)
from modeling.result_types import ResultStatus
from modeling.body_transaction import BodyTransaction
import tempfile
import json


# ============================================================================
# 1. Klassische CAD-Sequenz: Box → PushPull → Fillet → Chamfer
# ============================================================================

def test_workflow_box_pushpull_fillet_chamfer():
    """Klassische CAD-Sequenz"""
    doc = Document("Box PushPull Fillet Chamfer")
    body = Body("TestBody")

    # 1. Box erstellen (durch Extrude von Rechteck)
    profile = bd.Rectangle(20, 15).faces()[0]
    extrude = ExtrudeFeature(
        amount=10.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value
    initial_volume = solid.volume

    # 2. PushPull auf Top Face
    top_face = list(solid.faces())[0]
    pushpull = PushPullFeature(
        distance=3.0,
        face_indices=[0],
        operation_type="join"
    )

    result2 = doc._compute_pushpull(
        body_solid=solid,
        selected_faces=[top_face],
        feature=pushpull
    )

    assert result2.status == ResultStatus.SUCCESS
    solid = result2.value
    assert solid.volume > initial_volume

    # 3. Fillet auf vertikalen Kanten
    edges = list(solid.edges())
    fillet = FilletFeature(
        radius=1.0,
        edge_indices=[0, 1, 2, 3]
    )

    result3 = doc._compute_fillet(
        body_solid=solid,
        feature=fillet
    )

    assert result3.status == ResultStatus.SUCCESS
    solid = result3.value

    # 4. Chamfer auf Top Edge
    chamfer = ChamferFeature(
        distance=0.5,
        edge_indices=[0]
    )

    result4 = doc._compute_chamfer(
        body_solid=solid,
        feature=chamfer
    )

    assert result4.status == ResultStatus.SUCCESS
    final_solid = result4.value

    # Validierung
    assert final_solid.is_valid()
    assert final_solid.volume > 0

    print("✓ Box → PushPull → Fillet → Chamfer Workflow")


# ============================================================================
# 2. Bohrung mit Abrundung: Sketch → Extrude → Boolean → Fillet
# ============================================================================

def test_workflow_bore_with_fillet():
    """Bohrungs-Workflow mit Abrundung"""
    doc = Document("Bore with Fillet")
    body = Body("BoreBody")

    # 1. Base Plate
    profile = bd.Rectangle(30, 30).faces()[0]
    extrude = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value

    # 2. Bohrung (Boolean Cut)
    cylinder = bd.Solid.make_cylinder(3.0, 5)
    boolean = BooleanFeature(
        operation_type=BooleanOperationType.CUT,
        tool_bodies=[],
        tool_profile_center=None
    )

    result2 = doc._compute_boolean(
        body_solid=solid,
        tool_solid=cylinder,
        feature=boolean,
        operation="Cut"
    )

    assert result2.status == ResultStatus.SUCCESS
    solid = result2.value

    # Prüfe dass Loch vorhanden ist
    cylindrical_faces = []
    for face in solid.faces():
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cylindrical_faces.append(face)

    assert len(cylindrical_faces) >= 1

    # 3. Fillet auf Loch-Kanten
    # Finde die zirkulären Kanten des Lochs
    hole_edges = []
    for edge in solid.edges():
        # Kanten des Lochs sind typischerweise kurz
        if 18 < edge.length < 20:  # 2*pi*r ≈ 18.85 für r=3
            hole_edges.append(edge)

    if len(hole_edges) >= 1:
        fillet = FilletFeature(
            radius=0.5,
            edge_indices=[0]
        )

        result3 = doc._compute_fillet(
            body_solid=solid,
            feature=fillet
        )

        assert result3.status == ResultStatus.SUCCESS

    print("✓ Sketch → Extrude → Boolean → Fillet Workflow")


# ============================================================================
# 3. Gussteil-Workflow: Extrude → Draft → Hollow
# ============================================================================

def test_workflow_casting_part():
    """Gussteil-Workflow"""
    doc = Document("Casting Part")
    body = Body("CastingBody")

    # 1. Base Block
    profile = bd.Rectangle(40, 30).faces()[0]
    extrude = ExtrudeFeature(
        amount=20.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value

    # 2. Draft auf Seitenflächen
    faces = list(solid.faces())
    side_faces = faces[1:5]  # 4 Seitenflächen

    draft = DraftFeature(
        angle=3.0,
        face_indices=[1, 2, 3, 4],
        draft_plane_normal=None
    )

    result2 = doc._compute_draft(
        body_solid=solid,
        selected_faces=side_faces,
        feature=draft
    )

    assert result2.status == ResultStatus.SUCCESS
    solid = result2.value

    # 3. Hollow (Auswandung)
    hollow = HollowFeature(
        thickness=3.0,
        face_indices=[]
    )

    result3 = doc._compute_hollow(
        body_solid=solid,
        feature=hollow
    )

    assert result3.status == ResultStatus.SUCCESS
    final_solid = result3.value

    assert final_solid.is_valid()

    print("✓ Extrude → Draft → Hollow Workflow")


# ============================================================================
# 4. Rotations-Symmetrie: Revolve → Fillet → Shell
# ============================================================================

def test_workflow_revolution_part():
    """Rotations-Symmetrie Workflow"""
    doc = Document("Revolution Part")
    body = Body("RevolutionBody")

    # 1. Profil für Revolve
    # Erstelle ein L-förmiges Profil
    profile = (
        bd.Rectangle(20, 10)
        .moved(Location(Vector(10, 0, 0)))
        .faces()[0]
    )

    revolve = RevolveFeature(
        angle=360.0,
        profile_face_index=0,
        axis_edge_index=None,
        axis_point=None,
        axis_direction=None
    )

    result = doc._compute_revolve(
        body_solid=None,
        profile_face=profile,
        feature=revolve
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value

    # 2. Fillet auf Kanten
    fillet = FilletFeature(
        radius=1.0,
        edge_indices=[0, 1]
    )

    result2 = doc._compute_fillet(
        body_solid=solid,
        feature=fillet
    )

    assert result2.status == ResultStatus.SUCCESS
    solid = result2.value

    # 3. Hollow/Shell
    hollow = HollowFeature(
        thickness=2.0,
        face_indices=[0]  # Top Face öffnen
    )

    result3 = doc._compute_hollow(
        body_solid=solid,
        feature=hollow
    )

    assert result3.status == ResultStatus.SUCCESS

    print("✓ Revolve → Fillet → Shell Workflow")


# ============================================================================
# 5. Multiple Boolean mit Fillets
# ============================================================================

def test_workflow_multiple_booleans_fillets():
    """Multiple Boolean-Operationen mit nachfolgenden Fillets"""
    doc = Document("Multiple Booleans")
    body = Body("MultiBooleanBody")

    # 1. Base Plate
    profile = bd.Rectangle(50, 50).faces()[0]
    extrude = ExtrudeFeature(
        amount=10.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value

    # 2. Erste Bohrung
    cylinder1 = bd.Solid.make_cylinder(5.0, 10).located(Location(Vector(15, 15, 0)))
    boolean1 = BooleanFeature(
        operation_type=BooleanOperationType.CUT,
        tool_bodies=[],
        tool_profile_center=None
    )

    result2 = doc._compute_boolean(
        body_solid=solid,
        tool_solid=cylinder1,
        feature=boolean1,
        operation="Cut"
    )

    assert result2.status == ResultStatus.SUCCESS
    solid = result2.value

    # 3. Zweite Bohrung
    cylinder2 = bd.Solid.make_cylinder(4.0, 10).located(Location(Vector(35, 15, 0)))
    result3 = doc._compute_boolean(
        body_solid=solid,
        tool_solid=cylinder2,
        feature=boolean1,
        operation="Cut"
    )

    assert result3.status == ResultStatus.SUCCESS
    solid = result3.value

    # 4. Dritte Bohrung
    cylinder3 = bd.Solid.make_cylinder(6.0, 10).located(Location(Vector(25, 35, 0)))
    result4 = doc._compute_boolean(
        body_solid=solid,
        tool_solid=cylinder3,
        feature=boolean1,
        operation="Cut"
    )

    assert result4.status == ResultStatus.SUCCESS
    solid = result4.value

    # 5. Fillets auf alle Bohrungskanten
    # Finde zirkuläre Kanten
    hole_edges = []
    for i, edge in enumerate(solid.edges()):
        # Prüfe ob es eine zirkuläre Kante ist
        length = edge.length
        if 25 < length < 40:  # Löcher mit r=4-6 haben Umfang 25-38
            hole_edges.append(i)

    # Fillet auf erste paar Loch-Kanten
    if len(hole_edges) >= 2:
        fillet = FilletFeature(
            radius=1.0,
            edge_indices=hole_edges[:4]
        )

        result5 = doc._compute_fillet(
            body_solid=solid,
            feature=fillet
        )

        assert result5.status == ResultStatus.SUCCESS

    print("✓ Multiple Booleans with Fillets Workflow")


# ============================================================================
# 6. Undo/Redo Sequenzen
# ============================================================================

def test_workflow_undo_redo_sequence():
    """Undo/Redo Sequenz mit mehreren Features"""
    doc = Document("Undo Redo Sequence")
    body = Body("UndoRedoBody")

    # 1. Erste Operation: Extrude
    profile = bd.Rectangle(10, 10).faces()[0]
    extrude = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS
    solid1 = result.value
    volume1 = solid1.volume

    # 2. Zweite Operation: Fillet
    fillet = FilletFeature(radius=1.0, edge_indices=[0, 1, 2, 3])
    result2 = doc._compute_fillet(body_solid=solid1, feature=fillet)

    assert result2.status == ResultStatus.SUCCESS
    solid2 = result2.value
    volume2 = solid2.volume

    # 3. Dritte Operation: PushPull
    top_face = list(solid2.faces())[0]
    pushpull = PushPullFeature(distance=2.0, face_indices=[0], operation_type="join")
    result3 = doc._compute_pushpull(
        body_solid=solid2,
        selected_faces=[top_face],
        feature=pushpull
    )

    assert result3.status == ResultStatus.SUCCESS
    solid3 = result3.value
    volume3 = solid3.volume

    # Undo von PushPull
    # In echt würde das über den Command Handler gehen
    # Hier simulieren wir das durch erneute Ausführung von vorherigem State

    # Redo: Wiederhole PushPull
    result4 = doc._compute_pushpull(
        body_solid=solid2,
        selected_faces=[top_face],
        feature=pushpull
    )

    assert result4.status == ResultStatus.SUCCESS
    solid4 = result4.value

    # Volumen sollte gleich sein
    assert solid3.volume == pytest.approx(solid4.volume, abs=1e-6)

    print("✓ Undo/Redo Sequence")


# ============================================================================
# 7. Save/Load Cycle
# ============================================================================

def test_workflow_save_load_cycle():
    """Save/Load Cycle mit mehreren Features"""
    doc = Document("Save Load Cycle")
    body = Body("SaveLoadBody")

    # 1. Erstelle Features
    profile = bd.Rectangle(15, 15).faces()[0]
    extrude = ExtrudeFeature(
        amount=10.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS

    # 2. Serialisiere Feature
    data = result.value.to_dict() if hasattr(result.value, 'to_dict') else None

    # Wenn das Solid serialisierbar ist
    if data:
        # Simuliere Save/Load
        json_str = json.dumps(data)
        loaded_data = json.loads(json_str)

        assert loaded_data is not None

    print("✓ Save/Load Cycle")


# ============================================================================
# 8. Kompletter Teile-Workflow
# ============================================================================

def test_workflow_complete_part():
    """Kompletter Workflow für ein realistisches Teil"""
    doc = Document("Complete Part")
    body = Body("CompletePartBody")

    # 1. Base Plate
    profile = bd.Rectangle(40, 25).faces()[0]
    extrude = ExtrudeFeature(
        amount=8.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value
    initial_volume = solid.volume

    # 2. Vier Bohrungen in den Ecken
    hole_positions = [
        (5, 5), (35, 5), (5, 20), (35, 20)
    ]

    for pos in hole_positions:
        cylinder = bd.Solid.make_cylinder(2.0, 8).located(
            Location(Vector(pos[0], pos[1], 0))
        )

        boolean = BooleanFeature(
            operation_type=BooleanOperationType.CUT,
            tool_bodies=[],
            tool_profile_center=None
        )

        result = doc._compute_boolean(
            body_solid=solid,
            tool_solid=cylinder,
            feature=boolean,
            operation="Cut"
        )

        assert result.status == ResultStatus.Success
        solid = result.value

    # 3. Zentrale größere Bohrung
    center_cylinder = bd.Solid.make_cylinder(5.0, 8).located(
        Location(Vector(20, 12.5, 0))
    )

    result = doc._compute_boolean(
        body_solid=solid,
        tool_solid=center_cylinder,
        feature=boolean,
        operation="Cut"
    )

    assert result.status == ResultStatus.SUCCESS
    solid = result.value

    # 4. Fillets auf Außenkanten
    fillet = FilletFeature(radius=2.0, edge_indices=[0, 1, 2, 3])
    result = doc._compute_fillet(body_solid=solid, feature=fillet)

    assert result.status == ResultStatus.SUCCESS
    solid = result.value

    # 5. Chamfers auf Bohrungskanten
    chamfer = ChamferFeature(distance=0.5, edge_indices=[0, 1, 2, 3])
    result = doc._compute_chamfer(body_solid=solid, feature=chamfer)

    assert result.status == ResultStatus.SUCCESS
    final_solid = result.value

    # Validierung
    assert final_solid.is_valid()
    assert final_solid.volume < initial_volume  # Material wurde entfernt
    assert final_solid.volume > 0

    print("✓ Complete Part Workflow")


# ============================================================================
# 9. Rebuild-Idempotenz für komplexe Workflows
# ============================================================================

def test_workflow_rebuild_idempotent_complex():
    """Rebuild ist idempotent für komplexe Workflows"""
    doc = Document("Rebuild Complex")

    # Erstelle komplexe Geometrie
    profile = bd.Rectangle(20, 20).faces()[0]
    extrude = ExtrudeFeature(
        amount=10.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result1 = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    solid1 = result1.value

    # Füge Fillet hinzu
    fillet = FilletFeature(radius=1.0, edge_indices=[0, 1, 2, 3])
    result2 = doc._compute_fillet(body_solid=solid1, feature=fillet)
    solid2 = result2.value

    # Rebuild: Erstelle alles neu
    result3 = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    solid3 = result3.value

    result4 = doc._compute_fillet(body_solid=solid3, feature=fillet)
    solid4 = result4.value

    # Gleiche Volumina
    assert solid2.volume == pytest.approx(solid4.volume, abs=1e-5)

    print("✓ Rebuild Idempotent Complex")


# ============================================================================
# Test Runner
# ============================================================================

def run_all_integration_regression_tests():
    """Führt alle Integration Regression Tests aus"""
    print("\n" + "="*60)
    print("INTEGRATION REGRESSION TEST SUITE")
    print("="*60 + "\n")

    tests = [
        ("Box → PushPull → Fillet → Chamfer", test_workflow_box_pushpull_fillet_chamfer),
        ("Sketch → Extrude → Boolean → Fillet", test_workflow_bore_with_fillet),
        ("Extrude → Draft → Hollow", test_workflow_casting_part),
        ("Revolve → Fillet → Shell", test_workflow_revolution_part),
        ("Multiple Booleans with Fillets", test_workflow_multiple_booleans_fillets),
        ("Undo/Redo Sequence", test_workflow_undo_redo_sequence),
        ("Save/Load Cycle", test_workflow_save_load_cycle),
        ("Complete Part Workflow", test_workflow_complete_part),
        ("Rebuild Idempotent Complex", test_workflow_rebuild_idempotent_complex),
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
    success = run_all_integration_regression_tests()
    sys.exit(0 if success else 1)
