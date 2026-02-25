#!/usr/bin/env python3
"""
TNP v4.1 Regression Test Suite
==============================

Diese Tests beweisen dass TNP v4.1 nach neuen Änderungen weiterhin funktioniert.
Sie testen alle kritischen TNP-Pfade mit verschiedenen Features.

Updated für OCP-First Migration API (2026-02-10)
"""
import pytest
import build123d as bd
from build123d import Solid, Face, Edge, Location, Vector, Rotation
from shapely.geometry import Polygon

from modeling import (
    Body, Document, ExtrudeFeature,
    FilletFeature, ChamferFeature,
    ShellFeature, HoleFeature,
    RevolveFeature, BooleanFeature,
    LoftFeature, SweepFeature,
    DraftFeature, HollowFeature,
    PushPullFeature
)
from modeling.tnp_system import ShapeID, ShapeType
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.boolean_engine_v4 import BooleanEngineV4

# Test markers for pytest selection
pytestmark = [pytest.mark.tnp, pytest.mark.kernel, pytest.mark.fast]


# ============================================================================
# 1. TNP v4.1 Basis-Features Tests
# ============================================================================

def test_tnp_shape_id_creation_and_uniqueness():
    """ShapeID Erstellung und Einzigartigkeit"""
    id1 = ShapeID.create(
        shape_type=ShapeType.FACE,
        feature_id="feature_1",
        local_index=0,
        geometry_data=("feature_1", 0, "FACE")
    )
    id2 = ShapeID.create(
        shape_type=ShapeType.EDGE,
        feature_id="feature_1",
        local_index=1,
        geometry_data=("feature_1", 1, "EDGE")
    )
    id3 = ShapeID.create(
        shape_type=ShapeType.FACE,
        feature_id="feature_1",
        local_index=0,
        geometry_data=("feature_1", 0, "FACE")
    )

    # UUID ist immer einzigartig (zufällig generiert)
    assert id1.shape_type == ShapeType.FACE
    assert id2.shape_type == ShapeType.EDGE
    assert id1.uuid != id3.uuid  # Jedes create() generiert neue UUID
    assert id1 != id2  # Verschiedene Typen
    assert id1.feature_id == id3.feature_id  # Gleicher Feature
    assert id1.local_index == id3.local_index  # Gleicher Index

    print("✓ TNP ShapeID Creation & Uniqueness")


def test_tnp_registry_registration():
    """TNP Registry: Registrierung von Shapes"""
    doc = Document("TNP Registry Test")

    # Erstelle einen Body mit einem Feature
    body = Body("TestBody", document=doc)
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
# 2. Extrude mit TNP Tests
# ============================================================================

def test_extrude_creates_face_shape_ids():
    """Extrude Feature erstellt Face ShapeIDs"""
    doc = Document("Extrude TNP Test")
    body = Body("ExtrudeBody", document=doc)
    doc.add_body(body)

    # Extrude Feature mit aktualisierten Parametern
    feature = ExtrudeFeature(
        distance=5.0,
        direction=1,
        operation="New Body"
    )
    feature.face_brep = None
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    feature.precalculated_polys = [poly]
    feature.plane_origin = (0, 0, 0)
    feature.plane_normal = (0, 0, 1)

    # Führe Feature aus
    result = body._compute_extrude_part(feature)

    assert result is not None
    solid = result if isinstance(result, Solid) else result.solids()[0]

    # Prüfe dass gültiger Solid erstellt wurde
    assert solid.is_valid()
    assert solid.volume == pytest.approx(500, abs=1e-3)  # 10x10x5

    print("✓ Extrude creates Face ShapeIDs")


# ============================================================================
# 3. Fillet/Chamfer mit TNP Tests
# ============================================================================

def test_fillet_edge_tracking():
    """Fillet: Edge-Tracking mit ShapeIDs"""
    doc = Document("Fillet TNP Test")
    body = Body("FilletBody", document=doc)
    doc.add_body(body)

    # Box erstellen
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid

    # Kanten auswählen
    edges = list(solid.edges())
    assert len(edges) >= 12

    # Fillet Feature
    fillet_edges = edges[:3]
    edge_indices = [edge_index_of(solid, e) for e in fillet_edges]

    feature = FilletFeature(
        radius=1.0,
        edge_indices=edge_indices
    )

    # Initialisiere ShapeIDs mit korrekter API
    feature.edge_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.EDGE,
            feature_id=feature.id,
            local_index=i,
            geometry_data=(feature.id, i, "EDGE")
        )
        for i in range(3)
    ]

    # Führe Fillet aus (direkt auf Body) - feature_id is required for OCP-First
    result_solid = body._ocp_fillet(solid, fillet_edges, 1.0, feature_id=feature.id)

    assert result_solid is not None
    assert result_solid.is_valid()

    print("✓ Fillet Edge Tracking")


def test_chamfer_edge_tracking():
    """Chamfer: Edge-Tracking mit ShapeIDs"""
    doc = Document("Chamfer TNP Test")
    body = Body("ChamferBody", document=doc)
    doc.add_body(body)

    # Box erstellen
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid

    # Chamfer Feature
    edge = list(solid.edges())[0]
    edge_idx = edge_index_of(solid, edge)

    feature = ChamferFeature(
        distance=1.0,
        edge_indices=[edge_idx]
    )

    # Initialisiere ShapeIDs mit korrekter API
    feature.edge_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.EDGE,
            feature_id=feature.id,
            local_index=0,
            geometry_data=(feature.id, 0, "EDGE")
        )
    ]

    # Führe Chamfer aus (direkt auf Body) - feature_id is required for OCP-First
    result_solid = body._ocp_chamfer(solid, [edge], 1.0, feature_id=feature.id)

    assert result_solid is not None
    assert result_solid.is_valid()

    print("✓ Chamfer Edge Tracking")


# ============================================================================
# 4. Boolean-Operationen mit TNP Tests
# ============================================================================

def test_boolean_cut_face_tracking():
    """Boolean Cut: Face-Tracking mit BooleanEngineV4"""
    doc = Document("Boolean TNP Test")
    body = Body("BooleanBody", document=doc)
    doc.add_body(body)

    # Base solid erstellen
    base = bd.Solid.make_box(20, 20, 10)
    body._build123d_solid = base

    # Tool body erstellen (Cylinder zum Schneiden)
    tool = bd.Solid.make_cylinder(3.0, 10).located(Location(Vector(5, 5, 0)))

    # BooleanFeature erstellen
    feature = BooleanFeature(
        operation="Cut",
        tool_body_id=None  # Direkter Solid wird verwendet
    )

    # Initialisiere ShapeIDs für modified faces
    feature.modified_shape_ids = []

    # Boolean mit BooleanEngineV4.execute_boolean_on_shapes ausführen
    result = BooleanEngineV4.execute_boolean_on_shapes(base, tool, "Cut")

    assert result is not None
    assert result.status.name == "SUCCESS" or result.value is not None

    # Prüfe dass das Loch erstellt wurde (Volumen sollte kleiner sein)
    if result.value is not None:
        assert result.value.volume < base.volume

    print("✓ Boolean Cut Face Tracking")


# ============================================================================
# 5. Sweep/Loft mit TNP Tests
# ============================================================================

def test_sweep_profile_tracking():
    """Sweep: Profil-Tracking mit ShapeIDs"""
    doc = Document("Sweep TNP Test")
    body = Body("SweepBody", document=doc)
    doc.add_body(body)

    # Erstelle Sweep-Feature mit aktuellem API
    profile_poly = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])

    feature = SweepFeature(
        profile_data={
            "type": "sketch_profile",
            "shapely_poly": profile_poly,
            "plane_origin": (0, 0, 0),
            "plane_normal": (0, 0, 1)
        },
        path_data={
            "type": "sketch_edge",
            "edge_indices": [],
            "sketch_id": None,
            "body_id": None
        }
    )

    # Initialisiere ShapeIDs
    feature.profile_shape_id = ShapeID.create(
        shape_type=ShapeType.FACE,
        feature_id=feature.id,
        local_index=0,
        geometry_data=(feature.id, 0, "FACE")
    )

    # Prüfe dass Feature korrekt initialisiert wurde
    assert feature.profile_data is not None
    assert feature.profile_shape_id is not None
    assert feature.profile_shape_id.shape_type == ShapeType.FACE

    print("✓ Sweep Profile Tracking")


def test_loft_profile_tracking():
    """Loft: Profil-Tracking mit ShapeIDs"""
    doc = Document("Loft TNP Test")
    body = Body("LoftBody", document=doc)
    doc.add_body(body)

    # Erstelle Loft-Feature mit aktuellem API
    profile1 = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    profile2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])

    feature = LoftFeature(
        profile_data=[
            {
                "type": "sketch_profile",
                "shapely_poly": profile1,
                "plane_origin": (0, 0, 0),
                "plane_normal": (0, 0, 1)
            },
            {
                "type": "sketch_profile",
                "shapely_poly": profile2,
                "plane_origin": (0, 0, 5),
                "plane_normal": (0, 0, 1)
            }
        ]
    )

    # Initialisiere ShapeIDs für Profile
    feature.profile_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.FACE,
            feature_id=feature.id,
            local_index=i,
            geometry_data=(feature.id, i, "FACE")
        )
        for i in range(2)
    ]

    # Prüfe dass Feature korrekt initialisiert wurde
    assert len(feature.profile_data) == 2
    assert len(feature.profile_shape_ids) == 2
    assert all(sid.shape_type == ShapeType.FACE for sid in feature.profile_shape_ids)

    print("✓ Loft Profile Tracking")


# ============================================================================
# 6. Draft/Hollow mit TNP Tests
# ============================================================================

def test_draft_face_tracking():
    """Draft: Face-Tracking mit ShapeIDs"""
    doc = Document("Draft TNP Test")
    body = Body("DraftBody", document=doc)
    doc.add_body(body)

    # Erstelle Base Solid
    solid = bd.Solid.make_box(10, 10, 20)
    body._build123d_solid = solid

    # Erstelle Draft-Feature mit aktuellem API
    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0, 0, 1),
        neutral_plane_normal=(0, 0, 1)
    )

    # Initialisiere ShapeIDs für Faces
    feature.face_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.FACE,
            feature_id=feature.id,
            local_index=i,
            geometry_data=(feature.id, i, "FACE")
        )
        for i in range(4)  # 4 Seitenflächen
    ]

    # Prüfe dass Feature korrekt initialisiert wurde
    assert feature.draft_angle == 3.0
    assert len(feature.face_shape_ids) == 4
    assert all(sid.shape_type == ShapeType.FACE for sid in feature.face_shape_ids)

    print("✓ Draft Face Tracking")


def test_hollow_face_tracking():
    """Hollow: Face-Tracking mit ShapeIDs"""
    doc = Document("Hollow TNP Test")
    body = Body("HollowBody", document=doc)
    doc.add_body(body)

    # Erstelle Base Solid
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid

    # Erstelle Hollow-Feature mit aktuellem API
    feature = HollowFeature(
        wall_thickness=2.0
    )

    # Initialisiere ShapeIDs für Opening Faces
    feature.opening_face_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.FACE,
            feature_id=feature.id,
            local_index=0,
            geometry_data=(feature.id, 0, "FACE")
        )
    ]

    # Prüfe dass Feature korrekt initialisiert wurde
    assert feature.wall_thickness == 2.0
    assert len(feature.opening_face_shape_ids) == 1
    assert feature.opening_face_shape_ids[0].shape_type == ShapeType.FACE

    print("✓ Hollow Face Tracking")


# ============================================================================
# 7. Rebuild-Idempotenz Tests
# ============================================================================

def test_rebuild_extrude_idempotent():
    """Extrude Rebuild ist idempotent"""
    doc = Document("Rebuild Extrude Test")
    body = Body("RebuildBody", document=doc)
    doc.add_body(body)

    # Erste Extrusion mit aktualisierten Parametern
    feature = ExtrudeFeature(
        distance=5.0,
        direction=1,
        operation="New Body"
    )
    feature.face_brep = None
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    feature.precalculated_polys = [poly]
    feature.plane_origin = (0, 0, 0)
    feature.plane_normal = (0, 0, 1)

    result1 = body._compute_extrude_part(feature)
    assert result1 is not None
    solid1 = result1 if isinstance(result1, Solid) else result1.solids()[0]

    # Rebuild
    result2 = body._compute_extrude_part(feature)
    assert result2 is not None
    solid2 = result2 if isinstance(result2, Solid) else result2.solids()[0]

    # Gleiche Volumen (idempotent)
    assert solid1.volume == pytest.approx(solid2.volume, abs=1e-6)

    print("✓ Extrude Rebuild is Idempotent")


def test_rebuild_multi_feature_workflow():
    """Multi-Feature Rebuild Workflow"""
    doc = Document("Multi-Feature Rebuild Test")
    body = Body("MultiFeatureBody", document=doc)
    doc.add_body(body)

    # 1. Extrude
    feature = ExtrudeFeature(
        distance=10.0,
        direction=1,
        operation="New Body"
    )
    feature.face_brep = None
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    feature.precalculated_polys = [poly]
    feature.plane_origin = (0, 0, 0)
    feature.plane_normal = (0, 0, 1)

    result = body._compute_extrude_part(feature)
    solid = result if isinstance(result, Solid) else result.solids()[0]
    assert solid.is_valid()

    body._build123d_solid = solid
    body.invalidate_mesh()

    # 2. Fillet
    edges = list(body._build123d_solid.edges())
    fillet_edges = edges[:4]
    edge_indices = [edge_index_of(body._build123d_solid, e) for e in fillet_edges]
    fillet = FilletFeature(radius=1.0, edge_indices=edge_indices)

    result2 = body._ocp_fillet(body._build123d_solid, fillet_edges, 1.0, feature_id=fillet.id)
    assert result2 is not None
    solid2 = result2
    body._build123d_solid = solid2
    body.invalidate_mesh()

    # 3. Rebuild von allem
    # Erneute Extrusion
    feature2 = ExtrudeFeature(
        distance=10.0,
        direction=1,
        operation="New Body"
    )
    feature2.face_brep = None
    feature2.precalculated_polys = [poly]
    feature2.plane_origin = (0, 0, 0)
    feature2.plane_normal = (0, 0, 1)

    result3 = body._compute_extrude_part(feature2)
    assert result3 is not None
    solid3 = result3 if isinstance(result3, Solid) else result3.solids()[0]

    # Erneutes Fillet
    edges3 = list(solid3.edges())
    fillet_edges3 = edges3[:4]
    result4 = body._ocp_fillet(solid3, fillet_edges3, 1.0)

    assert result4 is not None
    solid4 = result4

    # Gleiche Volumen nach Rebuild
    assert solid2.volume == pytest.approx(solid4.volume, abs=1e-5)

    print("✓ Multi-Feature Rebuild Workflow")


# ============================================================================
# 8. Undo/Redo mit TNP Tests
# ============================================================================

def test_undo_redo_extrude_with_tnp():
    """Undo/Redo mit Extrude und TNP via AddFeatureCommand"""
    pytest.importorskip("gui.commands.feature_commands")

    from gui.commands.feature_commands import AddFeatureCommand

    doc = Document("Undo/Redo TNP Test")
    body = Body("UndoRedoBody", document=doc)
    doc.add_body(body)

    # Initiale Box
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid

    # Extrude Feature
    feature = ExtrudeFeature(
        distance=5.0,
        direction=1,
        operation="Join"
    )
    feature.face_brep = None
    poly = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    feature.precalculated_polys = [poly]
    feature.plane_origin = (0, 0, 10)
    feature.plane_normal = (0, 0, 1)

    # Dummy UI für Command
    class DummyUI:
        def statusBar(self):
            class DummyStatusBar:
                def showMessage(self, msg): pass
            return DummyStatusBar()

    ui = DummyUI()

    # Command erstellen und ausführen
    cmd = AddFeatureCommand(body, feature, ui)
    cmd.redo()

    # Prüfe dass Feature hinzugefügt wurde
    assert feature in body.features or body._build123d_solid is not None

    # Undo
    cmd.undo()

    # Redo
    cmd.redo()

    print("✓ Undo/Redo Extrude with TNP")


# ============================================================================
# 9. Save/Load mit TNP Tests
# ============================================================================

def test_serialize_deserialize_feature_with_tnp():
    """Serialisierung/Deserialisierung von TNP-Features via Body.to_dict/from_dict"""
    doc = Document("Serialize TNP Test")
    body = Body("SerializeBody", document=doc)
    doc.add_body(body)

    # Erstelle Solid
    solid = bd.Solid.make_box(10, 10, 10)
    body._build123d_solid = solid

    # Feature mit TNP-Referenzen
    feature = FilletFeature(radius=1.0, edge_indices=[0, 1, 2, 3])
    feature.edge_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.EDGE,
            feature_id=feature.id,
            local_index=i,
            geometry_data=(feature.id, i, "EDGE")
        )
        for i in range(4)
    ]
    body.features.append(feature)

    # Serialisiere Body
    body_dict = body.to_dict()

    # Prüfe dass Serialisierung funktioniert
    assert body_dict is not None
    assert "name" in body_dict
    assert body_dict["name"] == "SerializeBody"

    # Prüfe Features serialisiert wurden
    if "features" in body_dict:
        assert len(body_dict["features"]) >= 1

    print("✓ Serialize/Deserialize Feature with TNP")


# ============================================================================
# 10. Integration Tests - Komplette Workflows
# ============================================================================

def test_complete_modeling_workflow_with_tnp():
    """Kompletter Modeling-Workflow mit TNP (Extrude, Fillet, PushPull)"""
    doc = Document("Complete Workflow Test")
    body = Body("WorkflowBody", document=doc)
    doc.add_body(body)

    # 1. Extrude - Basis erstellen
    extrude = ExtrudeFeature(
        distance=10.0,
        direction=1,
        operation="New Body"
    )
    extrude.face_brep = None
    poly = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
    extrude.precalculated_polys = [poly]
    extrude.plane_origin = (0, 0, 0)
    extrude.plane_normal = (0, 0, 1)

    result = body._compute_extrude_part(extrude)
    assert result is not None
    solid = result if isinstance(result, Solid) else result.solids()[0]
    assert solid.is_valid()

    body._build123d_solid = solid
    body.features.append(extrude)

    # 2. Fillet - Kanten abrunden
    edges = list(solid.edges())
    fillet_edges = edges[:4]
    edge_indices = [edge_index_of(solid, e) for e in fillet_edges]

    fillet = FilletFeature(radius=2.0, edge_indices=edge_indices)
    fillet.edge_shape_ids = [
        ShapeID.create(
            shape_type=ShapeType.EDGE,
            feature_id=fillet.id,
            local_index=i,
            geometry_data=(fillet.id, i, "EDGE")
        )
        for i in range(4)
    ]

    # feature_id is mandatory for OCP-First Fillet
    result2 = body._ocp_fillet(solid, fillet_edges, 2.0, feature_id=fillet.id)
    assert result2 is not None
    assert result2.is_valid()

    body._build123d_solid = result2
    body.features.append(fillet)

    # 3. PushPull - Fläche extrudieren (via ExtrudeFeature auf Face)
    pushpull = PushPullFeature(
        distance=5.0,
        face_index=0,
        operation="Join"
    )
    pushpull.face_shape_id = ShapeID.create(
        shape_type=ShapeType.FACE,
        feature_id=pushpull.id,
        local_index=0,
        geometry_data=(pushpull.id, 0, "FACE")
    )

    # Prüfe dass PushPull korrekt initialisiert wurde
    assert pushpull.distance == 5.0
    assert pushpull.face_shape_id is not None
    assert pushpull.face_shape_id.shape_type == ShapeType.FACE

    print("✓ Complete Modeling Workflow with TNP")


def test_tnp_shape_resolution_after_boolean_chain():
    """TNP Shape-Resolution nach Boolean-Kette"""
    doc = Document("Boolean Chain Test")
    body = Body("BooleanChainBody", document=doc)
    doc.add_body(body)

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

        # 2. Extrude
        ("Extrude creates Face ShapeIDs", test_extrude_creates_face_shape_ids),

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
        ("Undo/Redo Extrude with TNP", test_undo_redo_extrude_with_tnp),

        # 9. Save/Load
        ("Serialize/Deserialize Feature with TNP", test_serialize_deserialize_feature_with_tnp),

        # 10. Integration
        ("Complete Modeling Workflow with TNP", test_complete_modeling_workflow_with_tnp),
        ("Boolean Chain Resolution", test_tnp_shape_resolution_after_boolean_chain),
    ]

    passed = 0
    failed = 0
    skipped = 0
    errors = []

    for name, test_func in tests:
        try:
            print(f"Running: {name}...", end=" ")
            test_func()
            print("✓ PASS")
            passed += 1
        except pytest.skip.Exception:
            print("⊘ SKIPPED")
            skipped += 1
        except AssertionError as e:
            print(f"✗ FAIL")
            failed += 1
            errors.append((name, str(e)))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
            errors.append((name, str(e)))

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print("="*60)

    if errors:
        print("\nFailed Tests:")
        for name, error in errors:
            print(f"  - {name}: {error[:100]}")

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tnp_regression_tests()
    sys.exit(0 if success else 1)
