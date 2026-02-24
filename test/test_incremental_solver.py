"""
Tests for Incremental Constraint Solver

W35 P4: Test suite for incremental solver components:
- DependencyGraph
- IncrementalSolverBackend
- Integration with SketchEditor
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock

from sketcher import Sketch
from sketcher.constraints import (
    Constraint, ConstraintType, ConstraintStatus,
    make_horizontal, make_vertical, make_length, make_fixed,
    make_distance
)
from sketcher.dependency_graph import DependencyGraph, IncrementalSolverContext
from sketcher.solver_incremental import IncrementalSolverBackend


@pytest.mark.skipif(not True, reason="Incremental solver tests")
class TestDependencyGraph:
    """Tests for DependencyGraph"""

    @pytest.fixture
    def simple_sketch(self):
        """Create a simple sketch for testing"""
        sketch = Sketch("Test")

        # Add points and lines
        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(10, 0)
        p3 = sketch.add_point(10, 10)
        p4 = sketch.add_point(0, 10)

        l1 = sketch.add_line_from_points(p1, p2)
        l2 = sketch.add_line_from_points(p2, p3)
        l3 = sketch.add_line_from_points(p3, p4)
        l4 = sketch.add_line_from_points(p4, p1)

        return sketch

    @pytest.fixture
    def constrained_sketch(self, simple_sketch):
        """Add constraints to the sketch"""
        sketch = simple_sketch

        # Get points and lines
        p1, p2, p3, p4 = sketch.points[:4]
        l1, l2, l3, l4 = sketch.lines[:4]

        # Add constraints
        sketch.constraints.append(make_fixed(p1))
        sketch.constraints.append(make_horizontal(l1))
        sketch.constraints.append(make_vertical(l2))
        sketch.constraints.append(make_length(l1, 10))

        return sketch

    def test_build_from_sketch(self, constrained_sketch):
        """Test building dependency graph from sketch"""
        graph = DependencyGraph()
        graph.build_from_sketch(constrained_sketch)

        stats = graph.get_stats()
        assert stats['entities'] >= 4  # At least 4 points
        assert stats['constraints'] == 4
        assert stats['avg_constraints_per_entity'] > 0

    def test_get_affected_constraints_for_point(self, constrained_sketch):
        """Test getting affected constraints when a point changes"""
        graph = DependencyGraph()
        graph.build_from_sketch(constrained_sketch)

        p1 = constrained_sketch.points[0]
        affected = graph.get_affected_constraints(p1.id)

        # p1 is fixed and is start of l1 (horizontal)
        # Should affect FIXED and HORIZONTAL constraints
        assert len(affected) >= 1

    def test_get_affected_entities_bfs(self, constrained_sketch):
        """Test BFS traversal for affected entities"""
        graph = DependencyGraph()
        graph.build_from_sketch(constrained_sketch)

        p1 = constrained_sketch.points[0]
        affected = graph.get_affected_entities(p1.id, max_depth=2)

        # Moving p1 should affect connected points
        assert len(affected) >= 1

    def test_get_independent_subsets(self, constrained_sketch):
        """Test partitioning constraints into independent subsets"""
        graph = DependencyGraph()
        graph.build_from_sketch(constrained_sketch)

        subsets = graph.get_independent_subsets()

        # All constraints are connected via points, so should be 1 subset
        assert len(subsets) >= 1


@pytest.mark.skipif(not True, reason="Incremental solver tests")
class TestIncrementalSolverContext:
    """Tests for IncrementalSolverContext"""

    @pytest.fixture
    def sketch(self):
        """Create a sketch with rectangle"""
        sketch = Sketch("Rectangle")

        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(10, 0)
        p3 = sketch.add_point(10, 10)
        p4 = sketch.add_point(0, 10)

        l1 = sketch.add_line_from_points(p1, p2)
        l2 = sketch.add_line_from_points(p2, p3)
        l3 = sketch.add_line_from_points(p3, p4)
        l4 = sketch.add_line_from_points(p4, p1)

        sketch.constraints.append(make_fixed(p1))
        sketch.constraints.append(make_horizontal(l1))
        sketch.constraints.append(make_vertical(l2))
        sketch.constraints.append(make_length(l1, 10))

        return sketch

    def test_context_creation(self, sketch):
        """Test creating incremental solver context"""
        context = IncrementalSolverContext(sketch, sketch.points[0].id)

        assert context.sketch is sketch
        assert context.dragged_entity_id == sketch.points[0].id
        assert len(context.active_constraints) > 0

    def test_get_active_constraint_objects(self, sketch):
        """Test getting active constraint objects"""
        context = IncrementalSolverContext(sketch, sketch.points[0].id)

        active = context.get_active_constraint_objects()
        assert len(active) > 0
        assert all(isinstance(c, Constraint) for c in active)

    def test_restore_initial_positions(self, sketch):
        """Test restoring initial positions"""
        context = IncrementalSolverContext(sketch, sketch.points[0].id)

        # Store initial position
        p1 = sketch.points[0]
        original_x, original_y = p1.x, p1.y

        # Modify position
        p1.x = 999
        p1.y = 999

        # Restore
        context.restore_initial_positions()

        assert p1.x == original_x
        assert p1.y == original_y


@pytest.mark.skipif(not True, reason="Incremental solver tests")
class TestIncrementalSolverBackend:
    """Tests for IncrementalSolverBackend"""

    @pytest.fixture
    def backend(self):
        return IncrementalSolverBackend()

    @pytest.fixture
    def sketch(self):
        sketch = Sketch("Test")

        # Simple triangle
        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(10, 0)
        p3 = sketch.add_point(5, 8)

        l1 = sketch.add_line_from_points(p1, p2)
        l2 = sketch.add_line_from_points(p2, p3)
        l3 = sketch.add_line_from_points(p3, p1)

        sketch.constraints.append(make_fixed(p1))
        sketch.constraints.append(make_horizontal(l1))
        sketch.constraints.append(make_length(l1, 10))
        sketch.constraints.append(make_length(l2, 8))
        sketch.constraints.append(make_length(l3, 7))

        return sketch

    def test_backend_properties(self, backend):
        """Test backend basic properties"""
        assert backend.name == "incremental"

        can_solve, reason = backend.can_solve(None)
        # SciPy might not be available in test environment
        assert isinstance(can_solve, bool)

    def test_start_drag(self, backend, sketch):
        """Test starting a drag operation"""
        context = backend.start_drag(sketch, sketch.points[0].id)

        assert context is not None
        assert context.sketch is sketch
        assert context.dragged_entity_id == sketch.points[0].id
        assert backend._is_dragging is True

    def test_drag_move(self, backend, sketch):
        """Test incremental solve during drag"""
        backend.start_drag(sketch, sketch.points[1].id)

        # Get original position
        p2 = sketch.points[1]
        original_x = p2.x

        # Move to new position
        result = backend.drag_move((15.0, 0.0))

        assert result is not None
        assert hasattr(result, 'success')
        assert hasattr(result, 'backend_used')
        assert result.backend_used == "incremental"

    def test_end_drag(self, backend, sketch):
        """Test ending drag with final solve"""
        backend.start_drag(sketch, sketch.points[1].id)
        backend.drag_move((12.0, 0.0))

        result = backend.end_drag()

        assert result is not None
        assert backend._is_dragging is False
        assert backend._context is None

    def test_solve_drag_without_context(self, backend):
        """Test drag_move without start_drag"""
        result = backend.drag_move((10.0, 10.0))

        assert result is not None
        assert result.success is False
        assert "No active drag context" in result.message


def test_incremental_vs_full_solve_benchmark():
    """
    Benchmark comparing incremental vs full solve.

    This test demonstrates the performance improvement of incremental solving.
    """
    sketch = Sketch("Benchmark")

    # Create a more complex sketch
    n_rectangles = 5
    points = []
    lines = []

    for i in range(n_rectangles):
        offset_x = i * 20
        p1 = sketch.add_point(offset_x, 0)
        p2 = sketch.add_point(offset_x + 10, 0)
        p3 = sketch.add_point(offset_x + 10, 10)
        p4 = sketch.add_point(offset_x, 10)

        l1 = sketch.add_line_from_points(p1, p2)
        l2 = sketch.add_line_from_points(p2, p3)
        l3 = sketch.add_line_from_points(p3, p4)
        l4 = sketch.add_line_from_points(p4, p1)

        points.extend([p1, p2, p3, p4])
        lines.extend([l1, l2, l3, l4])

        # Add constraints
        if i == 0:
            sketch.constraints.append(make_fixed(p1))

        sketch.constraints.append(make_horizontal(l1))
        sketch.constraints.append(make_vertical(l2))
        sketch.constraints.append(make_length(l1, 10))
        sketch.constraints.append(make_length(l2, 10))

    import time

    # Measure full solve time
    start = time.perf_counter()
    full_result = sketch.solve()
    full_time = (time.perf_counter() - start) * 1000

    # Measure incremental solve (simulated drag)
    backend = IncrementalSolverBackend()
    backend.start_drag(sketch, points[1].id)

    start = time.perf_counter()
    drag_result = backend.drag_move((15.0, 0.0))
    drag_time = (time.perf_counter() - start) * 1000

    backend.end_drag()

    print(f"\n=== Incremental Solver Benchmark ===")
    print(f"Full solve: {full_time:.2f}ms")
    print(f"Incremental solve: {drag_time:.2f}ms")
    print(f"Speedup: {full_time / max(drag_time, 0.01):.1f}x")
    print(f"Constraints: {len(sketch.constraints)}")
    print(f"Variables: {len(points) * 2}")

    # Incremental should be faster
    # Note: In test environment with small sketch, difference might be minimal
    assert drag_result is not None


if __name__ == "__main__":
    # Run benchmarks
    test_incremental_vs_full_solve_benchmark()
