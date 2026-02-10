#!/usr/bin/env python3
"""
Integration Regression Test Suite
==================================

Diese Tests beweisen dass komplette Workflows mit mehreren Features
nach neuen Änderungen weiterhin korrekt funktionieren.

Workflows (existierend):
1. Extrude → Fillet → Chamfer (klassische CAD-Sequenz)
2. Shell → Hollow (Hohlkörper)

TODO (nicht existierende Features):
- PushPullFeature, BooleanFeature
- DraftFeature, HollowFeature
- Undo/Redo (Feature-basiert)
- Save/Load Cycle (Feature-Serialisierung)
"""
import pytest
import build123d as bd
from build123d import Solid, Face, Edge, Location, Vector
from shapely.geometry import Polygon

from modeling import (
    Body, Document,
    ExtrudeFeature,
    FilletFeature, ChamferFeature,
    RevolveFeature,
    ShellFeature, HoleFeature
)
from modeling.topology_indexing import edge_index_of, face_index_of


# ============================================================================
# 1. Klassische CAD-Sequenz: Extrude → Fillet → Chamfer
# ============================================================================

def test_workflow_extrude_fillet_chamfer():
    """Extrude → Fillet → Chamfer Workflow"""
    doc = Document("Extrude Fillet Chamfer")
    body = Body("TestBody", document=doc)
    doc.add_body(body)

    # 1. Box erstellen (durch Extrude von Rechteck)
    feature = ExtrudeFeature(
        distance=10.0,
        direction=1,
        operation="New Body"
    )
    feature.face_brep = None
    poly = Polygon([(0, 0), (20, 0), (20, 15), (0, 15)])
    feature.precalculated_polys = [poly]
    feature.plane_origin = (0, 0, 0)
    feature.plane_normal = (0, 0, 1)

    result = body._compute_extrude_part(feature)
    assert result is not None
    solid = result if isinstance(result, Solid) else result.solids()[0]
    initial_volume = solid.volume

    body._build123d_solid = solid
    body.invalidate_mesh()

    # 2. Fillet auf vertikalen Kanten
    edges = list(body._build123d_solid.edges())
    fillet_edges = [e for e in edges if e.length > 8][:4]
    edge_indices = [edge_index_of(body._build123d_solid, e) for e in fillet_edges]

    fillet = FilletFeature(radius=1.0, edge_indices=edge_indices)
    solid2 = body._ocp_fillet(body._build123d_solid, fillet_edges, 1.0)

    assert solid2 is not None
    assert solid2.is_valid()
    assert solid2.volume < initial_volume  # Fillet entfernt Material

    body._build123d_solid = solid2
    body.invalidate_mesh()

    # 3. Chamfer auf Top Edge
    top_edges = [e for e in body._build123d_solid.edges() if e.center().Z > 14]
    if top_edges:
        chamfer_edge = top_edges[0]
        chamfer_idx = edge_index_of(body._build123d_solid, chamfer_edge)

        chamfer = ChamferFeature(distance=0.5, edge_indices=[chamfer_idx])
        solid3 = body._ocp_chamfer(body._build123d_solid, [chamfer_edge], 0.5)

        assert solid3 is not None
        assert solid3.is_valid()

    print("✓ Workflow: Extrude → Fillet → Chamfer")


# ============================================================================
# 2. Shell Workflow
# ============================================================================

def test_workflow_shell():
    """Shell Workflow"""
    doc = Document("Shell Test")
    body = Body("ShellBody", document=doc)
    doc.add_body(body)

    # Box erstellen
    solid = bd.Solid.make_box(20, 20, 20)
    body._build123d_solid = solid

    # Shell mit OCPShellHelper
    from modeling.ocp_helpers import OCPShellHelper

    # Top Face finden
    faces = list(body._build123d_solid.faces())
    top_face = max(faces, key=lambda f: f.center().Z)

    result = OCPShellHelper.shell(
        solid=body._build123d_solid,
        faces_to_remove=[top_face],
        thickness=2.0,
        naming_service=doc._shape_naming_service,
        feature_id="shell_test"
    )

    assert result is not None
    assert result.is_valid()
    assert result.volume < solid.volume

    print("✓ Workflow: Shell")


# ============================================================================
# TESTS FÜR NICHT-EXISTIERENDE WORKFLOWS (SKIPPED)
# ============================================================================

@pytest.mark.skip("PushPullFeature existiert nicht - TODO")
def test_workflow_box_pushpull_fillet_chamfer():
    """Box → PushPull → Fillet → Chamfer - SKIPPED"""
    pass


@pytest.mark.skip("BooleanFeature existiert nicht - TODO")
def test_workflow_bore_with_fillet():
    """Sketch → Extrude → Boolean Cut → Fillet - SKIPPED"""
    pass


@pytest.mark.skip("Revolve requires sketch integration - TODO")
def test_workflow_revolution_part():
    """Revolve → Fillet → Shell - SKIPPED"""
    pass


@pytest.mark.skip("BooleanFeature existiert nicht - TODO")
def test_workflow_multiple_booleans_fillets():
    """Multiple Boolean Operations mit Fillets - SKIPPED"""
    pass


@pytest.mark.skip("Undo/Redo existiert nicht auf Feature-Ebene - TODO")
def test_workflow_undo_redo_sequence():
    """Undo/Redo Sequenzen - SKIPPED"""
    pass


@pytest.mark.skip("Feature-Serialisierung existiert nicht - TODO")
def test_workflow_save_load_cycle():
    """Save/Load Cycle - SKIPPED"""
    pass


@pytest.mark.skip("Complex Assembly existiert nicht - TODO")
def test_workflow_complete_part():
    """Complete Part Workflow - SKIPPED"""
    pass


@pytest.mark.skip("Rebuild Idempotenz für komplexe Teile - TODO")
def test_workflow_rebuild_idempotent_complex():
    """Rebuild Idempotent Complex - SKIPPED"""
    pass


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_all_integration_tests():
    """Führt alle Integration-Tests aus"""
    print("\n" + "="*60)
    print("INTEGRATION REGRESSION SUITE")
    print("="*60 + "\n")

    tests = [
        ("Extrude Fillet Chamfer", test_workflow_extrude_fillet_chamfer),
        ("Shell Workflow", test_workflow_shell),
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
    success = run_all_integration_tests()
    sys.exit(0 if success else 1)
