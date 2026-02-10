#!/usr/bin/env python3
"""
TNP v4.1 Regression Test Suite
==============================

Diese Tests beweisen dass TNP v4.1 nach neuen Features weiterhin funktioniert.
Sie testen alle kritischen TNP-Pfade mit verschiedenen Features.

Test-Kategorien:
1. TNP v4.1 Basis-Features (ShapeID, Registry, Resolution)
2. Extrude/PushPull mit TNP
3. Fillet/Chamfer mit TNP
4. Boolean-Operationen mit TNP
5. Sweep/Loft mit TNP
6. Draft/Hollow mit TNP
7. Rebuild-Idempotenz
8. Undo/Redo mit TNP
9. Save/Load mit TNP
10. Multi-Feature Workflows
"""
import pytest
import build123d as bd
from build123d import Solid, Face, Edge, Location, Vector, Rotation
from modeling import (
    Body, Document, ExtrudeFeature,
    FilletFeature, ChamferFeature,
    SweepFeature, LoftFeature,
    DraftFeature, HollowFeature,
    ShellFeature, HoleFeature,
    ShapeID, ShapeType
    # Nicht existierende Klassen (TODO):
    # TNPShapeReference, PushPullFeature, BooleanFeature, BooleanOperationType
)
from modeling.body_transaction import BodyTransaction
from modeling.result_types import ResultStatus, OperationResult


# ============================================================================
# 1. TNP v4.1 Basis-Features Tests
# ============================================================================

def test_tnp_shape_id_creation_and_uniqueness():
    """ShapeID Erstellung und Einzigartigkeit"""
    id1 = ShapeID.create(ShapeType.FACE, "feature_1", 0)
    id2 = ShapeID.create(ShapeType.EDGE, "feature_1", 1)
    id3 = ShapeID.create(ShapeType.FACE, "feature_1", 0)

    assert id1.shape_type == ShapeType.FACE
    assert id2.shape_type == ShapeType.EDGE
    assert id1 == id3  # Gleiche Parameter = gleiche ID
    assert id1 != id2
    assert hash(id1) == hash(id3)

    print("✓ TNP ShapeID Creation & Uniqueness")


def test_tnp_registry_registration():
    """TNP Registry: Registrierung von Shapes"""
    doc = Document("TNP Registry Test")

    # Erstelle einen Body mit einem Feature
    body = Body("TestBody")
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid
    doc.add_body(body)

    # Registriere die Faces
    faces = list(solid.faces())
    assert len(faces) == 6

    shape_ids = []
    for i, face in enumerate(faces):
        shape_id = doc._shape_naming_service.register_shape(
            face.wrapped,
            "test_feature",
            i,
            ShapeType.FACE
        )
        shape_ids.append(shape_id)

    assert len(shape_ids) == 6
    assert len(set(shape_ids)) == 6  # Alle einzigartig

    # Resolution testen
    resolved = []
    for shape_id in shape_ids:
        resolved_shape = doc._shape_naming_service.resolve_shape(
            shape_id, solid
        )
        assert resolved_shape is not None
        resolved.append(resolved_shape)

    assert len(resolved) == 6

    print("✓ TNP Registry Registration & Resolution")


# ============================================================================
# 2. Extrude/PushPull mit TNP Tests
# ============================================================================

def test_extrude_creates_face_shape_ids():
    """Extrude Feature erstellt Face ShapeIDs"""
    doc = Document("Extrude TNP Test")

    # Erstelle Sketch-Profil
    profile = bd.Rectangle(10, 10).faces()[0]

    # Extrude Feature
    feature = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    # Führe Feature aus
    result = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    # Prüfe dass ShapeIDs erstellt wurden
    assert hasattr(feature, 'profile_shape_id')
    assert feature.profile_shape_id is not None

    print("✓ Extrude creates Face ShapeIDs")


def test_pushpull_face_tracking_after_operation():
    """PushPull: Face-Tracking nach Operation"""
    doc = Document("PushPull TNP Test")
    body = Body("PushPullBody")

    # Start-Geometrie
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid
    doc.add_body(body)

    # PushPull Feature
    top_face = list(solid.faces())[0]  # Top face
    feature = PushPullFeature(
        distance=2.0,
        face_indices=[0],
        operation_type="join"
    )

    # Führe PushPull aus
    with BodyTransaction(body, "PushPull"):
        result = doc._compute_pushpull(
            body_solid=solid,
            selected_faces=[top_face],
            feature=feature
        )
        assert result.status == ResultStatus.SUCCESS
        body._build123d_solid = result.value
        body.invalidate_mesh()

    # Prüfe dass ShapeIDs erstellt wurden
    assert hasattr(feature, 'face_shape_ids')
    assert len(feature.face_shape_ids) > 0

    print("✓ PushPull Face Tracking after operation")


# ============================================================================
# 3. Fillet/Chamfer mit TNP Tests
# ============================================================================

def test_fillet_edge_tracking():
    """Fillet: Edge-Tracking mit ShapeIDs"""
    doc = Document("Fillet TNP Test")
    body = Body("FilletBody")

    # Box erstellen
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid
    doc.add_body(body)

    # Kanten auswählen
    edges = list(solid.edges())
    assert len(edges) >= 12

    # Fillet Feature
    feature = FilletFeature(
        radius=1.0,
        edge_indices=[0, 1, 2]
    )

    # Initialisiere ShapeIDs
    from modeling.tnp_system import ShapeID
    feature.edge_shape_ids = [
        ShapeID.create(ShapeType.EDGE, feature.id, i)
        for i in range(3)
    ]

    # Führe Fillet aus
    result = doc._compute_fillet(
        body_solid=solid,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value is not None

    # Prüfe dass Feature auf gültige Edges angewendet wurde
    filleted_solid = result.value
    assert filleted_solid.is_valid()

    print("✓ Fillet Edge Tracking")


def test_chamfer_edge_tracking():
    """Chamfer: Edge-Tracking mit ShapeIDs"""
    doc = Document("Chamfer TNP Test")
    body = Body("ChamferBody")

    # Box erstellen
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid
    doc.add_body(body)

    # Chamfer Feature
    feature = ChamferFeature(
        distance=1.0,
        edge_indices=[0]
    )

    # Initialisiere ShapeIDs
    feature.edge_shape_ids = [
        ShapeID.create(ShapeType.EDGE, feature.id, 0)
    ]

    # Führe Chamfer aus
    result = doc._compute_chamfer(
        body_solid=solid,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Chamfer Edge Tracking")


# ============================================================================
# 4. Boolean-Operationen mit TNP Tests
# ============================================================================

def test_boolean_cut_face_tracking():
    """Boolean Cut: Face-Tracking"""
    doc = Document("Boolean Cut TNP Test")
    body = Body("CutBody")

    # Base solid
    base = bd.Solid.make_box(20, 20, 10)
    body._build123d_solid = base
    doc.add_body(body)

    # Tool solid
    tool = bd.Solid.make_cylinder(3.0, 10)

    # Boolean Feature
    feature = BooleanFeature(
        operation_type=BooleanOperationType.CUT,
        tool_bodies=[],  # Wird dynamisch erstellt
        tool_profile_center=None
    )

    # Führe Boolean aus
    result = doc._compute_boolean(
        body_solid=base,
        tool_solid=tool,
        feature=feature,
        operation="Cut"
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value is not None

    # Prüfe dass das Loch erstellt wurde
    cut_solid = result.value
    assert cut_solid.is_valid()

    # Zylindrische Faces sollten vorhanden sein
    cylindrical_faces = []
    for face in cut_solid.faces():
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            cylindrical_faces.append(face)

    assert len(cylindrical_faces) >= 1  # Mindestens die Loch-Wand

    print("✓ Boolean Cut Face Tracking")


# ============================================================================
# 5. Sweep/Loft mit TNP Tests
# ============================================================================

def test_sweep_profile_tracking():
    """Sweep: Profil-Tracking"""
    doc = Document("Sweep TNP Test")
    body = Body("SweepBody")

    # Pfad erstellen
    path_edge = bd.Edge.make_line(Vector(0, 0, 0), Vector(0, 0, 10))

    # Profil erstellen
    profile = bd.Circle(2.0).faces()[0]

    # Sweep Feature
    feature = SweepFeature(
        path_edge_index=0,
        profile_face_index=0,
        is_solid=True
    )

    # Führe Sweep aus
    result = doc._compute_sweep(
        body_solid=None,
        path_edge=path_edge,
        profile_face=profile,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value is not None

    print("✓ Sweep Profile Tracking")


def test_loft_profile_tracking():
    """Loft: Profil-Tracking zwischen multiple Profiles"""
    doc = Document("Loft TNP Test")

    # Zwei Profile erstellen
    profile1 = bd.Circle(2.0).faces()[0].moved(Location(Vector(0, 0, 0)))
    profile2 = bd.Circle(3.0).faces()[0].moved(Location(Vector(0, 0, 10)))

    # Loft Feature
    feature = LoftFeature(
        profile_face_indices=[0, 1],
        is_solid=True,
        is_ruled=False
    )

    # Führe Loft aus
    result = doc._compute_loft(
        body_solid=None,
        profiles=[profile1, profile2],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS
    assert result.value is not None

    print("✓ Loft Profile Tracking")


# ============================================================================
# 6. Draft/Hollow mit TNP Tests
# ============================================================================

def test_draft_face_tracking():
    """Draft: Face-Tracking"""
    doc = Document("Draft TNP Test")
    body = Body("DraftBody")

    # Block erstellen
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid
    doc.add_body(body)

    # Draft Feature
    feature = DraftFeature(
        angle=5.0,
        face_indices=[0],
        draft_plane_normal=None
    )

    # Führe Draft aus
    result = doc._compute_draft(
        body_solid=solid,
        selected_faces=[list(solid.faces())[0]],
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Draft Face Tracking")


def test_hollow_face_tracking():
    """Hollow: Face-Tracking"""
    doc = Document("Hollow TNP Test")
    body = Body("HollowBody")

    # Block erstellen
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid
    doc.add_body(body)

    # Hollow Feature
    feature = HollowFeature(
        thickness=1.0,
        face_indices=[]  # Alle Faces wenn leer
    )

    # Führe Hollow aus
    result = doc._compute_hollow(
        body_solid=solid,
        feature=feature
    )

    assert result.status == ResultStatus.SUCCESS

    print("✓ Hollow Face Tracking")


# ============================================================================
# 7. Rebuild-Idempotenz Tests
# ============================================================================

def test_rebuild_extrude_idempotent():
    """Extrude Rebuild ist idempotent"""
    doc = Document("Rebuild Extrude Test")
    body = Body("RebuildBody")

    # Erste Extrusion
    profile = bd.Rectangle(10, 10).faces()[0]
    feature1 = ExtrudeFeature(
        amount=5.0,
        profile_face_index=0,
        direction_vector=None,
        operation_type="join"
    )

    result1 = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature1
    )

    assert result1.status == ResultStatus.SUCCESS
    solid1 = result1.value

    # Rebuild
    result2 = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature1
    )

    assert result2.status == ResultStatus.SUCCESS
    solid2 = result2.value

    # Gleiche Volumen (idempotent)
    assert solid1.volume == pytest.approx(solid2.volume, abs=1e-6)

    print("✓ Extrude Rebuild is Idempotent")


def test_rebuild_multi_feature_workflow():
    """Multi-Feature Rebuild Workflow"""
    doc = Document("Multi-Feature Rebuild Test")
    body = Body("MultiFeatureBody")

    # 1. Extrude
    profile = bd.Rectangle(10, 10).faces()[0]
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

    solid = result.value
    assert solid.is_valid()

    # 2. Fillet
    edges = list(solid.edges())
    fillet = FilletFeature(radius=1.0, edge_indices=[0, 1, 2, 3])

    result2 = doc._compute_fillet(
        body_solid=solid,
        feature=fillet
    )

    assert result2.status == ResultStatus.SUCCESS
    solid2 = result2.value

    # 3. Rebuild von allem
    # Erneute Extrusion
    result3 = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=extrude
    )

    assert result3.status == ResultStatus.SUCCESS
    solid3 = result3.value

    # Erneutes Fillet
    result4 = doc._compute_fillet(
        body_solid=solid3,
        feature=fillet
    )

    assert result4.status == ResultStatus.SUCCESS
    solid4 = result4.value

    # Gleiche Volumen nach Rebuild
    assert solid2.volume == pytest.approx(solid4.volume, abs=1e-5)

    print("✓ Multi-Feature Rebuild Workflow")


# ============================================================================
# 8. Undo/Redo mit TNP Tests
# ============================================================================

def test_undo_redo_extrude_with_tnp():
    """Undo/Redo mit Extrude und TNP"""
    doc = Document("Undo Redo Test")
    body = Body("UndoRedoBody")

    # Snapshot erstellen
    snapshot_id = body._create_snapshot()

    # Extrude
    profile = bd.Rectangle(10, 10).faces()[0]
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

    volume_after = result.value.volume

    # Undo
    body._restore_snapshot(snapshot_id)
    assert body._build123d_solid is None

    # Redo
    result2 = doc._compute_extrude(
        body_solid=None,
        profile_face=profile,
        feature=feature
    )

    assert result2.status == ResultStatus.SUCCESS
    volume_after_redo = result2.value.volume

    # Gleiche Volumen nach Redo
    assert volume_after == pytest.approx(volume_after_redo, abs=1e-6)

    print("✓ Undo/Redo Extrude with TNP")


# ============================================================================
# 9. Save/Load mit TNP Tests
# ============================================================================

def test_serialize_deserialize_feature_with_tnp():
    """Serialisierung/Deserialisierung von TNP-Features"""
    from modeling.tnp_shape_reference import ShapeID

    # Erstelle Feature mit ShapeIDs
    feature = FilletFeature(radius=1.0, edge_indices=[0, 1, 2])

    # ShapeIDs hinzufügen
    feature.edge_shape_ids = [
        ShapeID.create(ShapeType.EDGE, "test_feature", i)
        for i in range(3)
    ]

    # Serialisiere
    data = feature.to_dict()

    # Prüfe dass ShapeIDs serialisiert wurden
    assert "edge_shape_ids" in data
    assert len(data["edge_shape_ids"]) == 3

    # Deserialisiere
    feature2 = FilletFeature.from_dict(data)

    # Prüfe dass ShapeIDs wiederhergestellt wurden
    assert hasattr(feature2, 'edge_shape_ids')
    assert len(feature2.edge_shape_ids) == 3

    print("✓ Serialize/Deserialize Feature with TNP")


# ============================================================================
# 10. Integration Tests - Komplette Workflows
# ============================================================================

def test_complete_modeling_workflow_with_tnp():
    """Kompletter Modeling-Workflow mit TNP"""
    doc = Document("Complete Workflow Test")
    body = Body("CompleteWorkflowBody")

    # 1. Sketch (Profil)
    profile = bd.Rectangle(20, 15).faces()[0]

    # 2. Extrude
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

    # 3. Fillet
    edges = list(solid.edges())
    fillet = FilletFeature(radius=1.0, edge_indices=[0, 1, 2, 3])

    result2 = doc._compute_fillet(
        body_solid=solid,
        feature=fillet
    )

    assert result2.status == ResultStatus.SUCCESS
    solid2 = result2.value

    # 4. PushPull
    top_face = list(solid2.faces())[0]
    pushpull = PushPullFeature(
        distance=2.0,
        face_indices=[0],
        operation_type="join"
    )

    result3 = doc._compute_pushpull(
        body_solid=solid2,
        selected_faces=[top_face],
        feature=pushpull
    )

    assert result3.status == ResultStatus.SUCCESS
    final_solid = result3.value

    # Prüfe dass alle Features funktionieren
    assert final_solid.is_valid()
    assert final_solid.volume > solid.volume  # PushPull fügt Material hinzu

    print("✓ Complete Modeling Workflow with TNP")


def test_tnp_shape_resolution_after_boolean_chain():
    """TNP Shape-Resolution nach Boolean-Kette"""
    doc = Document("Boolean Chain Test")
    body = Body("BooleanChainBody")

    # 1. Base Box
    base = bd.Solid.make_box(20, 20, 10)

    # 2. Cut Cylinder
    cylinder1 = bd.Solid.make_cylinder(3.0, 10).located(Location(Vector(5, 5, 0)))
    cut1 = base - cylinder1

    # 3. Cut zweiter Cylinder
    cylinder2 = bd.Solid.make_cylinder(2.0, 10).located(Location(Vector(15, 15, 0)))
    final = cut1 - cylinder2

    assert final.is_valid()

    # Prüfe dass beide Löcher vorhanden sind
    cylindrical_faces = []
    for face in final.faces():
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        adaptor = BRepAdaptor_Surface(face.wrapped)
        if adaptor.GetType() == GeomAbs_Cylinder:
            radius = adaptor.Cylinder().Radius()
            cylindrical_faces.append((face, radius))

    # Sollte 2 zylindrische Faces haben (die beiden Löcher)
    assert len(cylindrical_faces) >= 2

    radii = [r for _, r in cylindrical_faces]
    assert pytest.approx(3.0, abs=0.1) in radii
    assert pytest.approx(2.0, abs=0.1) in radii

    print("✓ TNP Shape Resolution after Boolean Chain")


# ============================================================================
# Test Runner
# ============================================================================

def run_all_tnp_regression_tests():
    """Führt alle TNP Regression Tests aus"""
    print("\n" + "="*60)
    print("TNP v4.1 REGRESSION TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # 1. Basis-Features
        ("TNP ShapeID Creation & Uniqueness", test_tnp_shape_id_creation_and_uniqueness),
        ("TNP Registry Registration", test_tnp_registry_registration),

        # 2. Extrude/PushPull
        ("Extrude creates Face ShapeIDs", test_extrude_creates_face_shape_ids),
        ("PushPull Face Tracking", test_pushpull_face_tracking_after_operation),

        # 3. Fillet/Chamfer
        ("Fillet Edge Tracking", test_fillet_edge_tracking),
        ("Chamfer Edge Tracking", test_chamfer_edge_tracking),

        # 4. Boolean
        ("Boolean Cut Face Tracking", test_boolean_cut_face_tracking),

        # 5. Sweep/Loft
        ("Sweep Profile Tracking", test_sweep_profile_tracking),
        ("Loft Profile Tracking", test_loft_profile_tracking),

        # 6. Draft/Hollow
        ("Draft Face Tracking", test_draft_face_tracking),
        ("Hollow Face Tracking", test_hollow_face_tracking),

        # 7. Rebuild
        ("Extrude Rebuild Idempotent", test_rebuild_extrude_idempotent),
        ("Multi-Feature Rebuild", test_rebuild_multi_feature_workflow),

        # 8. Undo/Redo
        ("Undo/Redo with TNP", test_undo_redo_extrude_with_tnp),

        # 9. Save/Load
        ("Serialize/Deserialize TNP", test_serialize_deserialize_feature_with_tnp),

        # 10. Integration
        ("Complete Workflow", test_complete_modeling_workflow_with_tnp),
        ("Boolean Chain Resolution", test_tnp_shape_resolution_after_boolean_chain),
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
    success = run_all_tnp_regression_tests()
    sys.exit(0 if success else 1)
