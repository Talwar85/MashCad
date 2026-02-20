"""
Tests for AS-002: Mate System V1

Tests cover:
- Mate creation
- Mate validation
- Conflict detection
- Serialization/deserialization
"""

import pytest
from modeling.mate_system import (
    MateType,
    MateStatus,
    MateReference,
    Mate,
    MateConflict,
    MateManager,
    create_coincident_mate,
    create_distance_mate,
)
from config.feature_flags import is_enabled, set_flag


class TestMateReference:
    """Tests for MateReference dataclass."""
    
    def test_create_valid_face_reference(self):
        """Test creating a valid face reference."""
        ref = MateReference(
            component_id="comp-1",
            reference_type="face",
            reference_id="face-hash-123"
        )
        assert ref.component_id == "comp-1"
        assert ref.reference_type == "face"
        assert ref.reference_id == "face-hash-123"
    
    def test_create_valid_edge_reference(self):
        """Test creating a valid edge reference."""
        ref = MateReference(
            component_id="comp-2",
            reference_type="edge",
            reference_id="edge-hash-456"
        )
        assert ref.reference_type == "edge"
    
    def test_create_valid_vertex_reference(self):
        """Test creating a valid vertex reference."""
        ref = MateReference(
            component_id="comp-3",
            reference_type="vertex",
            reference_id="vertex-789"
        )
        assert ref.reference_type == "vertex"
    
    def test_create_valid_axis_reference(self):
        """Test creating a valid axis reference."""
        ref = MateReference(
            component_id="comp-4",
            reference_type="axis",
            reference_id="axis-z"
        )
        assert ref.reference_type == "axis"
    
    def test_invalid_reference_type_raises_error(self):
        """Test that invalid reference type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            MateReference(
                component_id="comp-1",
                reference_type="invalid_type",
                reference_id="some-id"
            )
        assert "Invalid reference_type" in str(exc_info.value)
    
    def test_serialize_deserialize(self):
        """Test serialization and deserialization."""
        ref = MateReference(
            component_id="comp-1",
            reference_type="face",
            reference_id="face-hash-123"
        )
        data = ref.to_dict()
        restored = MateReference.from_dict(data)
        
        assert restored.component_id == ref.component_id
        assert restored.reference_type == ref.reference_type
        assert restored.reference_id == ref.reference_id


class TestMate:
    """Tests for Mate dataclass."""
    
    def test_create_coincident_mate(self):
        """Test creating a coincident mate."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = Mate(
            mate_type=MateType.COINCIDENT,
            reference1=ref1,
            reference2=ref2,
        )
        
        assert mate.mate_type == MateType.COINCIDENT
        assert mate.reference1 == ref1
        assert mate.reference2 == ref2
        assert mate.status == MateStatus.OK
        assert mate.mate_id  # Should have auto-generated ID
        assert mate.name  # Should have auto-generated name
    
    def test_create_distance_mate_with_params(self):
        """Test creating a distance mate with parameters."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = Mate(
            mate_type=MateType.DISTANCE,
            reference1=ref1,
            reference2=ref2,
            parameters={"distance": 10.0}
        )
        
        assert mate.mate_type == MateType.DISTANCE
        assert mate.parameters["distance"] == 10.0
    
    def test_create_angle_mate_with_params(self):
        """Test creating an angle mate with parameters."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = Mate(
            mate_type=MateType.ANGLE,
            reference1=ref1,
            reference2=ref2,
            parameters={"angle": 45.0}
        )
        
        assert mate.mate_type == MateType.ANGLE
        assert mate.parameters["angle"] == 45.0
    
    def test_involves_component(self):
        """Test checking if mate involves a component."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = Mate(
            mate_type=MateType.COINCIDENT,
            reference1=ref1,
            reference2=ref2,
        )
        
        assert mate.involves_component("comp-1")
        assert mate.involves_component("comp-2")
        assert not mate.involves_component("comp-3")
    
    def test_get_other_component(self):
        """Test getting the other component in a mate."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = Mate(
            mate_type=MateType.COINCIDENT,
            reference1=ref1,
            reference2=ref2,
        )
        
        assert mate.get_other_component("comp-1") == "comp-2"
        assert mate.get_other_component("comp-2") == "comp-1"
        assert mate.get_other_component("comp-3") is None
    
    def test_serialize_deserialize(self):
        """Test mate serialization and deserialization."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = Mate(
            mate_type=MateType.DISTANCE,
            reference1=ref1,
            reference2=ref2,
            parameters={"distance": 25.5},
            status=MateStatus.OK,
            name="Test Distance Mate"
        )
        
        data = mate.to_dict()
        restored = Mate.from_dict(data)
        
        assert restored.mate_id == mate.mate_id
        assert restored.mate_type == MateType.DISTANCE
        assert restored.reference1.component_id == "comp-1"
        assert restored.reference2.component_id == "comp-2"
        assert restored.parameters["distance"] == 25.5
        assert restored.status == MateStatus.OK
        assert restored.name == "Test Distance Mate"


class TestMateManager:
    """Tests for MateManager class."""
    
    def test_feature_flag_enabled(self):
        """Test that mate_system_v1 feature flag is enabled."""
        assert is_enabled("mate_system_v1"), "mate_system_v1 flag should be enabled"
    
    def test_create_manager(self):
        """Test creating a mate manager."""
        manager = MateManager()
        assert len(manager.get_all_mates()) == 0
    
    def test_create_mate(self):
        """Test creating a mate through the manager."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        
        assert mate.mate_type == MateType.COINCIDENT
        assert mate.reference1 == ref1
        assert mate.reference2 == ref2
        assert len(manager.get_all_mates()) == 1
    
    def test_create_mate_same_component_raises_error(self):
        """Test that creating a mate on the same component raises error."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-1", "face", "face-2")
        
        with pytest.raises(ValueError) as exc_info:
            manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        
        assert "same component" in str(exc_info.value).lower()
    
    def test_create_distance_mate_without_distance_raises_error(self):
        """Test that distance mate without distance parameter raises error."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        with pytest.raises(ValueError) as exc_info:
            manager.create_mate(MateType.DISTANCE, ref1, ref2)
        
        assert "distance" in str(exc_info.value).lower()
    
    def test_create_angle_mate_without_angle_raises_error(self):
        """Test that angle mate without angle parameter raises error."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        with pytest.raises(ValueError) as exc_info:
            manager.create_mate(MateType.ANGLE, ref1, ref2)
        
        assert "angle" in str(exc_info.value).lower()
    
    def test_delete_mate(self):
        """Test deleting a mate."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        assert len(manager.get_all_mates()) == 1
        
        result = manager.delete_mate(mate.mate_id)
        assert result is True
        assert len(manager.get_all_mates()) == 0
    
    def test_delete_nonexistent_mate(self):
        """Test deleting a mate that doesn't exist."""
        manager = MateManager()
        
        result = manager.delete_mate("nonexistent-id")
        assert result is False
    
    def test_get_mate(self):
        """Test getting a mate by ID."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        
        retrieved = manager.get_mate(mate.mate_id)
        assert retrieved is not None
        assert retrieved.mate_id == mate.mate_id
    
    def test_get_mates_for_component(self):
        """Test getting all mates for a component."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        ref3 = MateReference("comp-3", "face", "face-3")
        
        mate1 = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        mate2 = manager.create_mate(MateType.PARALLEL, ref1, ref3)
        
        comp1_mates = manager.get_mates_for_component("comp-1")
        assert len(comp1_mates) == 2
        
        comp2_mates = manager.get_mates_for_component("comp-2")
        assert len(comp2_mates) == 1
        assert comp2_mates[0].mate_id == mate1.mate_id
    
    def test_validate_mate_ok(self):
        """Test validating a valid mate."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        status = manager.validate_mate(mate)
        
        assert status == MateStatus.OK
    
    def test_validate_mate_missing_reference(self):
        """Test validating a mate with missing reference."""
        manager = MateManager()
        
        mate = Mate(
            mate_type=MateType.COINCIDENT,
            reference1=None,
            reference2=MateReference("comp-2", "face", "face-2"),
        )
        
        status = manager.validate_mate(mate)
        assert status == MateStatus.ERROR
    
    def test_clear_all_mates(self):
        """Test clearing all mates."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        ref3 = MateReference("comp-3", "face", "face-3")
        
        manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        manager.create_mate(MateType.PARALLEL, ref1, ref3)
        
        assert len(manager.get_all_mates()) == 2
        
        manager.clear_all_mates()
        
        assert len(manager.get_all_mates()) == 0
        assert len(manager.get_mates_for_component("comp-1")) == 0


class TestMateConflictDetection:
    """Tests for mate conflict detection."""
    
    def test_no_conflicts_single_mate(self):
        """Test that a single mate has no conflicts."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        
        conflicts = manager.get_mate_conflicts()
        assert len(conflicts) == 0
    
    def test_conflict_coincident_and_distance(self):
        """Test detection of coincident + distance conflict."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        manager.create_mate(MateType.DISTANCE, ref1, ref2, distance=10.0)
        
        conflicts = manager.get_mate_conflicts()
        assert len(conflicts) >= 1
        
        # Check that conflict involves COINCIDENT and DISTANCE
        conflict = conflicts[0]
        assert "COINCIDENT" in conflict.description or "DISTANCE" in conflict.description
    
    def test_conflict_parallel_and_perpendicular(self):
        """Test detection of parallel + perpendicular conflict."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        manager.create_mate(MateType.PARALLEL, ref1, ref2)
        manager.create_mate(MateType.PERPENDICULAR, ref1, ref2)
        
        conflicts = manager.get_mate_conflicts()
        assert len(conflicts) >= 1
        
        conflict = conflicts[0]
        assert conflict.conflict_type == "incompatible"
    
    def test_no_conflict_different_connections(self):
        """Test that mates on different connections don't conflict."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        ref3 = MateReference("comp-3", "face", "face-3")
        
        # comp-1 <-> comp-2
        manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        # comp-1 <-> comp-3 (different connection, no conflict)
        manager.create_mate(MateType.DISTANCE, ref1, ref3, distance=10.0)
        
        conflicts = manager.get_mate_conflicts()
        assert len(conflicts) == 0
    
    def test_validate_mate_with_conflict(self):
        """Test that validate_mate sets CONFLICT status when mates conflict."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        # Create first mate
        mate1 = manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        
        # Create conflicting mate (bypassing manager validation)
        mate2 = Mate(
            mate_type=MateType.DISTANCE,
            reference1=ref1,
            reference2=ref2,
            parameters={"distance": 10.0}
        )
        
        # Manually add to manager's internal storage to test conflict detection
        manager._mates[mate2.mate_id] = mate2
        manager._add_to_component_index(mate2.mate_id, ref1.component_id)
        manager._add_to_component_index(mate2.mate_id, ref2.component_id)
        
        # Now validate - should detect conflict with mate1
        status = manager.validate_mate(mate2)
        assert status == MateStatus.CONFLICT


class TestMateManagerSerialization:
    """Tests for MateManager serialization."""
    
    def test_serialize_empty_manager(self):
        """Test serializing an empty manager."""
        manager = MateManager()
        data = manager.to_dict()
        
        assert "mates" in data
        assert len(data["mates"]) == 0
    
    def test_serialize_with_mates(self):
        """Test serializing a manager with mates."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        manager.create_mate(MateType.COINCIDENT, ref1, ref2)
        manager.create_mate(MateType.PARALLEL, ref1, ref2)
        
        data = manager.to_dict()
        
        assert len(data["mates"]) == 2
    
    def test_deserialize(self):
        """Test deserializing a manager."""
        # Create and serialize
        manager1 = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        mate1 = manager1.create_mate(MateType.COINCIDENT, ref1, ref2)
        mate2 = manager1.create_mate(MateType.DISTANCE, ref1, ref2, distance=15.0)
        
        data = manager1.to_dict()
        
        # Deserialize
        manager2 = MateManager.from_dict(data)
        
        assert len(manager2.get_all_mates()) == 2
        
        # Verify mates are restored
        restored_mate1 = manager2.get_mate(mate1.mate_id)
        assert restored_mate1 is not None
        assert restored_mate1.mate_type == MateType.COINCIDENT
        
        restored_mate2 = manager2.get_mate(mate2.mate_id)
        assert restored_mate2 is not None
        assert restored_mate2.mate_type == MateType.DISTANCE
        assert restored_mate2.parameters["distance"] == 15.0
        
        # Verify component index is rebuilt
        comp1_mates = manager2.get_mates_for_component("comp-1")
        assert len(comp1_mates) == 2


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_create_coincident_mate_function(self):
        """Test the create_coincident_mate convenience function."""
        manager = MateManager()
        
        mate = create_coincident_mate(
            manager,
            "comp-1", "face", "face-1",
            "comp-2", "face", "face-2",
            name="Test Coincident"
        )
        
        assert mate.mate_type == MateType.COINCIDENT
        assert mate.name == "Test Coincident"
        assert mate.reference1.component_id == "comp-1"
        assert mate.reference2.component_id == "comp-2"
    
    def test_create_distance_mate_function(self):
        """Test the create_distance_mate convenience function."""
        manager = MateManager()
        
        mate = create_distance_mate(
            manager,
            "comp-1", "face", "face-1",
            "comp-2", "face", "face-2",
            distance=25.0,
            name="Test Distance"
        )
        
        assert mate.mate_type == MateType.DISTANCE
        assert mate.parameters["distance"] == 25.0
        assert mate.name == "Test Distance"


class TestAllMateTypes:
    """Tests for all mate types."""
    
    def test_all_mate_types_exist(self):
        """Test that all required mate types are defined."""
        required_types = [
            "COINCIDENT",
            "PARALLEL",
            "PERPENDICULAR",
            "DISTANCE",
            "ANGLE",
            "TANGENT",
            "ALIGN",
        ]
        
        for type_name in required_types:
            assert hasattr(MateType, type_name), f"MateType.{type_name} should exist"
    
    def test_create_all_mate_types(self):
        """Test creating mates of all types."""
        manager = MateManager()
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-2")
        
        # Types without parameters
        for mate_type in [MateType.COINCIDENT, MateType.PARALLEL, 
                         MateType.PERPENDICULAR, MateType.TANGENT, MateType.ALIGN]:
            mate = manager.create_mate(mate_type, ref1, ref2)
            assert mate.mate_type == mate_type
        
        # Types with parameters
        manager.create_mate(MateType.DISTANCE, ref1, ref2, distance=10.0)
        manager.create_mate(MateType.ANGLE, ref1, ref2, angle=45.0)


class TestAllMateStatuses:
    """Tests for all mate statuses."""
    
    def test_all_statuses_exist(self):
        """Test that all required statuses are defined."""
        required_statuses = [
            "OK",
            "WARNING",
            "ERROR",
            "CONFLICT",
        ]
        
        for status_name in required_statuses:
            assert hasattr(MateStatus, status_name), f"MateStatus.{status_name} should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
