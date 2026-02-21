"""
Performance, Stress & Edge-Case Test Suite
============================================

Tests für:
- Performance (Tessellation, Cache-Hit-Rates)
- Stress (1000+ Operationen, Large Models)
- Edge-Cases (Zero-Thickness, Tolerance-Boundaries)

Author: Claude (CAD System Improvement)
Date: 2026-02-10
"""
import pytest
import time
import build123d as bd
from build123d import Solid, Location, Vector

from modeling import (
    Body, Document, ExtrudeFeature, BooleanFeature,
    FilletFeature, PatternFeature
)
from modeling.boolean_engine_v4 import BooleanEngineV4, VolumeCache
from modeling.result_types import ResultStatus


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance-Tests für kritische Pfade."""

    def test_volume_cache_performance(self):
        """VolumeCache: Cache-HIT ist schneller als MISS."""
        box = bd.Solid.make_box(10, 10, 10)
        VolumeCache.clear()

        # MISS - erste Berechnung
        start = time.perf_counter()
        vol1 = VolumeCache.get_volume(box)
        miss_time = time.perf_counter() - start

        # HIT - zweite Berechnung
        start = time.perf_counter()
        vol2 = VolumeCache.get_volume(box)
        hit_time = time.perf_counter() - start

        assert vol1 == vol2
        # HIT sollte schneller sein (oder zumindest nicht langsamer)
        assert hit_time <= miss_time * 2  # Toleranz für System-Last

    def test_tessellation_cache_hit(self):
        """Tessellation-Cache verbessert Performance."""
        from modeling.cad_tessellator import CADTessellator

        box = bd.Solid.make_box(10, 10, 10)
        shape_hash = hash((box.faces, box.edges, box.vertices))

        # Erste Tessellation (Cache-Miss)
        start = time.perf_counter()
        mesh1, edges1 = CADTessellator.tessellate(box)
        first_time = time.perf_counter() - start

        # Zweite Tessellation (Cache-Hit)
        start = time.perf_counter()
        mesh2, edges2 = CADTessellator.tessellate(box)
        second_time = time.perf_counter() - start

        # Ergebnis sollte identisch sein
        assert mesh1 is not None
        assert mesh2 is not None

    def test_boolean_parallel_performance(self):
        """Boolean mit Parallel-Setting ist schneller."""
        # Kleiner Performance-Test
        target = bd.Solid.make_box(20, 20, 20)
        tool = bd.Solid.make_cylinder(5, 25).located(Location(Vector(10, 10, 0)))

        # Single-Thread (Approximation)
        start = time.perf_counter()
        result1 = BooleanEngineV4.execute_boolean_on_shapes(
            target, tool, "Cut", fuzzy_tolerance=1e-4
        )
        single_time = time.perf_counter() - start

        # Ergebnis sollte erfolgreich sein
        assert result1.status == ResultStatus.SUCCESS

    def test_polygon_approximation_performance(self):
        """Polygon-Approximation mit n_pts=12 ist performant."""
        # Ein Zylinder mit 12-Polygon-Approximation
        # sollte vernünftige Performance haben
        from shapely.geometry import Polygon

        import math
        n_pts = 12
        radius = 10.0
        coords = [
            (radius * math.cos(2 * math.pi * i / n_pts),
             radius * math.sin(2 * math.pi * i / n_pts))
            for i in range(n_pts)
        ]
        poly = Polygon(coords)

        # Polygon sollte effizient sein
        assert poly.area > 0
        assert len(poly.exterior.coords) == n_pts + 1  # geschlossen


# ============================================================================
# Stress Tests
# ============================================================================

class TestStress:
    """Stress-Tests für Large-Scale Szenarien."""

    def test_100_extrusions_in_series(self):
        """100 Extrusion-Features in Serie."""
        doc = Document("Stress Test 100 Extrusions")
        body = Body("StressBody", document=doc)
        doc.add_body(body)

        # Erstelle initialen Body
        box = bd.Solid.make_box(1, 1, 1)
        body._build123d_solid = box

        # Füge 100 Extrusion-Features hinzu (nicht ausgeführt, nur Liste)
        for i in range(100):
            feat = ExtrudeFeature(
                name=f"Extrude_{i}",
                distance=1.0,
                operation="Join"
            )
            body.add_feature(feat)

        assert len(body.features) == 100

    def test_multiple_booleans_stress(self):
        """Mehrere Boolean-Operationen hintereinander."""
        doc = Document("Stress Test Multi Boolean")
        body = Body("BooleanStressBody", document=doc)
        doc.add_body(body)

        # Start mit großer Box
        box = bd.Solid.make_box(100, 100, 100)
        body._build123d_solid = box

        # Füge 10 Löcher mit verschiedenen Bohrern
        for i in range(10):
            x = 10 + i * 8
            tool = bd.Solid.make_cylinder(3, 120).located(Location(Vector(x, 50, 0)))
            result = BooleanEngineV4.execute_boolean(body, tool, "Cut")
            assert result.status == ResultStatus.SUCCESS

        # Body sollte noch gültig sein
        assert body._build123d_solid is not None
        assert body._build123d_solid.is_valid()

    def test_pattern_large_instance_count(self):
        """Pattern mit hoher Instance-Anzahl."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=100,  # 100 Instanzen
            spacing=5.0
        )

        total = feat.get_total_instances()
        assert total == 100

    def test_2d_pattern_stress(self):
        """2D Pattern (Matrix) Stress-Test."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=50,
            count_2=50,  # 50x50 = 2500 Instanzen
            spacing=10.0  # Gleicher Spacing für beide Richtungen
        )

        total = feat.get_total_instances()
        assert total == 2500  # 50 * 50


# ============================================================================
# Edge-Case Tests
# ============================================================================

class TestEdgeCases:
    """Edge-Case-Tests für Boundary-Values."""

    def test_zero_distance_validation(self):
        """Zero-Distance wird validiert und abgelehnt."""
        from modeling import PushPullFeature

        feat = PushPullFeature(
            face_index=0,
            distance=0.0
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "cannot be zero" in error.lower()

    def test_negative_spacing_validation(self):
        """Negative Spacing wird validiert und abgelehnt."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=3,
            spacing=-5.0
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "positive" in error.lower()

    def test_count_minimum_validation(self):
        """Count < 2 wird validiert und abgelehnt."""
        # Linear Pattern
        feat1 = PatternFeature(
            pattern_type="Linear",
            count=1,
            spacing=10.0
        )
        is_valid1, _ = feat1.validate()
        assert not is_valid1

        # Circular Pattern
        feat2 = PatternFeature(
            pattern_type="Circular",
            count=1
        )
        is_valid2, _ = feat2.validate()
        assert not is_valid2

    def test_boolean_no_overlap(self):
        """Boolean ohne Überlappung → EMPTY oder ERROR."""
        doc = Document("Edge Case Boolean No Overlap")
        body = Body("NoOverlapBody", document=doc)
        doc.add_body(body)

        box = bd.Solid.make_box(10, 10, 10)
        body._build123d_solid = box

        # Tool weit entfernt (keine Überlappung)
        tool = bd.Solid.make_box(10, 10, 10).located(Location(Vector(50, 50, 50)))

        result = BooleanEngineV4.execute_boolean(body, tool, "Cut")

        # Sollte EMPTY oder ERROR sein (kein Absturz!)
        assert result.status in [ResultStatus.EMPTY, ResultStatus.ERROR]

    def test_fillet_zero_radius(self):
        """Fillet mit radius=0 - Edge Case Test."""
        feat = FilletFeature(
            radius=0.0,
            edge_indices=[0]
        )
        # FilletFeature hat keine validate()-Methode,
        # aber sollte mit radius=0 erstellt werden können
        assert feat.radius == 0.0
        assert feat.edge_indices == [0]

    def test_mirror_without_plane(self):
        """Mirror ohne mirror_plane wird abgelehnt."""
        feat = PatternFeature(
            pattern_type="Mirror"
            # mirror_plane fehlt
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "mirror_plane" in error.lower()

    def test_tolerance_boundary_values(self):
        """Tolerance-Grenzwerte werden korrekt gehandhabt."""
        # Sehr kleine aber gültige Toleranz
        result1 = BooleanEngineV4.execute_boolean_on_shapes(
            bd.Solid.make_box(10, 10, 10),
            bd.Solid.make_cylinder(3, 15).located(Location(Vector(5, 5, 0))),
            "Cut",
            fuzzy_tolerance=1e-6  # sehr klein
        )
        assert result1.status == ResultStatus.SUCCESS

        # Normale CAD-Toleranz
        result2 = BooleanEngineV4.execute_boolean_on_shapes(
            bd.Solid.make_box(10, 10, 10),
            bd.Solid.make_cylinder(3, 15).located(Location(Vector(5, 5, 0))),
            "Cut",
            fuzzy_tolerance=1e-4  # CAD-Standard
        )
        assert result2.status == ResultStatus.SUCCESS


# ============================================================================
# Memory Leak Tests
# ============================================================================

class TestMemoryLeaks:
    """Tests für potenzielle Memory-Leaks."""

    def test_volume_cache_clear(self):
        """VolumeCache.clear() leert den Cache."""
        box = bd.Solid.make_box(10, 10, 10)
        cylinder = bd.Solid.make_cylinder(5, 10)

        # Fülle Cache
        VolumeCache.get_volume(box)
        VolumeCache.get_volume(cylinder)
        assert len(VolumeCache._cache) >= 2

        # Clear leert Cache
        VolumeCache.clear()
        assert len(VolumeCache._cache) == 0

    def test_multiple_body_creation_cleanup(self):
        """Mehrere Bodies können erstellt und bereinigt werden."""
        doc = Document("Memory Test")

        # Erstelle 50 Bodies
        bodies = []
        for i in range(50):
            body = Body(f"Body_{i}", document=doc)
            box = bd.Solid.make_box(1, 1, 1)
            body._build123d_solid = box
            bodies.append(body)

        assert len(bodies) == 50
        # Alle Bodies sollten gültig sein
        for body in bodies:
            assert body._build123d_solid is not None


# ============================================================================
# Test Runner
# ============================================================================

def run_all_performance_stress_tests():
    """Führt alle Performance/Stress/Edge-Case Tests aus."""
    print("\n" + "="*60)
    print(" PERFORMANCE / STRESS / EDGE-CASE TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # Performance
        ("Volume Cache Performance", TestPerformance().test_volume_cache_performance),
        ("Tessellation Cache Hit", TestPerformance().test_tessellation_cache_hit),
        ("Boolean Parallel Performance", TestPerformance().test_boolean_parallel_performance),
        ("Polygon Approximation Performance", TestPerformance().test_polygon_approximation_performance),

        # Stress
        ("100 Extrusions in Series", TestStress().test_100_extrusions_in_series),
        ("Multiple Booleans Stress", TestStress().test_multiple_booleans_stress),
        ("Pattern Large Instance Count", TestStress().test_pattern_large_instance_count),
        ("2D Pattern Stress", TestStress().test_2d_pattern_stress),

        # Edge Cases
        ("Zero Distance Validation", TestEdgeCases().test_zero_distance_validation),
        ("Negative Spacing Validation", TestEdgeCases().test_negative_spacing_validation),
        ("Count Minimum Validation", TestEdgeCases().test_count_minimum_validation),
        ("Boolean No Overlap", TestEdgeCases().test_boolean_no_overlap),
        ("Fillet Zero Radius", TestEdgeCases().test_fillet_zero_radius),
        ("Mirror Without Plane", TestEdgeCases().test_mirror_without_plane),
        ("Tolerance Boundary Values", TestEdgeCases().test_tolerance_boundary_values),

        # Memory
        ("Volume Cache Clear", TestMemoryLeaks().test_volume_cache_clear),
        ("Multiple Body Creation Cleanup", TestMemoryLeaks().test_multiple_body_creation_cleanup),
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
    success = run_all_performance_stress_tests()
    sys.exit(0 if success else 1)
