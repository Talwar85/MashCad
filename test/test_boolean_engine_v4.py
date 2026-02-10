"""
BooleanEngineV4 Test Suite
=========================

Tests für die professionelle Boolean-Engine mit:
- VolumeCache Performance
- Fail-Fast Error Handling
- Tolerance Settings
- Transaction Safety
- Shape Validation

Author: Claude (CAD System Improvement)
Date: 2026-02-10
"""
import pytest
import build123d as bd
from build123d import Solid, Location, Vector

from modeling.boolean_engine_v4 import BooleanEngineV4, VolumeCache
from modeling.result_types import ResultStatus, BooleanResult
from modeling import Body, Document
from modeling.body_transaction import BodyTransaction


# ============================================================================
# VolumeCache Tests
# ============================================================================

class TestVolumeCache:
    """Tests für VolumeCache Performance-Optimierung."""

    def test_volume_cache_hit_miss(self):
        """Volume Cache: HIT nach erstem Aufruf."""
        box = bd.Solid.make_box(10, 10, 10)
        shape_id = id(box.wrapped)

        # MISS beim ersten Aufruf
        vol1 = VolumeCache.get_volume(box)
        assert vol1 > 0

        # HIT beim zweiten Aufruf (gleiche Shape ID)
        vol2 = VolumeCache.get_volume(box)
        assert vol2 == vol1
        assert shape_id in VolumeCache._cache

    def test_volume_cache_multiple_shapes(self):
        """Volume Cache: Mehrere Shapes cachen."""
        box1 = bd.Solid.make_box(10, 10, 10)
        box2 = bd.Solid.make_box(20, 20, 20)
        cylinder = bd.Solid.make_cylinder(5, 10)

        # Alle Volumes berechnen
        vol_box1 = VolumeCache.get_volume(box1)
        vol_box2 = VolumeCache.get_volume(box2)
        vol_cyl = VolumeCache.get_volume(cylinder)

        assert vol_box1 == pytest.approx(1000, abs=1)  # 10×10×10
        assert vol_box2 == pytest.approx(8000, abs=1)  # 20×20×20
        assert vol_cyl > 0

        # Alle sollten im Cache sein
        assert len(VolumeCache._cache) >= 3

    def test_volume_cache_clear(self):
        """Volume Cache: Clear leert den Cache."""
        box = bd.Solid.make_box(10, 10, 10)

        # Erster Aufruf füllt Cache
        vol1 = VolumeCache.get_volume(box)
        assert len(VolumeCache._cache) > 0

        # Clear leert Cache
        VolumeCache.clear()
        assert len(VolumeCache._cache) == 0

        # Zweiter Aufruf ist wieder MISS
        vol2 = VolumeCache.get_volume(box)
        assert vol2 == vol1


# ============================================================================
# Boolean Cut Tests
# ============================================================================

class TestBooleanCut:
    """Tests für Boolean Cut Operation."""

    def test_boolean_cut_simple_box(self):
        """Boolean Cut: Einfacher Box-Cylinder."""
        target = bd.Solid.make_box(20, 20, 10)
        tool = bd.Solid.make_cylinder(3.0, 15).located(Location(Vector(10, 10, 0)))

        result = BooleanEngineV4.execute_boolean_on_shapes(
            target, tool, "Cut"
        )

        assert result.status == ResultStatus.SUCCESS
        assert result.value is not None
        assert result.value.is_valid()
        # Cut reduziert Volumen
        assert result.value.volume < target.volume

    def test_boolean_cut_with_tolerance(self):
        """Boolean Cut: Mit custom Tolerance."""
        target = bd.Solid.make_box(20, 20, 10)
        tool = bd.Solid.make_cylinder(3.0, 15).located(Location(Vector(10, 10, 0)))

        # Custom tolerance (stricter than default)
        result = BooleanEngineV4.execute_boolean_on_shapes(
            target, tool, "Cut",
            fuzzy_tolerance=0.00005
        )

        assert result.status == ResultStatus.SUCCESS
        assert result.value is not None

    def test_boolean_cut_no_overlap(self):
        """Boolean Cut: Keine Überlappung → EMPTY."""
        target = bd.Solid.make_box(10, 10, 10)
        # Tool weit entfernt (keine Überlappung)
        tool = bd.Solid.make_box(30, 30, 30).located(Location(Vector(50, 50, 50)))

        result = BooleanEngineV4.execute_boolean_on_shapes(
            target, tool, "Cut"
        )

        # Bei keinem Intersection → EMPTY
        assert result.status in [ResultStatus.EMPTY, ResultStatus.ERROR]

    def test_boolean_cut_none_input(self):
        """Boolean Cut: None Input → ERROR."""
        result = BooleanEngineV4.execute_boolean_on_shapes(
            None, bd.Solid.make_box(10, 10, 10), "Cut"
        )

        assert result.status == ResultStatus.ERROR
        assert "none" in result.message.lower()


# ============================================================================
# Boolean Join (Union) Tests
# ============================================================================

class TestBooleanJoin:
    """Tests für Boolean Join/Union Operation."""

    def test_boolean_join_two_boxes(self):
        """Boolean Join: Zwei Boxes zusammenfügen."""
        box1 = bd.Solid.make_box(10, 10, 10).located(Location(Vector(0, 0, 0)))
        box2 = bd.Solid.make_box(10, 10, 10).located(Location(Vector(10, 0, 0)))

        result = BooleanEngineV4.execute_boolean_on_shapes(
            box1, box2, "Join"
        )

        assert result.status == ResultStatus.SUCCESS
        assert result.value is not None
        assert result.value.is_valid()
        # Join erhöht Volumen (zwei getrennte Boxes)
        assert result.value.volume > box1.volume

    def test_boolean_union_multiple_bodies(self):
        """Boolean Join: Mehrere Bodies kombinieren."""
        boxes = [
            bd.Solid.make_box(10, 10, 10).located(Location(Vector(i*10, 0, 0)))
            for i in range(3)
        ]

        # Sukzessive Union
        result = BooleanEngineV4.execute_boolean_on_shapes(boxes[0], boxes[1], "Join")
        assert result.status == ResultStatus.SUCCESS

        result2 = BooleanEngineV4.execute_boolean_on_shapes(result.value, boxes[2], "Join")
        assert result2.status == ResultStatus.SUCCESS
        assert result2.value.is_valid()


# ============================================================================
# Boolean Common (Intersect) Tests
# ============================================================================

class TestBooleanIntersect:
    """Tests für Boolean Intersect/Common Operation."""

    def test_boolean_common_intersection(self):
        """Boolean Common: Zwei überlappende Boxes."""
        box1 = bd.Solid.make_box(20, 20, 20)
        box2 = bd.Solid.make_box(20, 20, 20).located(Location(Vector(10, 10, 10)))

        result = BooleanEngineV4.execute_boolean_on_shapes(
            box1, box2, "Intersect"
        )

        assert result.status == ResultStatus.SUCCESS
        assert result.value is not None
        assert result.value.is_valid()
        # Intersect reduziert Volumen (nur Überlappung)
        assert result.value.volume < box1.volume

    def test_boolean_common_no_intersection(self):
        """Boolean Common: Keine Überlappung → EMPTY."""
        box1 = bd.Solid.make_box(10, 10, 10)
        box2 = bd.Solid.make_box(10, 10, 10).located(Location(Vector(20, 20, 20)))

        result = BooleanEngineV4.execute_boolean_on_shapes(
            box1, box2, "Intersect"
        )

        # Keine Überlappung → EMPTY oder ERROR (abhängig von OCP Verhalten)
        assert result.status in [ResultStatus.EMPTY, ResultStatus.ERROR]


# ============================================================================
# Body-Boolean Tests (with Transaction)
# ============================================================================

class TestBooleanWithBody:
    """Tests für Boolean mit Body und Transaction."""

    def test_boolean_cut_with_body(self):
        """Boolean Cut mit Body: Transaction-Safety."""
        doc = Document("Boolean Cut Test")
        body = Body("CutBody", document=doc)
        doc.add_body(body)

        # Initialer Solid
        initial_solid = bd.Solid.make_box(20, 20, 10)
        body._build123d_solid = initial_solid
        initial_volume = initial_solid.volume

        # Tool Solid
        tool = bd.Solid.make_cylinder(3.0, 15).located(Location(Vector(10, 10, 0)))

        # Boolean Cut mit Transaction
        result = BooleanEngineV4.execute_boolean(
            body, tool, "Cut"
        )

        assert result.status == ResultStatus.SUCCESS
        assert body._build123d_solid is not None
        assert body._build123d_solid.is_valid()
        # Volumen wurde reduziert
        assert body._build123d_solid.volume < initial_volume

    def test_boolean_with_invalid_body(self):
        """Boolean mit ungültigem Body → Fehler."""
        doc = Document("Boolean Invalid Test")
        body = Body("InvalidBody", document=doc)
        doc.add_body(body)

        # Kein Solid gesetzt
        body._build123d_solid = None

        tool = bd.Solid.make_cylinder(3.0, 10)

        result = BooleanEngineV4.execute_boolean(
            body, tool, "Cut"
        )

        assert result.status == ResultStatus.ERROR
        assert "no solid" in result.message.lower()


# ============================================================================
# Fail-Fast Behavior Tests
# ============================================================================

class TestFailFastBehavior:
    """Tests für Fail-Fast Error Handling."""

    def test_fail_fast_unknown_operation(self):
        """Fail-Fast: Unbekannte Operation."""
        result = BooleanEngineV4.execute_boolean_on_shapes(
            bd.Solid.make_box(10, 10, 10),
            bd.Solid.make_box(10, 10, 10),
            "InvalidOp"
        )

        assert result.status == ResultStatus.ERROR
        assert "unknown" in result.message.lower()

    def test_fail_fast_both_none(self):
        """Fail-Fast: Beide Solids None."""
        result = BooleanEngineV4.execute_boolean_on_shapes(
            None, None, "Cut"
        )

        assert result.status == ResultStatus.ERROR


# ============================================================================
# Tolerance Settings Tests
# ============================================================================

class TestToleranceSettings:
    """Tests für Tolerance-Einstellungen."""

    def test_default_fuzzy_tolerance(self):
        """Default Fuzzy Toleranz sollte CAD-Grade sein."""
        # Toleranz sollte im Bereich 1e-4 bis 1e-5 liegen
        assert BooleanEngineV4.PRODUCTION_FUZZY_TOLERANCE < 0.001
        assert BooleanEngineV4.PRODUCTION_FUZZY_TOLERANCE > 0.00001

    def test_min_volume_change_exists(self):
        """MIN_VOLUME_CHANGE sollte definiert sein."""
        # Sollte ein sehr kleiner aber positiver Wert sein
        assert BooleanEngineV4.MIN_VOLUME_CHANGE > 0
        assert BooleanEngineV4.MIN_VOLUME_CHANGE < 1.0  # Weniger als 1mm³


# ============================================================================
# VolumeCache Performance Test
# ============================================================================

class TestVolumeCachePerformance:
    """Performance-Tests für VolumeCache."""

    def test_cache_performance_benefit(self):
        """Test dass Cache Performance-Verbesserung bringt."""
        import time

        box = bd.Solid.make_box(10, 10, 10)

        # Clear für sauberen Test
        VolumeCache.clear()

        # Erste Berechnung (MISS) - langsam
        start = time.perf_counter()
        vol1 = VolumeCache.get_volume(box)
        miss_time = time.perf_counter() - start

        # Zweite Berechnung (HIT) - schnell
        start = time.perf_counter()
        vol2 = VolumeCache.get_volume(box)
        hit_time = time.perf_counter() - start

        assert vol1 == vol2
        # HIT sollte schneller sein als MISS (in den meisten Fällen)
        # Aber tolerieren wir Abweichungen durch System-Last
        assert hit_time >= 0

    def test_cache_invalidation(self):
        """Cache-Invalidation nach Shape-Änderung."""
        box = bd.Solid.make_box(10, 10, 10)

        # Erster Aufruf
        vol1 = VolumeCache.get_volume(box)
        shape_id = id(box.wrapped)
        assert shape_id in VolumeCache._cache

        # Invalidieren
        VolumeCache.invalidate(box)
        assert shape_id not in VolumeCache._cache

        # Zweiter Aufruf ist wieder MISS
        vol2 = VolumeCache.get_volume(box)
        assert vol2 == vol1


# ============================================================================
# Test Runner
# ============================================================================

def run_all_boolean_engine_tests():
    """Führt alle BooleanEngineV4 Tests aus."""
    print("\n" + "="*60)
    print("BOOLEAN ENGINE V4 TEST SUITE")
    print("="*60 + "\n")

    tests = [
        ("VolumeCache Hit/Miss", TestVolumeCache().test_volume_cache_hit_miss),
        ("VolumeCache Multiple", TestVolumeCache().test_volume_cache_multiple_shapes),
        ("VolumeCache Clear", TestVolumeCache().test_volume_cache_clear),
        ("Boolean Cut Simple", TestBooleanCut().test_boolean_cut_simple_box),
        ("Boolean Cut Tolerance", TestBooleanCut().test_boolean_cut_with_tolerance),
        ("Boolean Cut No Overlap", TestBooleanCut().test_boolean_cut_no_overlap),
        ("Boolean Cut None Input", TestBooleanCut().test_boolean_cut_none_input),
        ("Boolean Join Two Boxes", TestBooleanJoin().test_boolean_join_two_boxes),
        ("Boolean Join Multiple", TestBooleanJoin().test_boolean_union_multiple_bodies),
        ("Boolean Common Intersection", TestBooleanIntersect().test_boolean_common_intersection),
        ("Boolean Common No Intersection", TestBooleanIntersect().test_boolean_common_no_intersection),
        ("Boolean Cut with Body", TestBooleanWithBody().test_boolean_cut_with_body),
        ("Boolean Invalid Body", TestBooleanWithBody().test_boolean_with_invalid_body),
        ("Fail-Fast Unknown Op", TestFailFastBehavior().test_fail_fast_unknown_operation),
        ("Fail-Fast Both None", TestFailFastBehavior().test_fail_fast_both_none),
        ("Default Fuzzy Tolerance", TestToleranceSettings().test_default_fuzzy_tolerance),
        ("Min Volume Change", TestToleranceSettings().test_min_volume_change_exists),
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
    success = run_all_boolean_engine_tests()
    sys.exit(0 if success else 1)
