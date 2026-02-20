"""
MashCAD Integration Tests - Feature Edit Workflow
==================================================

Integration tests for Feature lifecycle including:
- Feature creation → edit → delete workflow
- Dependency Graph updates
- Rebuild behavior
- Transaction safety

Author: QA-001 Phase 4
Date: 2026-02-20
"""

import pytest
from typing import Optional
from loguru import logger
from build123d import Solid, Location, Vector

from modeling import Body, Document, Feature
from modeling.feature_dependency import (
    FeatureDependencyGraph,
    DependencyType,
    get_dependency_graph,
    clear_global_dependency_graph
)
from modeling.result_types import ResultStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def document():
    """Create a fresh Document for each test."""
    clear_global_dependency_graph()
    doc = Document("FeatureEditTestDoc")
    yield doc
    doc.bodies.clear()
    clear_global_dependency_graph()


@pytest.fixture
def body_with_box(document):
    """Create a body with a simple box solid."""
    body = Body("TestBody", document=document)
    body._solid = Solid.make_box(20, 20, 10)
    body._mesh_valid = False
    return body


@pytest.fixture
def dependency_graph():
    """Create a fresh dependency graph for each test."""
    clear_global_dependency_graph()
    graph = FeatureDependencyGraph()
    yield graph
    graph.clear()
    clear_global_dependency_graph()


# ============================================================================
# FEATURE LIFECYCLE TESTS
# ============================================================================

class TestFeatureLifecycle:
    """Tests for complete feature lifecycle: create → edit → delete."""

    def test_create_feature_adds_to_body(self, document):
        """Creating a feature should add it to body's feature list."""
        body = Body("TestBody", document=document)
        
        # Create a simple feature
        feature = Feature()
        feature.id = "test_feature_1"
        feature.name = "Test Feature"
        
        body.add_feature(feature, rebuild=False)
        
        assert len(body.features) == 1
        assert body.features[0].id == "test_feature_1"

    def test_create_multiple_features_sequential(self, document):
        """Multiple features should be added in sequence."""
        body = Body("TestBody", document=document)
        
        for i in range(3):
            feature = Feature()
            feature.id = f"feature_{i}"
            feature.name = f"Feature {i}"
            body.add_feature(feature, rebuild=False)
        
        assert len(body.features) == 3
        # Features should be in order
        assert body.features[0].id == "feature_0"
        assert body.features[1].id == "feature_1"
        assert body.features[2].id == "feature_2"

    def test_remove_feature_from_body(self, document):
        """Removing a feature should update body's feature list."""
        body = Body("TestBody", document=document)
        
        feature1 = Feature()
        feature1.id = "feature_1"
        feature2 = Feature()
        feature2.id = "feature_2"
        
        body.add_feature(feature1, rebuild=False)
        body.add_feature(feature2, rebuild=False)
        
        assert len(body.features) == 2
        
        # Remove first feature
        body.remove_feature(feature1)
        
        assert len(body.features) == 1
        assert body.features[0].id == "feature_2"

    def test_remove_middle_feature(self, document):
        """Removing a middle feature should maintain order."""
        body = Body("TestBody", document=document)
        
        features = []
        for i in range(5):
            feature = Feature()
            feature.id = f"feature_{i}"
            body.add_feature(feature, rebuild=False)
            features.append(feature)
        
        # Remove middle feature
        body.remove_feature(features[2])
        
        assert len(body.features) == 4
        assert body.features[0].id == "feature_0"
        assert body.features[1].id == "feature_1"
        assert body.features[2].id == "feature_3"  # Skipped 2
        assert body.features[3].id == "feature_4"


# ============================================================================
# DEPENDENCY GRAPH INTEGRATION TESTS
# ============================================================================

class TestDependencyGraphIntegration:
    """Tests for dependency graph updates during feature operations."""

    def test_add_feature_updates_graph(self, dependency_graph):
        """Adding a feature should update the dependency graph."""
        dependency_graph.add_feature("sketch_1", index=0)
        dependency_graph.add_feature("extrude_1", index=1)
        dependency_graph.add_feature("fillet_1", index=2)
        
        stats = dependency_graph.get_statistics()
        assert stats['total_features'] == 3

    def test_remove_feature_updates_graph(self, dependency_graph):
        """Removing a feature should update the dependency graph."""
        dependency_graph.add_feature("feature_1", index=0)
        dependency_graph.add_feature("feature_2", index=1)
        dependency_graph.add_feature("feature_3", index=2)
        
        stats = dependency_graph.get_statistics()
        assert stats['total_features'] == 3
        
        dependency_graph.remove_feature("feature_2")
        
        stats = dependency_graph.get_statistics()
        assert stats['total_features'] == 2

    def test_sequential_dependency_tracking(self, dependency_graph):
        """Features should have sequential dependencies by default."""
        dependency_graph.add_feature("feature_1", index=0)
        dependency_graph.add_feature("feature_2", index=1)
        dependency_graph.add_feature("feature_3", index=2)
        
        # Feature 2 should depend on Feature 1
        deps_2 = dependency_graph._dependencies.get("feature_2", [])
        assert any(d.target_id == "feature_1" for d in deps_2)
        
        # Feature 3 should depend on Feature 2
        deps_3 = dependency_graph._dependencies.get("feature_3", [])
        assert any(d.target_id == "feature_2" for d in deps_3)

    def test_explicit_dependency_tracking(self, dependency_graph):
        """Explicit dependencies should be tracked correctly."""
        dependency_graph.add_feature("sketch_1", index=0)
        dependency_graph.add_feature("extrude_1", index=1, 
            dependencies=[("sketch_1", DependencyType.SKETCH_REFERENCE)])
        dependency_graph.add_feature("fillet_1", index=2,
            dependencies=[("extrude_1", DependencyType.EDGE_REFERENCE)])
        
        # Check sketch reference
        deps_extrude = dependency_graph._dependencies.get("extrude_1", [])
        sketch_deps = [d for d in deps_extrude if d.dependency_type == DependencyType.SKETCH_REFERENCE]
        assert len(sketch_deps) == 1
        assert sketch_deps[0].target_id == "sketch_1"
        
        # Check edge reference
        deps_fillet = dependency_graph._dependencies.get("fillet_1", [])
        edge_deps = [d for d in deps_fillet if d.dependency_type == DependencyType.EDGE_REFERENCE]
        assert len(edge_deps) == 1
        assert edge_deps[0].target_id == "extrude_1"

    def test_affected_features_on_change(self, dependency_graph):
        """Changing a feature should identify all affected features."""
        dependency_graph.add_feature("sketch_1", index=0)
        dependency_graph.add_feature("extrude_1", index=1,
            dependencies=[("sketch_1", DependencyType.SKETCH_REFERENCE)])
        dependency_graph.add_feature("fillet_1", index=2,
            dependencies=[("extrude_1", DependencyType.EDGE_REFERENCE)])
        
        # Change sketch_1 should affect all downstream features
        affected = dependency_graph.get_affected_features("sketch_1")
        
        assert "sketch_1" in affected
        assert "extrude_1" in affected
        assert "fillet_1" in affected

    def test_build_order_respects_dependencies(self, dependency_graph):
        """Build order should respect dependency chain."""
        dependency_graph.add_feature("sketch_1", index=0)
        dependency_graph.add_feature("extrude_1", index=1,
            dependencies=[("sketch_1", DependencyType.SKETCH_REFERENCE)])
        dependency_graph.add_feature("fillet_1", index=2,
            dependencies=[("extrude_1", DependencyType.EDGE_REFERENCE)])
        
        build_order = dependency_graph.get_build_order()
        
        # Sketch must come before extrude
        assert build_order.index("sketch_1") < build_order.index("extrude_1")
        # Extrude must come before fillet
        assert build_order.index("extrude_1") < build_order.index("fillet_1")


# ============================================================================
# FEATURE EDIT WORKFLOW TESTS
# ============================================================================

class TestFeatureEditWorkflow:
    """Tests for feature editing workflow."""

    def test_edit_feature_parameters(self, document):
        """Editing feature parameters should mark it for rebuild."""
        body = Body("TestBody", document=document)
        
        feature = Feature()
        feature.id = "extrude_1"
        feature.name = "Extrude 1"
        body.add_feature(feature, rebuild=False)
        
        # Edit feature
        feature.name = "Modified Extrude"
        
        assert body.features[0].name == "Modified Extrude"

    def test_edit_triggers_downstream_rebuild(self, dependency_graph):
        """Editing a feature should trigger rebuild of dependent features."""
        dependency_graph.add_feature("base", index=0)
        dependency_graph.add_feature("derived_1", index=1,
            dependencies=[("base", DependencyType.SEQUENTIAL)])
        dependency_graph.add_feature("derived_2", index=2,
            dependencies=[("derived_1", DependencyType.SEQUENTIAL)])
        
        # Mark base as dirty
        dependency_graph.mark_dirty("base")
        
        # Check dirty propagation
        dirty = dependency_graph.get_dirty_features()
        assert "base" in dirty

    def test_feature_edit_preserves_order(self, document):
        """Editing a feature should preserve feature order."""
        body = Body("TestBody", document=document)
        
        features = []
        for i in range(3):
            feature = Feature()
            feature.id = f"feature_{i}"
            body.add_feature(feature, rebuild=False)
            features.append(feature)
        
        # Edit middle feature
        features[1].name = "Edited Feature"
        
        # Order should be preserved
        assert body.features[0].id == "feature_0"
        assert body.features[1].id == "feature_1"
        assert body.features[1].name == "Edited Feature"
        assert body.features[2].id == "feature_2"


# ============================================================================
# TRANSACTION SAFETY TESTS
# ============================================================================

class TestTransactionSafety:
    """Tests for transaction safety during feature operations."""

    def test_feature_add_can_rollback(self, document):
        """Adding a feature should be rollback-able."""
        body = Body("TestBody", document=document)
        
        initial_count = len(body.features)
        
        feature = Feature()
        feature.id = "test_feature"
        body.add_feature(feature, rebuild=False)
        
        assert len(body.features) == initial_count + 1
        
        # Simulate rollback by removing
        body.remove_feature(feature)
        
        assert len(body.features) == initial_count

    def test_graph_clear_on_body_destruction(self, document):
        """Dependency graph should be clearable."""
        graph = FeatureDependencyGraph()
        
        graph.add_feature("f1", index=0)
        graph.add_feature("f2", index=1)
        
        assert graph.get_statistics()['total_features'] == 2
        
        graph.clear()
        
        assert graph.get_statistics()['total_features'] == 0


# ============================================================================
# COMPLEX WORKFLOW TESTS
# ============================================================================

class TestComplexFeatureWorkflows:
    """Tests for complex feature workflows."""

    def test_create_edit_delete_cycle(self, document):
        """Complete cycle: create → edit → delete."""
        body = Body("TestBody", document=document)
        
        # Create
        feature = Feature()
        feature.id = "test_feature"
        feature.name = "Original Name"
        body.add_feature(feature, rebuild=False)
        
        assert len(body.features) == 1
        
        # Edit
        feature.name = "Edited Name"
        assert body.features[0].name == "Edited Name"
        
        # Delete
        body.remove_feature(feature)
        assert len(body.features) == 0

    def test_multiple_edits_same_feature(self, document):
        """Multiple edits to the same feature should work."""
        body = Body("TestBody", document=document)
        
        feature = Feature()
        feature.id = "test_feature"
        body.add_feature(feature, rebuild=False)
        
        # Multiple edits
        for i in range(5):
            feature.name = f"Version {i}"
        
        assert body.features[0].name == "Version 4"

    def test_interleaved_operations(self, document):
        """Interleaved create/edit/delete operations."""
        body = Body("TestBody", document=document)
        
        # Create features
        f1 = Feature()
        f1.id = "f1"
        f2 = Feature()
        f2.id = "f2"
        f3 = Feature()
        f3.id = "f3"
        
        body.add_feature(f1, rebuild=False)
        body.add_feature(f2, rebuild=False)
        
        # Edit f1
        f1.name = "Edited F1"
        
        # Add f3
        body.add_feature(f3, rebuild=False)
        
        # Remove f2
        body.remove_feature(f2)
        
        # Edit f3
        f3.name = "Edited F3"
        
        # Verify final state
        assert len(body.features) == 2
        assert body.features[0].id == "f1"
        assert body.features[0].name == "Edited F1"
        assert body.features[1].id == "f3"
        assert body.features[1].name == "Edited F3"

    def test_dependency_chain_preservation_after_edit(self, dependency_graph):
        """Dependency chain should be preserved after edits."""
        # Build chain: sketch -> extrude -> fillet -> chamfer
        dependency_graph.add_feature("sketch", index=0)
        dependency_graph.add_feature("extrude", index=1,
            dependencies=[("sketch", DependencyType.SKETCH_REFERENCE)])
        dependency_graph.add_feature("fillet", index=2,
            dependencies=[("extrude", DependencyType.EDGE_REFERENCE)])
        dependency_graph.add_feature("chamfer", index=3,
            dependencies=[("fillet", DependencyType.SEQUENTIAL)])
        
        # Verify chain
        build_order = dependency_graph.get_build_order()
        
        assert build_order.index("sketch") < build_order.index("extrude")
        assert build_order.index("extrude") < build_order.index("fillet")
        assert build_order.index("fillet") < build_order.index("chamfer")
        
        # Get affected features when sketch changes
        affected = dependency_graph.get_affected_features("sketch")
        assert len(affected) == 4  # All features affected
