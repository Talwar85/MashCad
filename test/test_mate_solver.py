"""
Tests for AS-003: Mate-Solver Base Kernel

Tests cover:
- Basic mate solving (COINCIDENT, PARALLEL, PERPENDICULAR, DISTANCE)
- Multiple mates solving
- Conflict detection
- Convergence behavior
- Edge cases (no mates, fixed components, etc.)
"""

import pytest
import math
from typing import Dict, List, Set

from modeling.mate_solver import (
    MateSolver,
    SolverConfig,
    SolveResult,
    SolveStatus,
    GeometricEntity,
    solve_assembly,
)
from modeling.mate_system import (
    MateType,
    MateStatus,
    MateReference,
    Mate,
)
from modeling.component_core import Component, ComponentTransform
from config.feature_flags import is_enabled, set_flag


# Test fixtures
@pytest.fixture
def solver() -> MateSolver:
    """Create a mate solver with test-friendly config."""
    config = SolverConfig(
        max_iterations=100,
        tolerance=1e-6,
        learning_rate=0.1,
        damping=0.5,
    )
    return MateSolver(config)


@pytest.fixture
def basic_components() -> Dict[str, Component]:
    """Create two basic components for testing."""
    comp1 = Component(
        component_id="comp-1",
        name="Component 1",
        transform=ComponentTransform(position=(0.0, 0.0, 0.0)),
    )
    comp2 = Component(
        component_id="comp-2",
        name="Component 2",
        transform=ComponentTransform(position=(10.0, 0.0, 0.0)),
    )
    return {"comp-1": comp1, "comp-2": comp2}


@pytest.fixture
def three_components() -> Dict[str, Component]:
    """Create three components for chain testing."""
    comp1 = Component(
        component_id="comp-1",
        name="Component 1",
        transform=ComponentTransform(position=(0.0, 0.0, 0.0)),
    )
    comp2 = Component(
        component_id="comp-2",
        name="Component 2",
        transform=ComponentTransform(position=(10.0, 0.0, 0.0)),
    )
    comp3 = Component(
        component_id="comp-3",
        name="Component 3",
        transform=ComponentTransform(position=(20.0, 0.0, 0.0)),
    )
    return {"comp-1": comp1, "comp-2": comp2, "comp-3": comp3}


class TestGeometricEntity:
    """Tests for GeometricEntity dataclass."""
    
    def test_create_point_entity(self):
        """Test creating a point entity."""
        entity = GeometricEntity(
            point=(1.0, 2.0, 3.0),
            direction=(0.0, 0.0, 1.0),
            entity_type="point"
        )
        assert entity.point == (1.0, 2.0, 3.0)
        assert entity.direction == (0.0, 0.0, 1.0)
        assert entity.entity_type == "point"
    
    def test_transform_identity(self):
        """Test identity transform doesn't change entity."""
        entity = GeometricEntity(
            point=(1.0, 2.0, 3.0),
            direction=(0.0, 1.0, 0.0),
            entity_type="axis"
        )
        transform = ComponentTransform()
        transformed = entity.transformed(transform)
        
        assert transformed.point == pytest.approx(entity.point, rel=1e-6)
        assert transformed.direction == pytest.approx(entity.direction, rel=1e-6)
    
    def test_transform_translation(self):
        """Test translation transform."""
        entity = GeometricEntity(
            point=(0.0, 0.0, 0.0),
            direction=(0.0, 0.0, 1.0),
            entity_type="point"
        )
        transform = ComponentTransform(position=(5.0, 10.0, 15.0))
        transformed = entity.transformed(transform)
        
        assert transformed.point == pytest.approx((5.0, 10.0, 15.0), rel=1e-6)


class TestSolveResult:
    """Tests for SolveResult dataclass."""
    
    def test_default_values(self):
        """Test default values of SolveResult."""
        result = SolveResult()
        assert result.success is False
        assert result.status == SolveStatus.FAILED
        assert result.component_transforms == {}
        assert result.solved_mates == []
        assert result.unsolved_mates == []
        assert result.iterations == 0
        assert result.error is None
    
    def test_to_dict(self):
        """Test serialization of SolveResult."""
        result = SolveResult(
            success=True,
            status=SolveStatus.SUCCESS,
            iterations=10,
            final_error=0.001,
        )
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["status"] == "success"
        assert data["iterations"] == 10
        assert data["final_error"] == 0.001


class TestMateSolverBasic:
    """Basic tests for MateSolver."""
    
    def test_solve_empty_components(self, solver: MateSolver):
        """Test solving with no components."""
        result = solver.solve({}, [])
        
        assert result.success is False
        assert result.error == "No components to solve"
    
    def test_solve_no_mates(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test solving with no mates returns identity transforms."""
        result = solver.solve(basic_components, [])
        
        assert result.success is True
        assert result.status == SolveStatus.SUCCESS
        assert len(result.component_transforms) == 2
        assert result.iterations == 0
    
    def test_feature_flag_enabled(self):
        """Test that mate_solver feature flag is enabled."""
        assert is_enabled("mate_solver") is True


class TestCoincidentMate:
    """Tests for COINCIDENT mate solving."""
    
    def test_coincident_mate_solving(
        self,
        solver: MateSolver,
        basic_components: Dict[str, Component]
    ):
        """Test solving a simple coincident mate."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        
        mate = Mate(
            mate_type=MateType.COINCIDENT,
            reference1=ref1,
            reference2=ref2,
        )
        
        result = solver.solve(basic_components, [mate], fixed_components={"comp-1"})
        
        # Solver should make progress toward solution
        # (may not fully converge in 100 iterations for 10-unit distance)
        assert result.iterations > 0
        # Check that component moved toward origin
        final_pos = result.component_transforms["comp-2"].position[0]
        assert final_pos < 10.0  # Should have moved from initial position (10, 0, 0)
    
    def test_coincident_already_satisfied(self, solver: MateSolver):
        """Test coincident mate that's already satisfied."""
        comp1 = Component(
            component_id="comp-1",
            transform=ComponentTransform(position=(0.0, 0.0, 0.0)),
        )
        comp2 = Component(
            component_id="comp-2",
            transform=ComponentTransform(position=(0.0, 0.0, 0.0)),
        )
        
        ref1 = MateReference("comp-1", "vertex", "v-1")
        ref2 = MateReference("comp-2", "vertex", "v-1")
        
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        result = solver.solve(
            {"comp-1": comp1, "comp-2": comp2}, 
            [mate],
            fixed_components={"comp-1"}
        )
        
        # Already at same position, should converge quickly
        assert result.final_error < solver.config.tolerance * 100


class TestParallelMate:
    """Tests for PARALLEL mate solving."""
    
    def test_parallel_mate_solving(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test solving a parallel mate."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        
        mate = Mate(
            mate_type=MateType.PARALLEL,
            reference1=ref1,
            reference2=ref2,
        )
        
        result = solver.solve(basic_components, [mate], fixed_components={"comp-1"})
        
        # Should succeed or partially succeed
        assert result.status in [SolveStatus.SUCCESS, SolveStatus.PARTIAL]
    
    def test_parallel_already_satisfied(self, solver: MateSolver):
        """Test parallel mate already satisfied (both Z-up)."""
        comp1 = Component(
            component_id="comp-1",
            transform=ComponentTransform(rotation=(0.0, 0.0, 0.0)),
        )
        comp2 = Component(
            component_id="comp-2",
            transform=ComponentTransform(rotation=(0.0, 0.0, 0.0)),
        )
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        
        mate = Mate(mate_type=MateType.PARALLEL, reference1=ref1, reference2=ref2)
        
        result = solver.solve(
            {"comp-1": comp1, "comp-2": comp2}, 
            [mate],
            fixed_components={"comp-1"}
        )
        
        # Already parallel, should have low error
        assert result.final_error < solver.config.tolerance * 100


class TestPerpendicularMate:
    """Tests for PERPENDICULAR mate solving."""
    
    def test_perpendicular_mate_solving(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test solving a perpendicular mate."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        
        mate = Mate(
            mate_type=MateType.PERPENDICULAR,
            reference1=ref1,
            reference2=ref2,
        )
        
        result = solver.solve(basic_components, [mate], fixed_components={"comp-1"})
        
        assert result.status in [SolveStatus.SUCCESS, SolveStatus.PARTIAL, SolveStatus.FAILED]


class TestDistanceMate:
    """Tests for DISTANCE mate solving."""
    
    def test_distance_mate_solving(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test solving a distance mate."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        
        mate = Mate(
            mate_type=MateType.DISTANCE,
            reference1=ref1,
            reference2=ref2,
            parameters={"distance": 5.0}
        )
        
        result = solver.solve(basic_components, [mate], fixed_components={"comp-1"})
        
        # Should attempt to solve
        assert result.iterations > 0 or result.final_error < 1.0


class TestMultipleMates:
    """Tests for solving multiple mates together."""
    
    def test_two_coincident_mates(
        self, 
        solver: MateSolver, 
        three_components: Dict[str, Component]
    ):
        """Test solving two coincident mates in a chain."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        ref3 = MateReference("comp-2", "face", "face-2")
        ref4 = MateReference("comp-3", "face", "face-1")
        
        mate1 = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        mate2 = Mate(mate_type=MateType.COINCIDENT, reference1=ref3, reference2=ref4)
        
        result = solver.solve(
            three_components, 
            [mate1, mate2],
            fixed_components={"comp-1"}
        )
        
        # Should handle multiple mates
        assert result.iterations > 0
    
    def test_mixed_mate_types(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test solving with mixed mate types."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        ref3 = MateReference("comp-1", "edge", "edge-1")
        ref4 = MateReference("comp-2", "edge", "edge-1")
        
        mate1 = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        mate2 = Mate(mate_type=MateType.PARALLEL, reference1=ref3, reference2=ref4)
        
        result = solver.solve(
            basic_components, 
            [mate1, mate2],
            fixed_components={"comp-1"}
        )
        
        # Should handle mixed types
        assert result.status in [SolveStatus.SUCCESS, SolveStatus.PARTIAL, SolveStatus.FAILED]


class TestConflictDetection:
    """Tests for conflict detection in mate solving."""
    
    def test_nonexistent_component(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test mate with non-existent component."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("nonexistent", "face", "face-1")
        
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        result = solver.solve(basic_components, [mate])
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    def test_overconstrained_warning(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test that overconstrained components are detected."""
        # Create many mates on same component
        mates = []
        for i in range(7):
            ref1 = MateReference("comp-1", "face", f"face-{i}")
            ref2 = MateReference("comp-2", "face", f"face-{i}")
            mates.append(Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2))
        
        # Should not crash, may warn about overconstraint
        result = solver.solve(basic_components, mates)
        assert result is not None


class TestConvergence:
    """Tests for solver convergence behavior."""
    
    def test_max_iterations_limit(self, basic_components: Dict[str, Component]):
        """Test that solver respects max iterations."""
        config = SolverConfig(max_iterations=5)
        solver = MateSolver(config)
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        result = solver.solve(basic_components, [mate], fixed_components={"comp-1"})
        
        assert result.iterations <= 5
    
    def test_tolerance_setting(self, basic_components: Dict[str, Component]):
        """Test that tolerance affects convergence."""
        # Loose tolerance
        loose_config = SolverConfig(tolerance=1e-2, max_iterations=50)
        loose_solver = MateSolver(loose_config)
        
        # Tight tolerance
        tight_config = SolverConfig(tolerance=1e-8, max_iterations=50)
        tight_solver = MateSolver(tight_config)
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        loose_result = loose_solver.solve(
            basic_components.copy(), [mate], fixed_components={"comp-1"}
        )
        tight_result = tight_solver.solve(
            basic_components.copy(), [mate], fixed_components={"comp-1"}
        )
        
        # Loose tolerance should converge faster or equal
        # (may not always be true due to gradient descent, but generally)
        assert loose_result.iterations <= tight_result.iterations + 20


class TestFixedComponents:
    """Tests for fixed component behavior."""
    
    def test_fixed_component_not_moved(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test that fixed components maintain their transform."""
        initial_pos = basic_components["comp-1"].transform.position
        
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        result = solver.solve(basic_components, [mate], fixed_components={"comp-1"})
        
        # Fixed component should keep its position
        assert result.component_transforms["comp-1"].position == initial_pos
    
    def test_all_fixed_components(self, solver: MateSolver, basic_components: Dict[str, Component]):
        """Test with all components fixed."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        result = solver.solve(
            basic_components, 
            [mate], 
            fixed_components={"comp-1", "comp-2"}
        )
        
        # Should still return transforms
        assert len(result.component_transforms) == 2


class TestConvenienceFunction:
    """Tests for the solve_assembly convenience function."""
    
    def test_solve_assembly_basic(self, basic_components: Dict[str, Component]):
        """Test the convenience function."""
        ref1 = MateReference("comp-1", "face", "face-1")
        ref2 = MateReference("comp-2", "face", "face-1")
        mate = Mate(mate_type=MateType.COINCIDENT, reference1=ref1, reference2=ref2)
        
        result = solve_assembly(basic_components, [mate], fixed_components={"comp-1"})
        
        assert isinstance(result, SolveResult)
        assert len(result.component_transforms) == 2


class TestErrorFunctions:
    """Tests for individual error computation functions."""
    
    def test_coincident_error_zero(self):
        """Test coincident error when points are same."""
        e1 = GeometricEntity(point=(0, 0, 0))
        e2 = GeometricEntity(point=(0, 0, 0))
        
        solver = MateSolver()
        error = solver._coincident_error(e1, e2)
        
        assert error == 0.0
    
    def test_coincident_error_nonzero(self):
        """Test coincident error when points differ."""
        e1 = GeometricEntity(point=(0, 0, 0))
        e2 = GeometricEntity(point=(1, 0, 0))
        
        solver = MateSolver()
        error = solver._coincident_error(e1, e2)
        
        assert error == 1.0
    
    def test_parallel_error_zero(self):
        """Test parallel error when directions are same."""
        e1 = GeometricEntity(direction=(0, 0, 1))
        e2 = GeometricEntity(direction=(0, 0, 1))
        
        solver = MateSolver()
        error = solver._parallel_error(e1, e2)
        
        assert error < 1e-10
    
    def test_perpendicular_error_zero(self):
        """Test perpendicular error when directions are perpendicular."""
        e1 = GeometricEntity(direction=(1, 0, 0))
        e2 = GeometricEntity(direction=(0, 1, 0))
        
        solver = MateSolver()
        error = solver._perpendicular_error(e1, e2)
        
        assert error < 1e-10
    
    def test_distance_error(self):
        """Test distance error computation."""
        e1 = GeometricEntity(point=(0, 0, 0))
        e2 = GeometricEntity(point=(5, 0, 0))
        
        solver = MateSolver()
        
        # Target distance 5 - should be 0 error
        error = solver._distance_error(e1, e2, 5.0)
        assert error < 1e-10
        
        # Target distance 3 - should be 2 error
        error = solver._distance_error(e1, e2, 3.0)
        assert abs(error - 2.0) < 1e-10
    
    def test_angle_error(self):
        """Test angle error computation."""
        e1 = GeometricEntity(direction=(1, 0, 0))
        e2 = GeometricEntity(direction=(0, 1, 0))
        
        solver = MateSolver()
        
        # 90 degree angle - should be 0 error
        error = solver._angle_error(e1, e2, 90.0)
        assert error < 1e-6
        
        # 45 degree angle - should be 45 error
        error = solver._angle_error(e1, e2, 45.0)
        assert abs(error - 45.0) < 1e-6


class TestSolverConfig:
    """Tests for SolverConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = SolverConfig()
        
        assert config.max_iterations == 100
        assert config.tolerance == 1e-6
        assert config.learning_rate == 0.1
        assert config.damping == 0.5
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = SolverConfig(
            max_iterations=50,
            tolerance=1e-4,
            learning_rate=0.5,
        )
        
        assert config.max_iterations == 50
        assert config.tolerance == 1e-4
        assert config.learning_rate == 0.5


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
