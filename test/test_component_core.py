"""
MashCAD - Component Core Tests
==============================

AS-001: Component-Core Stabilization tests.

Tests for:
 - Component dataclass
 - ComponentManager CRUD operations
 - ComponentTransform operations
 - Serialization/deserialization
"""

import pytest
from dataclasses import dataclass
from typing import Optional

# Test imports
from modeling.component_core import (
    Component,
    ComponentTransform,
    ComponentManager,
    get_default_manager,
    reset_default_manager,
)
from modeling.component_transform import (
    apply_transform,
    reset_transform,
    combine_transforms,
    set_position,
    set_rotation,
    set_scale,
    translate,
    rotate,
    get_world_transform,
    TransformOperations,
)


# =============================================================================
# Mock Body for testing
# =============================================================================

@dataclass
class MockBody:
    """Mock body for testing component references."""
    id: str
    name: str

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())[:8]


# =============================================================================
# ComponentTransform Tests
# =============================================================================

class TestComponentTransform:
    """Tests for ComponentTransform dataclass."""

    def test_default_transform(self):
        """Test default transform is identity."""
        t = ComponentTransform()
        assert t.position == (0.0, 0.0, 0.0)
        assert t.rotation == (0.0, 0.0, 0.0)
        assert t.scale == 1.0

    def test_custom_transform(self):
        """Test custom transform values."""
        t = ComponentTransform(
            position=(10.0, 20.0, 30.0),
            rotation=(45.0, 90.0, 180.0),
            scale=2.0
        )
        assert t.position == (10.0, 20.0, 30.0)
        assert t.rotation == (45.0, 90.0, 180.0)
        assert t.scale == 2.0

    def test_is_identity(self):
        """Test identity check."""
        t1 = ComponentTransform()
        assert t1.is_identity() is True

        t2 = ComponentTransform(position=(1, 0, 0))
        assert t2.is_identity() is False

        t3 = ComponentTransform(rotation=(0, 0, 1))
        assert t3.is_identity() is False

        t4 = ComponentTransform(scale=0.5)
        assert t4.is_identity() is False

    def test_copy(self):
        """Test transform copy."""
        t1 = ComponentTransform(position=(5, 10, 15))
        t2 = t1.copy()
        assert t2.position == t1.position
        assert t2 is not t1

    def test_to_dict(self):
        """Test serialization to dict."""
        t = ComponentTransform(
            position=(1, 2, 3),
            rotation=(10, 20, 30),
            scale=1.5
        )
        d = t.to_dict()
        assert d["position"] == [1, 2, 3]
        assert d["rotation"] == [10, 20, 30]
        assert d["scale"] == 1.5

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "position": [5, 10, 15],
            "rotation": [45, 90, 135],
            "scale": 2.0
        }
        t = ComponentTransform.from_dict(d)
        assert t.position == (5, 10, 15)
        assert t.rotation == (45, 90, 135)
        assert t.scale == 2.0

    def test_from_dict_defaults(self):
        """Test deserialization with missing keys."""
        t = ComponentTransform.from_dict({})
        assert t.position == (0.0, 0.0, 0.0)
        assert t.rotation == (0.0, 0.0, 0.0)
        assert t.scale == 1.0


# =============================================================================
# Component Tests
# =============================================================================

class TestComponent:
    """Tests for Component dataclass."""

    def test_default_component(self):
        """Test default component creation."""
        comp = Component()
        assert comp.component_id != ""
        assert comp.name == "Component"
        assert comp.body_reference is None
        assert comp.transform.is_identity()

    def test_custom_component(self):
        """Test component with custom values."""
        t = ComponentTransform(position=(10, 0, 0))
        comp = Component(
            component_id="test123",
            name="TestComponent",
            body_reference="body_456",
            transform=t,
            metadata={"key": "value"}
        )
        assert comp.component_id == "test123"
        assert comp.name == "TestComponent"
        assert comp.body_reference == "body_456"
        assert comp.transform.position == (10, 0, 0)
        assert comp.metadata["key"] == "value"

    def test_component_hierarchy(self):
        """Test parent-child relationships."""
        parent = Component(name="Parent")
        child1 = Component(name="Child1")
        child2 = Component(name="Child2")

        parent.add_child(child1)
        parent.add_child(child2)

        assert len(parent.children) == 2
        assert child1.parent == parent
        assert child2.parent == parent

    def test_remove_child(self):
        """Test removing a child."""
        parent = Component(name="Parent")
        child = Component(name="Child")
        parent.add_child(child)

        assert parent.remove_child(child) is True
        assert len(parent.children) == 0
        assert child.parent is None

    def test_get_all_descendants(self):
        """Test getting all descendants."""
        root = Component(name="Root")
        c1 = Component(name="C1")
        c2 = Component(name="C2")
        c3 = Component(name="C3")

        root.add_child(c1)
        root.add_child(c2)
        c1.add_child(c3)

        descendants = root.get_all_descendants()
        assert len(descendants) == 3
        assert c1 in descendants
        assert c2 in descendants
        assert c3 in descendants

    def test_find_by_id(self):
        """Test finding component by ID."""
        root = Component(name="Root", component_id="root")
        child = Component(name="Child", component_id="child")
        root.add_child(child)

        found = root.find_by_id("child")
        assert found == child

        not_found = root.find_by_id("nonexistent")
        assert not_found is None

    def test_get_depth(self):
        """Test depth calculation."""
        root = Component(name="Root")
        c1 = Component(name="C1")
        c2 = Component(name="C2")

        root.add_child(c1)
        c1.add_child(c2)

        assert root.get_depth() == 0
        assert c1.get_depth() == 1
        assert c2.get_depth() == 2

    def test_get_path(self):
        """Test path string generation."""
        root = Component(name="Root")
        c1 = Component(name="Child1")
        c2 = Component(name="Child2")

        root.add_child(c1)
        c1.add_child(c2)

        assert c2.get_path() == "Root / Child1 / Child2"

    def test_to_dict(self):
        """Test component serialization."""
        comp = Component(
            component_id="test",
            name="Test",
            body_reference="body1"
        )
        d = comp.to_dict()
        assert d["component_id"] == "test"
        assert d["name"] == "Test"
        assert d["body_reference"] == "body1"
        assert "transform" in d

    def test_from_dict(self):
        """Test component deserialization."""
        d = {
            "component_id": "restored",
            "name": "Restored",
            "body_reference": "body2",
            "transform": {"position": [1, 2, 3], "rotation": [0, 0, 0], "scale": 1.0},
            "children": [
                {"component_id": "child1", "name": "Child", "transform": {}}
            ]
        }
        comp = Component.from_dict(d)
        assert comp.component_id == "restored"
        assert comp.name == "Restored"
        assert len(comp.children) == 1


# =============================================================================
# ComponentManager Tests
# =============================================================================

class TestComponentManager:
    """Tests for ComponentManager CRUD operations."""

    def setup_method(self):
        """Reset manager before each test."""
        self.manager = ComponentManager()

    def test_create_component(self):
        """Test component creation."""
        comp = self.manager.create_component(name="TestComp")
        assert comp.name == "TestComp"
        assert comp.component_id in self.manager._components

    def test_create_component_with_body(self):
        """Test component creation from body."""
        body = MockBody(id="body123", name="TestBody")
        comp = self.manager.create_component(body=body, name="BodyComponent")
        assert comp.body_reference == "body123"
        assert comp._body_obj == body

    def test_get_component(self):
        """Test getting component by ID."""
        comp = self.manager.create_component(name="Test")
        retrieved = self.manager.get_component(comp.component_id)
        assert retrieved == comp

        nonexistent = self.manager.get_component("nonexistent")
        assert nonexistent is None

    def test_update_component(self):
        """Test updating component properties."""
        comp = self.manager.create_component(name="Original")

        success = self.manager.update_component(
            comp.component_id,
            name="Updated",
            body_reference="new_body"
        )
        assert success is True
        assert comp.name == "Updated"
        assert comp.body_reference == "new_body"

    def test_update_nonexistent(self):
        """Test updating nonexistent component."""
        success = self.manager.update_component("nonexistent", name="Test")
        assert success is False

    def test_delete_component(self):
        """Test deleting component."""
        comp = self.manager.create_component(name="ToDelete")
        comp_id = comp.component_id

        success = self.manager.delete_component(comp_id)
        assert success is True
        assert self.manager.get_component(comp_id) is None

    def test_delete_with_children(self):
        """Test deleting component with children."""
        parent = self.manager.create_component(name="Parent")
        child = self.manager.create_component(name="Child", parent=parent)

        # Non-recursive: children become root
        self.manager.delete_component(parent.component_id)
        assert self.manager.get_component(child.component_id) is not None

        # Reset and test recursive
        parent = self.manager.create_component(name="Parent2")
        child = self.manager.create_component(name="Child2", parent=parent)
        self.manager.delete_component(parent.component_id, recursive=True)
        assert self.manager.get_component(child.component_id) is None

    def test_list_components(self):
        """Test listing all components."""
        self.manager.create_component(name="C1")
        self.manager.create_component(name="C2")
        all_comps = self.manager.list_components()
        assert len(all_comps) == 2

    def test_list_root_components(self):
        """Test listing root components."""
        parent = self.manager.create_component(name="Parent")
        child = self.manager.create_component(name="Child", parent=parent)

        roots = self.manager.list_root_components()
        assert len(roots) == 1
        assert parent in roots
        assert child not in roots

    def test_find_by_name(self):
        """Test finding components by name."""
        self.manager.create_component(name="Unique")
        self.manager.create_component(name="Duplicate")
        self.manager.create_component(name="Duplicate")

        found = self.manager.find_by_name("Duplicate")
        assert len(found) == 2

    def test_find_by_body_reference(self):
        """Test finding component by body reference."""
        body = MockBody(id="body789", name="TestBody")
        comp = self.manager.create_component(body=body, name="BodyComp")

        found = self.manager.find_by_body_reference("body789")
        assert found == comp

    def test_move_component(self):
        """Test moving component to new parent."""
        parent1 = self.manager.create_component(name="Parent1")
        parent2 = self.manager.create_component(name="Parent2")
        child = self.manager.create_component(name="Child", parent=parent1)

        assert child.parent == parent1

        self.manager.move_component(child.component_id, parent2)
        assert child.parent == parent2
        assert child in parent2.children

    def test_serialize_deserialize(self):
        """Test manager serialization."""
        parent = self.manager.create_component(name="Parent")
        child = self.manager.create_component(name="Child", parent=parent)

        data = self.manager.serialize()
        assert data["count"] == 2

        new_manager = ComponentManager.deserialize(data)
        assert new_manager.get_component_count() == 2

    def test_clear(self):
        """Test clearing all components."""
        self.manager.create_component(name="C1")
        self.manager.create_component(name="C2")
        self.manager.clear()
        assert self.manager.get_component_count() == 0


# =============================================================================
# Transform Operations Tests
# =============================================================================

class TestTransformOperations:
    """Tests for transform operations."""

    def test_apply_transform(self):
        """Test applying transform to component."""
        comp = Component(name="Test")
        t = ComponentTransform(position=(10, 20, 30))

        success = apply_transform(comp, t)
        assert success is True
        assert comp.transform.position == (10, 20, 30)

    def test_apply_transform_accumulate(self):
        """Test accumulating transforms."""
        comp = Component(name="Test")
        comp.transform = ComponentTransform(position=(5, 0, 0))

        t = ComponentTransform(position=(10, 0, 0))
        apply_transform(comp, t, accumulate=True)
        assert comp.transform.position == (15, 0, 0)

    def test_reset_transform(self):
        """Test resetting transform."""
        comp = Component(name="Test")
        comp.transform = ComponentTransform(position=(10, 10, 10))

        success = reset_transform(comp)
        assert success is True
        assert comp.transform.is_identity()

    def test_combine_transforms(self):
        """Test combining transforms."""
        t1 = ComponentTransform(position=(10, 0, 0))
        t2 = ComponentTransform(position=(0, 20, 0))

        combined = combine_transforms(t1, t2)
        assert combined.position == (10, 20, 0)

    def test_combine_with_rotation(self):
        """Test combining transforms with rotation."""
        t1 = ComponentTransform(rotation=(45, 0, 0))
        t2 = ComponentTransform(rotation=(0, 90, 0))

        combined = combine_transforms(t1, t2)
        assert combined.rotation == (45, 90, 0)

    def test_combine_with_scale(self):
        """Test combining transforms with scale."""
        t1 = ComponentTransform(scale=2.0)
        t2 = ComponentTransform(scale=1.5)

        combined = combine_transforms(t1, t2)
        assert combined.scale == 3.0

    def test_set_position(self):
        """Test setting position."""
        comp = Component(name="Test")
        set_position(comp, (100, 200, 300))
        assert comp.transform.position == (100, 200, 300)

    def test_set_rotation(self):
        """Test setting rotation."""
        comp = Component(name="Test")
        set_rotation(comp, (45, 90, 135))
        assert comp.transform.rotation == (45, 90, 135)

    def test_set_scale(self):
        """Test setting scale."""
        comp = Component(name="Test")
        set_scale(comp, 2.5)
        assert comp.transform.scale == 2.5

    def test_translate(self):
        """Test translating component."""
        comp = Component(name="Test")
        comp.transform = ComponentTransform(position=(10, 10, 10))

        translate(comp, (5, -5, 0))
        assert comp.transform.position == (15, 5, 10)

    def test_rotate(self):
        """Test rotating component."""
        comp = Component(name="Test")
        comp.transform = ComponentTransform(rotation=(10, 20, 30))

        rotate(comp, (5, 10, 15))
        assert comp.transform.rotation == (15, 30, 45)

    def test_get_world_transform(self):
        """Test world transform calculation."""
        root = Component(name="Root", component_id="root")
        root.transform = ComponentTransform(position=(10, 0, 0))

        child = Component(name="Child", component_id="child")
        child.transform = ComponentTransform(position=(5, 0, 0))
        root.add_child(child)

        world = get_world_transform(child)
        assert world.position == (15, 0, 0)  # 10 + 5

    def test_transform_operations_class(self):
        """Test TransformOperations utility class."""
        comp = Component(name="Test")

        ops = TransformOperations()
        ops.move_to(comp, (10, 20, 30))
        assert comp.transform.position == (10, 20, 30)

        ops.move_by(comp, (5, 5, 5))
        assert comp.transform.position == (15, 25, 35)

        ops.rotate_to(comp, (45, 0, 0))
        assert comp.transform.rotation == (45, 0, 0)

        ops.rotate_by(comp, (0, 45, 0))
        assert comp.transform.rotation == (45, 45, 0)

        ops.scale_to(comp, 2.0)
        assert comp.transform.scale == 2.0

        ops.reset(comp)
        assert comp.transform.is_identity()


# =============================================================================
# Integration Tests
# =============================================================================

class TestComponentIntegration:
    """Integration tests for component system."""

    def test_full_workflow(self):
        """Test complete component workflow."""
        manager = ComponentManager()

        # Create assembly structure
        assembly = manager.create_component(name="Assembly")
        part1 = manager.create_component(name="Part1", parent=assembly)
        part2 = manager.create_component(name="Part2", parent=assembly)

        # Add transforms
        set_position(part1, (0, 0, 0))
        set_position(part2, (100, 0, 0))

        # Create sub-assembly
        sub_assy = manager.create_component(name="SubAssembly", parent=part1)
        set_position(sub_assy, (10, 10, 0))

        # Verify structure
        assert len(assembly.children) == 2
        assert part1.parent == assembly
        assert sub_assy.parent == part1

        # Test world transform
        world = get_world_transform(sub_assy)
        assert world.position == (10, 10, 0)  # part1 (0,0,0) + sub_assy (10,10,0)

        # Test serialization
        data = manager.serialize()
        restored = ComponentManager.deserialize(data)
        assert restored.get_component_count() == 4

    def test_body_reference_workflow(self):
        """Test workflow with body references."""
        manager = ComponentManager()

        # Create mock bodies
        body1 = MockBody(id="body_001", name="Body1")
        body2 = MockBody(id="body_002", name="Body2")

        # Create components from bodies
        comp1 = manager.create_component(body=body1, name="Part1")
        comp2 = manager.create_component(body=body2, name="Part2")

        # Find by body reference
        found = manager.find_by_body_reference("body_001")
        assert found == comp1

        # Update body reference
        manager.update_component(comp2.component_id, body_reference="new_body_ref")
        assert comp2.body_reference == "new_body_ref"


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_component_operations(self):
        """Test operations with None component."""
        assert apply_transform(None, ComponentTransform()) is False
        assert reset_transform(None) is False
        assert set_position(None, (0, 0, 0)) is False

    def test_empty_manager_operations(self):
        """Test operations on empty manager."""
        manager = ComponentManager()
        assert manager.get_component("nonexistent") is None
        assert manager.update_component("nonexistent", name="Test") is False
        assert manager.delete_component("nonexistent") is False
        assert len(manager.list_components()) == 0

    def test_circular_parent_prevention(self):
        """Test that circular parent relationships are handled."""
        # Note: The current implementation doesn't explicitly prevent cycles
        # This test documents expected behavior
        root = Component(name="Root")
        child = Component(name="Child")
        root.add_child(child)

        # Attempting to make root a child of child would create a cycle
        # Current implementation allows this (potential improvement)
        # This test verifies current behavior
        assert child.parent == root

    def test_large_hierarchy(self):
        """Test performance with large hierarchy."""
        manager = ComponentManager()
        root = manager.create_component(name="Root")

        # Create 100 nested components
        current = root
        for i in range(100):
            current = manager.create_component(name=f"Level{i}", parent=current)

        assert manager.get_component_count() == 101

        # Test finding deep component
        deep = manager.find_by_name("Level99")[0]
        assert deep.get_depth() == 100

    def test_transform_precision(self):
        """Test transform precision."""
        comp = Component(name="Test")
        t = ComponentTransform(
            position=(0.123456789, 0.987654321, 0.555555555),
            rotation=(0.111111111, 0.222222222, 0.333333333)
        )
        apply_transform(comp, t)

        # Values should be preserved
        assert comp.transform.position[0] == pytest.approx(0.123456789, rel=1e-9)
        assert comp.transform.rotation[2] == pytest.approx(0.333333333, rel=1e-9)


# =============================================================================
# Feature Flag Test
# =============================================================================

class TestFeatureFlag:
    """Test that assembly_system feature flag has been removed (feature integrated)."""

    def test_assembly_feature_flag_removed(self):
        """Verify assembly_system feature flag was removed (feature is now integrated)."""
        from config.feature_flags import is_enabled
        # Flag was removed after feature integration
        assert is_enabled("assembly_system") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
