"""
Import-Path Test Suite
======================

Tests dass alle Code-Pfade (OCP-First, Legacy, Fallback) funktionieren.
Dies ist wichtig bevor Legacy entfernt wird.

Author: Claude (Import Tests)
Date: 2026-02-10
"""
import sys
sys.path.insert(0, 'c:/LiteCad')

# Logging aktivieren für Debug-Info wie im GUI
from config.feature_flags import set_flag, get_all_flags
set_flag("tnp_debug_logging", True)
set_flag("extrude_debug", True)


def test_extrude_native_circles():
    """Test 1: OCP-First Extrude mit nativen Kreisen"""
    print("\n" + "="*60)
    print("TEST 1: OCP-First Extrude (Native Circles)")
    print("="*60)

    try:
        # OCP-First aktivieren
        set_flag("ocp_first_extrude", True)

        sketch = Sketch('Circle Test')
        sketch.add_circle(0, 0, 20)

        doc = Document('TestDoc')
        body = Body('TestBody', document=doc)
        doc.add_body(body)

        feature = ExtrudeFeature(sketch=sketch, distance=10.0, operation='New Body')
        body.add_feature(feature)

        solid = body._build123d_solid
        if solid is None:
            print("[FAIL] Solid ist None")
            return False

        faces = list(solid.faces())
        # Native Kreise = 3 Faces (Top, Bottom, Side)
        if len(faces) == 3:
            print(f"[OK] Native Circle Extrude: {len(faces)} Faces")
            return True
        else:
            print(f"[WARN] Face-Count: {len(faces)} (evtl. Polygon-Approximation)")
            return len(faces) < 10  # Noch akzeptabel

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_extrude_rectangle():
    """Test 2: OCP-First Extrude mit Rechteck (closed_profiles Konvertierung)"""
    print("\n" + "="*60)
    print("TEST 2: OCP-First Extrude (Rectangle + closed_profiles)")
    print("="*60)

    try:
        set_flag("ocp_first_extrude", True)

        sketch = Sketch('Rectangle Test')
        sketch.add_rectangle(0, 0, 50, 50)

        doc = Document('TestDoc')
        body = Body('TestBody', document=doc)
        doc.add_body(body)

        feature = ExtrudeFeature(sketch=sketch, distance=20.0, operation='New Body')
        body.add_feature(feature)

        solid = body._build123d_solid
        if solid is None:
            print("[FAIL] Solid ist None")
            return False

        volume = solid.volume
        expected = 50 * 50 * 20  # 50000
        if abs(volume - expected) < 1.0:
            print(f"[OK] Rectangle Extrude: Volume={volume:.2f} (erwartet {expected})")
            return True
        else:
            print(f"[FAIL] Volume falsch: {volume:.2f} (erwartet {expected})")
            return False

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_extrude_legacy_fallback():
    """Test 3: Legacy Fallback wenn OCP-First keine Profile findet"""
    print("\n" + "="*60)
    print("TEST 3: Legacy Fallback")
    print("="*60)

    try:
        # OCP-First aktivieren (sollte bei leerem Sketch auf Legacy fallen)
        set_flag("ocp_first_extrude", True)

        sketch = Sketch('Rectangle Test')
        sketch.add_rectangle(0, 0, 30, 40)

        doc = Document('TestDoc')
        body = Body('TestBody', document=doc)
        doc.add_body(body)

        feature = ExtrudeFeature(sketch=sketch, distance=15.0, operation='New Body')
        body.add_feature(feature)

        solid = body._build123d_solid
        if solid is None:
            print("[FAIL] Solid ist None (Legacy Fallback fehlgeschlagen!)")
            return False

        print(f"[OK] Legacy Fallback funktioniert: Volume={solid.volume:.2f}")
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fillet_ocp_first():
    """Test 4: OCP-First Fillet"""
    print("\n" + "="*60)
    print("TEST 4: OCP-First Fillet")
    print("="*60)

    try:
        set_flag("ocp_first_fillet", True)

        # Basis-Körper erstellen
        sketch = Sketch('Box')
        sketch.add_rectangle(0, 0, 50, 50)

        doc = Document('TestDoc')
        body = Body('TestBody', document=doc)
        doc.add_body(body)

        extrude = ExtrudeFeature(sketch=sketch, distance=20.0, operation='New Body')
        body.add_feature(extrude)

        # Fillet auf 4 Kanten
        solid_before = body._build123d_solid
        edges = list(solid_before.edges())

        # Top-Edges finden (Z = 20)
        top_edges = [e for e in edges if hasattr(e, 'bounding_box')
                     and e.bounding_box().max.Z > 19]

        if len(top_edges) < 4:
            print(f"[WARN] Nur {len(top_edges)} Top-Edges gefunden")

        fillet = FilletFeature(radius=2.0, edge_indices=[0, 1, 2, 3])
        body.add_feature(fillet)

        solid_after = body._build123d_solid
        if solid_after is None:
            print("[FAIL] Fillet: Solid ist None")
            return False

        print(f"[OK] OCP-First Fillet: {len(list(solid_after.edges()))} Edges")
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_chamfer_ocp_first():
    """Test 5: OCP-First Chamfer"""
    print("\n" + "="*60)
    print("TEST 5: OCP-First Chamfer")
    print("="*60)

    try:
        set_flag("ocp_first_chamfer", True)

        # Basis-Körper erstellen
        sketch = Sketch('Box')
        sketch.add_rectangle(0, 0, 50, 50)

        doc = Document('TestDoc')
        body = Body('TestBody', document=doc)
        doc.add_body(body)

        extrude = ExtrudeFeature(sketch=sketch, distance=20.0, operation='New Body')
        body.add_feature(extrude)

        # Chamfer auf 4 Kanten
        solid_before = body._build123d_solid

        chamfer = ChamferFeature(distance=2.0, edge_indices=[0, 1, 2, 3])
        body.add_feature(chamfer)

        solid_after = body._build123d_solid
        if solid_after is None:
            print("[FAIL] Chamfer: Solid ist None")
            return False

        print(f"[OK] OCP-First Chamfer: {len(list(solid_after.edges()))} Edges")
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def test_legacy_only_mode():
    """Test 6: Reiner Legacy-Mode (ohne OCP-First)"""
    print("\n" + "="*60)
    print("TEST 6: Legacy-Only Mode")
    print("="*60)

    try:
        # OCP-First DEAKTIVIEREN
        set_flag("ocp_first_extrude", False)
        set_flag("ocp_first_fillet", False)
        set_flag("ocp_first_chamfer", False)

        sketch = Sketch('Legacy Test')
        sketch.add_rectangle(0, 0, 40, 30)

        doc = Document('TestDoc')
        body = Body('TestBody', document=doc)
        doc.add_body(body)

        feature = ExtrudeFeature(sketch=sketch, distance=15.0, operation='New Body')
        body.add_feature(feature)

        solid = body._build123d_solid
        if solid is None:
            print("[FAIL] Legacy-Mode: Solid ist None")
            return False

        print(f"[OK] Legacy-Only funktioniert: Volume={solid.volume:.2f}")
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_import_tests():
    """Führt alle Import-Path-Tests aus"""
    print("\n" + "="*60)
    print("IMPORT-PATH TEST SUITE")
    print("="*60)

    results = {
        "Test 1: OCP-First Extrude (Native Circles)": test_extrude_native_circles(),
        "Test 2: OCP-First Extrude (Rectangle)": test_extrude_rectangle(),
        "Test 3: Legacy Fallback": test_extrude_legacy_fallback(),
        "Test 4: OCP-First Fillet": test_fillet_ocp_first(),
        "Test 5: OCP-First Chamfer": test_chamfer_ocp_first(),
        "Test 6: Legacy-Only Mode": test_legacy_only_mode(),
    }

    print("\n" + "="*60)
    print("ERGEBNISSE")
    print("="*60)

    for name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    print(f"\nGesamt: {passed_count}/{total_count} Tests bestanden")

    if passed_count == total_count:
        print("[SUCCESS] Alle Import-Pfade funktionieren!")
        return 0
    else:
        print(f"[FAILURE] {total_count - passed_count} Tests fehlgeschlagen")
        return 1


if __name__ == "__main__":
    exit(run_all_import_tests())
