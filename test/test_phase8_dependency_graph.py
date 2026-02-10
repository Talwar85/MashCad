"""
Phase 8: Dependency Graph Integration Tests

Tests für Feature Dependency Graph mit topological sort und incremental rebuild.

Author: Claude (OCP-First Migration Phase 8)
Date: 2026-02-10
"""

import pytest
from modeling.feature_dependency import (
    FeatureDependencyGraph,
    DependencyType,
    get_dependency_graph,
    clear_global_dependency_graph
)


# ============================================================================
# BASIC GRAPH OPERATIONS TESTS
# ============================================================================

class TestDependencyGraphBasic:
    """Tests für grundlegende Graph Operationen."""

    def test_empty_graph(self):
        """Test leerer Graph."""
        graph = FeatureDependencyGraph()

        assert graph.get_statistics()['total_features'] == 0
        assert graph.get_build_order() == []

    def test_add_single_feature(self):
        """Test einzelnes Feature hinzufügen."""
        graph = FeatureDependencyGraph()

        graph.add_feature("feature1", index=0)

        stats = graph.get_statistics()
        assert stats['total_features'] == 1
        assert "feature1" in graph._feature_index

    def test_add_multiple_features(self):
        """Test mehrere Features hinzufügen."""
        graph = FeatureDependencyGraph()

        graph.add_feature("feature1", index=0)
        graph.add_feature("feature2", index=1)
        graph.add_feature("feature3", index=2)

        stats = graph.get_statistics()
        assert stats['total_features'] == 3

    def test_remove_feature(self):
        """Test Feature entfernen."""
        graph = FeatureDependencyGraph()

        graph.add_feature("feature1", index=0)
        graph.add_feature("feature2", index=1)

        stats = graph.get_statistics()
        assert stats['total_features'] == 2

        graph.remove_feature("feature1")

        stats = graph.get_statistics()
        assert stats['total_features'] == 1
        assert "feature1" not in graph._feature_index

    def test_remove_nonexistent_feature(self):
        """Test entfernen nicht existierendes Feature (no error)."""
        graph = FeatureDependencyGraph()

        # Sollte keinen Fehler werfen
        graph.remove_feature("nonexistent")

        assert graph.get_statistics()['total_features'] == 0


# ============================================================================
# TOPOLOGICAL SORT TESTS
# ============================================================================

class TestTopologicalSort:
    """Tests für topologische Sortierung (Kahn's Algorithm)."""

    def test_build_order_linear_chain(self):
        """Test Build Order für lineare Kette."""
        graph = FeatureDependencyGraph()

        # sketch -> extrude -> fillet
        graph.add_feature("sketch1", index=0)
        graph.add_feature("extrude1", index=1)
        graph.add_feature("fillet1", index=2)

        build_order = graph.get_build_order()

        # Lineare Kette sollte in Index-Reihenfolge sein
        assert build_order == ["sketch1", "extrude1", "fillet1"]

    def test_build_order_with_dependencies(self):
        """Test Build Order mit expliziten Abhängigkeiten."""
        graph = FeatureDependencyGraph()

        # sketch1 wird von extrude1 benötigt
        graph.add_feature("sketch1", index=0)
        graph.add_feature("extrude1", index=1, dependencies=[("sketch1", DependencyType.SKETCH_REFERENCE)])
        graph.add_feature("fillet1", index=2, dependencies=[("extrude1", DependencyType.EDGE_REFERENCE)])

        build_order = graph.get_build_order()

        # sketch1 muss vor extrude1, fillet1 nach extrude1
        sketch_idx = build_order.index("sketch1")
        extrude_idx = build_order.index("extrude1")
        fillet_idx = build_order.index("fillet1")

        assert sketch_idx < extrude_idx < fillet_idx

    def test_build_order_subset(self):
        """Test Build Order für subset von Features."""
        graph = FeatureDependencyGraph()

        graph.add_feature("feature1", index=0)
        graph.add_feature("feature2", index=1)
        graph.add_feature("feature3", index=2)

        # Nur subset
        build_order = graph.get_build_order({"feature1", "feature3"})

        assert "feature1" in build_order
        assert "feature3" in build_order
        assert "feature2" not in build_order

    def test_build_order_empty_subset(self):
        """Test Build Order für leeren subset."""
        graph = FeatureDependencyGraph()

        graph.add_feature("feature1", index=0)

        build_order = graph.get_build_order(set())

        assert build_order == []

    def test_build_order_all_features(self):
        """Test Build Order ohne Parameter (alle Features)."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        graph.add_feature("f3", index=2)

        build_order = graph.get_build_order()

        assert len(build_order) == 3
        assert build_order == ["f1", "f2", "f3"]

    def test_build_order_deterministic(self):
        """Test dass Build Order deterministisch ist."""
        graph = FeatureDependencyGraph()

        graph.add_feature("alpha", index=0)
        graph.add_feature("beta", index=1)
        graph.add_feature("gamma", index=2)

        # Mehrfach aufrufen sollte gleiches Ergebnis liefern
        order1 = graph.get_build_order()
        order2 = graph.get_build_order()

        assert order1 == order2


# ============================================================================
# CYCLE DETECTION TESTS
# ============================================================================

class TestCycleDetection:
    """Tests für Zyklus-Detection."""

    def test_no_cycle_in_linear_chain(self):
        """Test keine Zyklen in linearer Kette."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        graph.add_feature("f3", index=2)

        cycles = graph.detect_cycles()

        assert cycles == []

    def test_cycle_detection_with_self_loop(self):
        """Test Zyklus-Detection mit self-loop."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        # Manuelles hinzufügen einer zyklischen Abhängigkeit
        graph._add_dependency("f1", "f1", DependencyType.SEQUENTIAL)

        cycles = graph.detect_cycles()

        # Zyklus sollte erkannt werden
        assert len(cycles) > 0
        assert any("f1" in cycle for cycle in cycles)

    def test_validate_with_cycle(self):
        """Test validate() mit Zyklus."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph._add_dependency("f1", "f1", DependencyType.SEQUENTIAL)

        is_valid, errors = graph.validate()

        assert not is_valid
        assert len(errors) > 0
        assert "Zykl" in errors[0]  # "Zyklische" in German

    def test_validate_without_cycle(self):
        """Test validate() ohne Zyklus."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)

        is_valid, errors = graph.validate()

        assert is_valid
        assert len(errors) == 0


# ============================================================================
# DIRTY TRACKING TESTS
# ============================================================================

class TestDirtyTracking:
    """Tests für Dirty-Tracking."""

    def test_mark_dirty_single_feature(self):
        """Test einzelnes Feature als dirty markieren."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)

        graph.mark_dirty("f1")

        assert "f1" in graph._dirty_features
        # f2 ist auch dirty wegen sequentieller Abhängigkeit (Propagation)
        assert "f2" in graph._dirty_features

    def test_mark_dirty_propagates_to_dependents(self):
        """Test dass dirty-Status zu abhängigen Features propagiert."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        graph.add_feature("f3", index=2)

        # f2 hängt von f1 ab (sequentiell)
        # f3 hängt von f2 ab (sequentiell)

        graph.mark_dirty("f1")

        # Alle sollten dirty sein (Propagation)
        assert "f1" in graph._dirty_features
        assert "f2" in graph._dirty_features
        assert "f3" in graph._dirty_features

    def test_clear_dirty(self):
        """Test clear_dirty()."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)

        graph.mark_dirty("f1")
        assert "f1" in graph._dirty_features

        graph.clear_dirty()
        assert len(graph._dirty_features) == 0

    def test_get_dirty_features(self):
        """Test get_dirty_features()."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)

        graph.mark_dirty("f1")

        dirty = graph.get_dirty_features()
        assert "f1" in dirty
        # f2 ist auch dirty wegen sequentieller Abhängigkeit (Propagation)
        assert "f2" in dirty


# ============================================================================
# INCREMENTAL REBUILD TESTS
# ============================================================================

class TestIncrementalRebuild:
    """Tests für inkrementelles Rebuild."""

    def test_incremental_rebuild_single_changed(self):
        """Test inkrementelles Rebuild mit einem geänderten Feature."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        graph.add_feature("f3", index=2)

        # f2 geändert
        rebuild_order = graph.get_incremental_rebuild_order({"f2"})

        # f2 und f3 sollten rebuilded werden (f3 hängt von f2 ab)
        assert "f2" in rebuild_order
        assert "f3" in rebuild_order

    def test_incremental_rebuild_multiple_changed(self):
        """Test inkrementelles Rebuild mit mehreren geänderten Features."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        graph.add_feature("f3", index=2)

        # f1 und f3 geändert
        rebuild_order = graph.get_incremental_rebuild_order({"f1", "f3"})

        # Alle sollten rebuilded werden (f1 -> f2 -> f3)
        assert len(rebuild_order) == 3

    def test_incremental_rebuild_clears_dirty_after(self):
        """Test dass dirty-Status nach Rebuild zurückgesetzt wird."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)

        graph.mark_dirty("f1")
        assert len(graph._dirty_features) > 0

        # Rebuild
        rebuild_order = graph.get_incremental_rebuild_order({"f1"})

        # Dirty sollte geleert sein
        assert len(graph._dirty_features) == 0

    def test_incremental_rebuild_order_sorted(self):
        """Test dass Rebuild-Order korrekt sortiert ist."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        graph.add_feature("f3", index=2)

        rebuild_order = graph.get_incremental_rebuild_order({"f2"})

        # Reihenfolge sollte nach Index sortiert sein
        indices = [graph._feature_index[fid] for fid in rebuild_order]
        assert indices == sorted(indices)


# ============================================================================
# DEPENDENCY QUERIES TESTS
# ============================================================================

class TestDependencyQueries:
    """Tests für Abhängigkeits-Abfragen."""

    def test_get_dependencies(self):
        """Test get_dependencies()."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1, dependencies=[("f1", DependencyType.SEQUENTIAL)])

        deps = graph.get_dependencies("f2")

        assert "f1" in deps

    def test_get_dependencies_empty(self):
        """Test get_dependencies() für Feature ohne Abhängigkeiten."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)

        deps = graph.get_dependencies("f1")

        assert deps == set()

    def test_get_dependents(self):
        """Test get_dependents()."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1, dependencies=[("f1", DependencyType.SEQUENTIAL)])

        dependents = graph.get_dependents("f1")

        assert "f2" in dependents

    def test_get_all_transitive_dependencies(self):
        """Test get_all_transitive_dependencies()."""
        graph = FeatureDependencyGraph()

        # f1 <- f2 <- f3
        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1, dependencies=[("f1", DependencyType.SEQUENTIAL)])
        graph.add_feature("f3", index=2, dependencies=[("f2", DependencyType.SEQUENTIAL)])

        # f3 hängt transitiv von f1 und f2 ab
        transitive = graph.get_all_transitive_dependencies("f3")

        assert "f1" in transitive
        assert "f2" in transitive

    def test_get_all_transitive_dependents(self):
        """Test get_all_transitive_dependents()."""
        graph = FeatureDependencyGraph()

        # f1 <- f2 <- f3
        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1, dependencies=[("f1", DependencyType.SEQUENTIAL)])
        graph.add_feature("f3", index=2, dependencies=[("f2", DependencyType.SEQUENTIAL)])

        # f1 hat transitiv f2 und f3 als dependents
        transitive = graph.get_all_transitive_dependents("f1")

        assert "f2" in transitive
        assert "f3" in transitive


# ============================================================================
# VISUALIZE TESTS
# ============================================================================

class TestVisualize:
    """Tests für visualize()."""

    def test_visualize_empty_graph(self):
        """Test visualize() für leeren Graph."""
        graph = FeatureDependencyGraph()

        viz = graph.visualize()

        assert "(empty)" in viz

    def test_visualize_with_features(self):
        """Test visualize() mit Features."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)

        viz = graph.visualize()

        assert "f1" in viz
        assert "f2" in viz
        assert "Build Order" in viz

    def test_visualize_with_dirty(self):
        """Test visualize() zeigt dirty-Status."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.mark_dirty("f1")

        viz = graph.visualize()

        assert "[DIRTY]" in viz


# ============================================================================
# GLOBAL GRAPH TESTS
# ============================================================================

class TestGlobalGraph:
    """Tests für globale Dependency Graph Instance."""

    def test_get_global_graph_singleton(self):
        """Test dass get_dependency_graph() Singleton zurückgibt."""
        clear_global_dependency_graph()

        g1 = get_dependency_graph()
        g2 = get_dependency_graph()

        assert g1 is g2

    def test_clear_global_graph(self):
        """Test dass clear_global_dependency_graph() funktioniert."""
        g1 = get_dependency_graph()
        g1.add_feature("test", index=0)

        clear_global_dependency_graph()

        g2 = get_dependency_graph()
        assert g2.get_statistics()['total_features'] == 0


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestStatistics:
    """Tests für Statistiken."""

    def test_statistics_empty(self):
        """Test Statistiken für leeren Graph."""
        graph = FeatureDependencyGraph()

        stats = graph.get_statistics()

        assert stats['total_features'] == 0
        assert stats['total_dependencies'] == 0
        assert stats['dirty_features'] == 0

    def test_statistics_with_features(self):
        """Test Statistiken mit Features."""
        graph = FeatureDependencyGraph()

        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)

        stats = graph.get_statistics()

        assert stats['total_features'] == 2
        # f2 hat eine SEQUENTIAL Abhängigkeit zu f1
        assert stats['total_dependencies'] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
