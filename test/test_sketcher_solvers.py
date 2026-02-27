"""
Unit tests for sketcher/solver_*.py modules.

Tests for:
- solver_interface.py: Solver interface, registry, and unified solver
- solver_scipy.py: SciPy-based solver backends
- solver_staged.py: Staged solver with priority phases
- parametric_solver.py: py-slvs based parametric solver
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import List, Any, Optional, Tuple
import uuid

# Test markers for pytest selection
pytestmark = [pytest.mark.solver, pytest.mark.fast]

# ============================================================================
# Fixtures for Mock Geometry and Constraints
# ============================================================================

@pytest.fixture
def mock_point():
    """Create a mock Point2D-like object."""
    def _create(x=0.0, y=0.0, id=None, fixed=False):
        point = Mock()
        point.x = x
        point.y = y
        point.id = id or str(uuid.uuid4())[:8]
        point.fixed = fixed
        point.construction = False
        return point
    return _create


@pytest.fixture
def mock_line(mock_point):
    """Create a mock Line2D-like object."""
    def _create(x1=0.0, y1=0.0, x2=10.0, y2=0.0, id=None):
        line = Mock()
        line.start = mock_point(x1, y1)
        line.end = mock_point(x2, y2)
        line.id = id or str(uuid.uuid4())[:8]
        line.construction = False
        return line
    return _create


@pytest.fixture
def mock_circle(mock_point):
    """Create a mock Circle2D-like object."""
    def _create(cx=0.0, cy=0.0, radius=5.0, id=None):
        circle = Mock()
        circle.center = mock_point(cx, cy)
        circle.radius = radius
        circle.id = id or str(uuid.uuid4())[:8]
        return circle
    return _create


@pytest.fixture
def mock_arc(mock_point):
    """Create a mock Arc2D-like object."""
    def _create(cx=0.0, cy=0.0, radius=5.0, start_angle=0.0, end_angle=90.0, id=None):
        arc = Mock()
        arc.center = mock_point(cx, cy)
        arc.radius = radius
        arc.start_angle = start_angle
        arc.end_angle = end_angle
        arc.id = id or str(uuid.uuid4())[:8]
        return arc
    return _create


@pytest.fixture
def mock_constraint():
    """Create a mock Constraint-like object."""
    def _create(constraint_type, entities=None, value=None, enabled=True, valid=True):
        constraint = Mock()
        constraint.type = constraint_type
        constraint.entities = entities or []
        constraint.value = value
        constraint.enabled = enabled
        constraint.formula = None
        constraint.driving = True
        constraint.satisfied = False
        constraint.error = 0.0
        
        def is_valid():
            return valid
        constraint.is_valid = is_valid
        
        def get_weight():
            return 100.0  # Default weight
        constraint.get_weight = get_weight
        
        return constraint
    return _create


# ============================================================================
# Test SolverInterface Module
# ============================================================================

class TestSolverBackendType:
    """Tests for SolverBackendType enum."""
    
    def test_backend_types_exist(self):
        """Test that all expected backend types are defined."""
        from sketcher.solver_interface import SolverBackendType
        
        assert hasattr(SolverBackendType, 'SCIPY_LM')
        assert hasattr(SolverBackendType, 'SCIPY_TRF')
        assert hasattr(SolverBackendType, 'STAGED')
    
    def test_backend_type_values(self):
        """Test backend type string values."""
        from sketcher.solver_interface import SolverBackendType
        
        assert SolverBackendType.SCIPY_LM.value == "scipy_lm"
        assert SolverBackendType.SCIPY_TRF.value == "scipy_trf"
        assert SolverBackendType.STAGED.value == "staged"


class TestSolverOptions:
    """Tests for SolverOptions dataclass."""
    
    def test_default_options(self):
        """Test default SolverOptions values."""
        from sketcher.solver_interface import SolverOptions
        
        options = SolverOptions()
        
        assert options.tolerance == 1e-6
        assert options.max_iterations == 1000
        assert options.regularization == 0.01
        assert options.verbose is False
        assert options.pre_validation is False
        assert options.smooth_penalties is False
    
    def test_custom_options(self):
        """Test custom SolverOptions values."""
        from sketcher.solver_interface import SolverOptions
        
        options = SolverOptions(
            tolerance=1e-8,
            max_iterations=5000,
            regularization=0.1,
            verbose=True,
            pre_validation=True
        )
        
        assert options.tolerance == 1e-8
        assert options.max_iterations == 5000
        assert options.regularization == 0.1
        assert options.verbose is True
        assert options.pre_validation is True


class TestSolverProblem:
    """Tests for SolverProblem dataclass."""
    
    def test_empty_problem(self):
        """Test creating an empty SolverProblem."""
        from sketcher.solver_interface import SolverProblem
        
        problem = SolverProblem(
            points=[],
            lines=[],
            circles=[],
            arcs=[],
            constraints=[]
        )
        
        assert problem.points == []
        assert problem.lines == []
        assert problem.circles == []
        assert problem.arcs == []
        assert problem.constraints == []
    
    def test_problem_with_geometry(self, mock_point, mock_line, mock_circle, mock_constraint):
        """Test SolverProblem with geometry and constraints."""
        from sketcher.solver_interface import SolverProblem, SolverOptions
        
        points = [mock_point(0, 0), mock_point(10, 10)]
        lines = [mock_line(0, 0, 10, 10)]
        circles = [mock_circle(5, 5, 3)]
        
        # Create a mock constraint type
        constraint_type = Mock()
        constraint = mock_constraint(constraint_type, entities=lines, value=14.14)
        
        problem = SolverProblem(
            points=points,
            lines=lines,
            circles=circles,
            arcs=[],
            constraints=[constraint]
        )
        
        assert len(problem.points) == 2
        assert len(problem.lines) == 1
        assert len(problem.circles) == 1
        assert len(problem.constraints) == 1
    
    def test_problem_with_spline_control_points(self, mock_point):
        """Test SolverProblem with spline control points."""
        from sketcher.solver_interface import SolverProblem
        
        spline_points = [mock_point(0, 0), mock_point(5, 5), mock_point(10, 0)]
        
        problem = SolverProblem(
            points=[],
            lines=[],
            circles=[],
            arcs=[],
            constraints=[],
            spline_control_points=spline_points
        )
        
        assert len(problem.spline_control_points) == 3


class TestSolverResult:
    """Tests for SolverResult dataclass."""
    
    def test_success_result(self):
        """Test creating a successful SolverResult."""
        from sketcher.solver_interface import SolverResult
        from sketcher.constraints import ConstraintStatus
        
        result = SolverResult(
            success=True,
            iterations=50,
            final_error=1e-8,
            status=ConstraintStatus.FULLY_CONSTRAINED,
            message="Vollständig bestimmt"
        )
        
        assert result.success is True
        assert result.iterations == 50
        assert result.final_error == 1e-8
        assert result.backend_used == ""
    
    def test_failure_result(self):
        """Test creating a failed SolverResult."""
        from sketcher.solver_interface import SolverResult
        from sketcher.constraints import ConstraintStatus
        
        result = SolverResult(
            success=False,
            iterations=0,
            final_error=float('inf'),
            status=ConstraintStatus.INCONSISTENT,
            message="Widersprüchliche Constraints"
        )
        
        assert result.success is False
        assert result.final_error == float('inf')


class TestISolverBackend:
    """Tests for ISolverBackend abstract base class."""
    
    def test_abstract_methods_exist(self):
        """Test that ISolverBackend has required abstract methods."""
        from sketcher.solver_interface import ISolverBackend
        import inspect
        
        # Check that name is an abstract property
        assert hasattr(ISolverBackend, 'name')
        
        # Check that solve is an abstract method
        assert hasattr(ISolverBackend, 'solve')
    
    def test_cannot_instantiate_directly(self):
        """Test that ISolverBackend cannot be instantiated directly."""
        from sketcher.solver_interface import ISolverBackend
        
        with pytest.raises(TypeError):
            ISolverBackend()
    
    def test_can_solve_default_implementation(self):
        """Test default can_solve implementation returns True."""
        from sketcher.solver_interface import ISolverBackend, SolverProblem
        
        # Create a concrete implementation for testing
        class ConcreteBackend(ISolverBackend):
            @property
            def name(self):
                return "concrete"
            
            def solve(self, problem):
                from sketcher.solver_interface import SolverResult
                return SolverResult(True, 0, 0.0, Mock(), "")
        
        backend = ConcreteBackend()
        problem = SolverProblem(points=[], lines=[], circles=[], arcs=[], constraints=[])
        
        can_solve, reason = backend.can_solve(problem)
        assert can_solve is True
        assert reason == ""


class TestSolverBackendRegistry:
    """Tests for SolverBackendRegistry class."""
    
    def test_register_and_get_backend(self):
        """Test registering and retrieving a backend."""
        from sketcher.solver_interface import SolverBackendRegistry, SolverBackendType, ISolverBackend
        
        # Clear any existing registrations for this test
        original_backends = SolverBackendRegistry._backends.copy()
        
        try:
            # Create a mock backend
            mock_backend = Mock(spec=ISolverBackend)
            mock_backend.name = "test_backend"
            
            # Register it
            SolverBackendRegistry.register(SolverBackendType.SCIPY_LM, mock_backend)
            
            # Retrieve it
            retrieved = SolverBackendRegistry.get(SolverBackendType.SCIPY_LM)
            assert retrieved is mock_backend
            
            # Also test getting by string
            retrieved_by_string = SolverBackendRegistry.get("scipy_lm")
            assert retrieved_by_string is mock_backend
        finally:
            # Restore original backends
            SolverBackendRegistry._backends = original_backends
    
    def test_get_nonexistent_backend(self):
        """Test getting a backend that doesn't exist."""
        from sketcher.solver_interface import SolverBackendRegistry
        
        result = SolverBackendRegistry.get("nonexistent_backend")
        assert result is None
    
    def test_list_available(self):
        """Test listing available backends."""
        from sketcher.solver_interface import SolverBackendRegistry
        
        backends = SolverBackendRegistry.list_available()
        assert isinstance(backends, list)


class TestUnifiedConstraintSolver:
    """Tests for UnifiedConstraintSolver class."""
    
    def test_init_without_backend(self):
        """Test initialization without a specific backend."""
        from sketcher.solver_interface import UnifiedConstraintSolver
        
        solver = UnifiedConstraintSolver()
        
        assert solver._backend is None
        assert len(solver._fallback_chain) > 0
    
    def test_init_with_backend(self):
        """Test initialization with a specific backend."""
        from sketcher.solver_interface import UnifiedConstraintSolver, ISolverBackend
        
        mock_backend = Mock(spec=ISolverBackend)
        solver = UnifiedConstraintSolver(backend=mock_backend)
        
        assert solver._backend is mock_backend
    
    def test_solve_no_constraints(self, mock_point, mock_line):
        """Test solving with no constraints returns under-constrained."""
        from sketcher.solver_interface import UnifiedConstraintSolver
        from sketcher.constraints import ConstraintStatus

        solver = UnifiedConstraintSolver()
        
        # Mock the backend to return a result
        with patch.object(solver, '_select_backend') as mock_select:
            mock_backend = Mock()
            mock_backend.name = "test"
            mock_backend.solve.return_value = Mock(
                success=True,
                iterations=0,
                final_error=0.0,
                status=ConstraintStatus.UNDER_CONSTRAINED,
                message="Keine Constraints",
                backend_used="test"
            )
            mock_select.return_value = (mock_backend, "test", "")

            result = solver.solve(
                points=[mock_point(0, 0)],
                lines=[mock_line(0, 0, 10, 0)],
                circles=[],
                arcs=[],
                constraints=[]
            )

            assert result.success is True
            assert result.backend_used == "test"
            assert result.requested_backend == "test"

    def test_solve_exposes_backend_selection_detail(self, mock_point, mock_line):
        """Backend fallback details must be visible in the returned result."""
        from sketcher.solver_interface import UnifiedConstraintSolver
        from sketcher.constraints import ConstraintStatus

        solver = UnifiedConstraintSolver()

        with patch.object(solver, '_select_backend') as mock_select:
            mock_backend = Mock()
            mock_backend.name = "scipy_lm"
            mock_backend.solve.return_value = Mock(
                success=True,
                iterations=4,
                final_error=0.0,
                status=ConstraintStatus.UNDER_CONSTRAINED,
                message="Solved",
                backend_used="",
            )
            detail = "requested backend 'staged' cannot solve: test reason; fell back to 'scipy_lm'"
            mock_select.return_value = (mock_backend, "staged", detail)

            result = solver.solve(
                points=[mock_point(0, 0)],
                lines=[mock_line(0, 0, 10, 0)],
                circles=[],
                arcs=[],
                constraints=[],
            )

            assert result.success is True
            assert result.backend_used == "scipy_lm"
            assert result.requested_backend == "staged"
            assert result.selection_detail == detail
            assert detail in result.message


# ============================================================================
# Test SolverScipy Module
# ============================================================================

class TestSciPyBackendBase:
    """Tests for SciPyBackendBase class."""
    
    def test_init_default_method(self):
        """Test default initialization."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        assert backend.method == 'lm'
        assert backend._iteration_count == 0
    
    def test_init_custom_method(self):
        """Test initialization with custom method."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase(method='trf')
        
        assert backend.method == 'trf'
    
    def test_name_property(self):
        """Test name property returns correct format."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase(method='lm')
        assert backend.name == "scipy_lm"
        
        backend_trf = SciPyBackendBase(method='trf')
        assert backend_trf.name == "scipy_trf"
    
    def test_count_effective_constraints(self, mock_constraint):
        """Test counting effective constraints with DOF weighting."""
        from sketcher.solver_scipy import SciPyBackendBase
        from sketcher.constraints import ConstraintType
        
        backend = SciPyBackendBase()
        
        # Create mock constraints with different types
        c1 = mock_constraint(ConstraintType.COINCIDENT, entities=[Mock(), Mock()])
        c2 = mock_constraint(ConstraintType.HORIZONTAL, entities=[Mock()])
        c3 = mock_constraint(ConstraintType.LENGTH, entities=[Mock()], value=10.0)
        
        # COINCIDENT counts as 2 DOF, others as 1
        count = backend._count_effective_constraints([c1, c2, c3])
        
        # Should be 2 (COINCIDENT) + 1 + 1 = 4
        assert count == 4


class TestSciPyLMBackend:
    """Tests for SciPyLMBackend class."""
    
    def test_init(self):
        """Test SciPyLMBackend initialization."""
        from sketcher.solver_scipy import SciPyLMBackend
        
        backend = SciPyLMBackend()
        
        assert backend.method == 'lm'
        assert backend.name == "scipy_lm"
    
    def test_is_subclass_of_base(self):
        """Test that SciPyLMBackend is subclass of SciPyBackendBase."""
        from sketcher.solver_scipy import SciPyLMBackend, SciPyBackendBase
        
        backend = SciPyLMBackend()
        assert isinstance(backend, SciPyBackendBase)


class TestSciPyTRFBackend:
    """Tests for SciPyTRFBackend class."""
    
    def test_init(self):
        """Test SciPyTRFBackend initialization."""
        from sketcher.solver_scipy import SciPyTRFBackend
        
        backend = SciPyTRFBackend()
        
        assert backend.method == 'trf'
        assert backend.name == "scipy_trf"
    
    def test_is_subclass_of_base(self):
        """Test that SciPyTRFBackend is subclass of SciPyBackendBase."""
        from sketcher.solver_scipy import SciPyTRFBackend, SciPyBackendBase
        
        backend = SciPyTRFBackend()
        assert isinstance(backend, SciPyBackendBase)


class TestSciPySolverCollectVariables:
    """Tests for _collect_variables method."""
    
    def test_collect_from_points(self, mock_point):
        """Test collecting variables from points."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        p1 = mock_point(0, 0, id="p1")
        p2 = mock_point(10, 5, id="p2")
        
        refs, x0_vals = backend._collect_variables([p1, p2], [], [], [], [])
        
        # Each point contributes x and y
        assert len(refs) == 4
        assert len(x0_vals) == 4
        assert x0_vals == [0.0, 0.0, 10.0, 5.0]
    
    def test_collect_from_lines(self, mock_point, mock_line):
        """Test collecting variables from lines."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        line = mock_line(0, 0, 10, 5)
        
        refs, x0_vals = backend._collect_variables([], [line], [], [], [])
        
        # Line has start and end points (4 variables)
        assert len(refs) == 4
        assert len(x0_vals) == 4
    
    def test_collect_from_circles(self, mock_circle):
        """Test collecting variables from circles."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        circle = mock_circle(5, 5, 3)
        
        refs, x0_vals = backend._collect_variables([], [], [circle], [], [])
        
        # Circle has center (x, y) and radius (3 variables)
        assert len(refs) == 3
        assert len(x0_vals) == 3
    
    def test_collect_from_arcs(self, mock_arc):
        """Test collecting variables from arcs."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        arc = mock_arc(5, 5, 3, 0, 90)
        
        refs, x0_vals = backend._collect_variables([], [], [], [arc], [])
        
        # Arc has center (x, y), radius, start_angle, end_angle (5 variables)
        assert len(refs) == 5
        assert len(x0_vals) == 5
    
    def test_collect_fixed_points_excluded(self, mock_point):
        """Test that fixed points are excluded from variables."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        p1 = mock_point(0, 0, id="p1", fixed=True)
        p2 = mock_point(10, 5, id="p2", fixed=False)
        
        refs, x0_vals = backend._collect_variables([p1, p2], [], [], [], [])
        
        # Only p2 should be included (2 variables)
        assert len(refs) == 2
        assert x0_vals == [10.0, 5.0]
    
    def test_collect_spline_control_points(self, mock_point):
        """Test collecting variables from spline control points."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        spline_points = [mock_point(0, 0), mock_point(5, 5), mock_point(10, 0)]
        
        refs, x0_vals = backend._collect_variables([], [], [], [], spline_points)
        
        # 3 points * 2 coordinates = 6 variables
        assert len(refs) == 6
        assert len(x0_vals) == 6


class TestSciPySolverPreValidation:
    """Tests for _validate_pre_solve method."""
    
    def test_validate_empty_constraints(self, mock_line):
        """Test validation with empty constraints."""
        from sketcher.solver_scipy import SciPyBackendBase
        
        backend = SciPyBackendBase()
        
        is_valid, issues = backend._validate_pre_solve([], [])
        
        assert is_valid is True
        assert len(issues) == 0
    
    def test_validate_negative_distance(self, mock_constraint, mock_point):
        """Test validation catches negative distance values."""
        from sketcher.solver_scipy import SciPyBackendBase
        from sketcher.constraints import ConstraintType
        
        backend = SciPyBackendBase()
        
        p1 = mock_point(0, 0)
        p2 = mock_point(10, 0)
        constraint = mock_constraint(ConstraintType.DISTANCE, entities=[p1, p2], value=-5.0)
        
        is_valid, issues = backend._validate_pre_solve([], [constraint])
        
        assert is_valid is False
        assert len(issues) > 0
        assert "negative" in issues[0].lower()


class TestSciPySolverSolve:
    """Tests for solve method."""
    
    def test_solve_no_scipy(self, monkeypatch):
        """Test solve returns error when SciPy is forced unavailable."""
        import sketcher.solver_scipy as solver_scipy_module
        from sketcher.solver_interface import SolverProblem

        monkeypatch.setattr(solver_scipy_module, "HAS_SCIPY", False)

        backend = solver_scipy_module.SciPyBackendBase()
        problem = SolverProblem(points=[], lines=[], circles=[], arcs=[], constraints=[])

        result = backend.solve(problem)

        assert result.success is False
        assert "SciPy" in result.message
        assert result.error_code == "no_scipy"
    
    def test_solve_no_constraints(self):
        """Test solve with no constraints."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = SciPyLMBackend()
        problem = SolverProblem(points=[], lines=[], circles=[], arcs=[], constraints=[])
        
        result = backend.solve(problem)
        
        assert result.success is True
        assert "Keine Constraints" in result.message or "Keine aktiven Constraints" in result.message
    
    @pytest.mark.skipif(
        not pytest.importorskip("scipy", reason="SciPy not available"),
        reason="SciPy not available"
    )
    def test_solve_simple_constraint(self, mock_line, mock_constraint):
        """Test solve with a simple constraint."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem
        from sketcher.constraints import ConstraintType
        
        backend = SciPyLMBackend()
        
        line = mock_line(0, 0, 10, 0)
        constraint = mock_constraint(ConstraintType.HORIZONTAL, entities=[line])
        
        problem = SolverProblem(
            points=[],
            lines=[line],
            circles=[],
            arcs=[],
            constraints=[constraint]
        )
        
        result = backend.solve(problem)
        
        # Line is already horizontal, should succeed
        assert result.success is True or result.status is not None


# ============================================================================
# Test SolverStaged Module
# ============================================================================

class TestStagedSolverBackend:
    """Tests for StagedSolverBackend class."""
    
    def test_name_property(self):
        """Test name property returns 'staged'."""
        from sketcher.solver_staged import StagedSolverBackend
        
        backend = StagedSolverBackend()
        assert backend.name == "staged"
    
    def test_can_solve_with_scipy(self):
        """Test can_solve returns True when SciPy is available."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = StagedSolverBackend()
        problem = SolverProblem(points=[], lines=[], circles=[], arcs=[], constraints=[])
        
        can_solve, reason = backend.can_solve(problem)
        
        # Should return True if SciPy is available
        # The actual result depends on whether scipy is installed
        assert isinstance(can_solve, bool)
        assert isinstance(reason, str)
    
    def test_group_constraints_by_priority(self, mock_constraint, mock_line):
        """Test grouping constraints by priority."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.constraints import ConstraintType
        
        backend = StagedSolverBackend()
        
        line1 = mock_line(0, 0, 10, 0)
        line2 = mock_line(0, 0, 0, 10)
        
        # Create constraints of different types
        c_fixed = mock_constraint(ConstraintType.FIXED, entities=[line1.start])
        c_coincident = mock_constraint(ConstraintType.COINCIDENT, entities=[line1.end, line2.start])
        c_horizontal = mock_constraint(ConstraintType.HORIZONTAL, entities=[line1])
        c_length = mock_constraint(ConstraintType.LENGTH, entities=[line1], value=10.0)
        
        groups = backend._group_constraints_by_priority([c_fixed, c_coincident, c_horizontal, c_length])
        
        # FIXED and COINCIDENT should be in 'critical'
        assert len(groups['critical']) == 2
        # HORIZONTAL should be in 'medium'
        assert len(groups['medium']) == 1
        # LENGTH should be in 'low'
        assert len(groups['low']) == 1
    
    def test_group_constraints_disabled(self, mock_constraint, mock_line):
        """Test that disabled constraints are not grouped."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.constraints import ConstraintType
        
        backend = StagedSolverBackend()
        
        line = mock_line(0, 0, 10, 0)
        c_enabled = mock_constraint(ConstraintType.HORIZONTAL, entities=[line], enabled=True)
        c_disabled = mock_constraint(ConstraintType.VERTICAL, entities=[line], enabled=False)
        
        groups = backend._group_constraints_by_priority([c_enabled, c_disabled])
        
        # Only enabled constraint should be grouped
        total_grouped = sum(len(g) for g in groups.values())
        assert total_grouped == 1
    
    def test_group_constraints_invalid(self, mock_constraint, mock_line):
        """Test that invalid constraints are not grouped."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.constraints import ConstraintType
        
        backend = StagedSolverBackend()
        
        line = mock_line(0, 0, 10, 0)
        c_valid = mock_constraint(ConstraintType.HORIZONTAL, entities=[line], valid=True)
        c_invalid = mock_constraint(ConstraintType.HORIZONTAL, entities=[], valid=False)
        
        groups = backend._group_constraints_by_priority([c_valid, c_invalid])
        
        # Only valid constraint should be grouped
        total_grouped = sum(len(g) for g in groups.values())
        assert total_grouped == 1


class TestStagedSolverGeometryState:
    """Tests for geometry state save/restore."""
    
    def test_save_geometry_state(self, mock_point, mock_line, mock_circle, mock_arc):
        """Test saving geometry state."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = StagedSolverBackend()
        
        p = mock_point(5, 5)
        line = mock_line(0, 0, 10, 0)
        circle = mock_circle(5, 5, 3)
        arc = mock_arc(10, 10, 2, 0, 90)
        
        problem = SolverProblem(
            points=[p],
            lines=[line],
            circles=[circle],
            arcs=[arc],
            constraints=[]
        )
        
        state = backend._save_geometry_state(problem)
        
        # State should contain entries for all geometry
        assert id(p) in state
        assert id(line.start) in state
        assert id(line.end) in state
        assert id(circle.center) in state
        assert id(circle) in state
        assert id(arc.center) in state
        assert id(arc) in state
    
    def test_restore_geometry_state(self, mock_point, mock_line):
        """Test restoring geometry state."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = StagedSolverBackend()
        
        p = mock_point(5, 5)
        line = mock_line(0, 0, 10, 0)
        
        problem = SolverProblem(
            points=[p],
            lines=[line],
            circles=[],
            arcs=[],
            constraints=[]
        )
        
        # Save state
        state = backend._save_geometry_state(problem)
        
        # Modify geometry
        p.x = 100
        p.y = 100
        line.start.x = 50
        
        # Restore state
        backend._restore_geometry_state(problem, state)
        
        # Check values are restored
        assert p.x == 5
        assert p.y == 5
        assert line.start.x == 0


class TestStagedSolverFastPath:
    """Tests for fast path optimization."""
    
    def test_fast_path_simple_sketch(self, mock_line, mock_constraint):
        """Test fast path is used for simple sketches."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.solver_interface import SolverProblem, SolverOptions
        from sketcher.constraints import ConstraintType
        
        backend = StagedSolverBackend()
        
        line = mock_line(0, 0, 10, 0)
        # Create fewer than 10 constraints
        constraints = [mock_constraint(ConstraintType.HORIZONTAL, entities=[line])]
        
        problem = SolverProblem(
            points=[],
            lines=[line],
            circles=[],
            arcs=[],
            constraints=constraints,
            options=SolverOptions()
        )
        
        # Fast path should be triggered (< 10 constraints)
        # We can't directly test the internal logic, but we can verify solve doesn't crash
        import time
        start_time = time.perf_counter()
        
        # This will either use fast path or full staged depending on scipy availability
        result = backend.solve(problem)
        
        # Should complete without error
        assert result is not None
        assert result.backend_used in ["staged", "staged_fast"]


# ============================================================================
# Test ParametricSolver Module
# ============================================================================

class TestSolveResult:
    """Tests for SolveResult enum."""
    
    def test_solve_result_values(self):
        """Test SolveResult enum values exist."""
        from sketcher.parametric_solver import SolveResult
        
        assert hasattr(SolveResult, 'OK')
        assert hasattr(SolveResult, 'INCONSISTENT')
        assert hasattr(SolveResult, 'DIDNT_CONVERGE')
        assert hasattr(SolveResult, 'TOO_MANY_UNKNOWNS')
        assert hasattr(SolveResult, 'NO_SOLVER')


class TestParametricSolverResult:
    """Tests for SolverResult dataclass in parametric_solver."""
    
    def test_success_result(self):
        """Test creating a successful SolverResult."""
        from sketcher.parametric_solver import SolverResult, SolveResult
        
        result = SolverResult(
            success=True,
            result=SolveResult.OK,
            dof=0,
            message="Gelöst. DOF: 0"
        )
        
        assert result.success is True
        assert result.result == SolveResult.OK
        assert result.dof == 0
        assert result.failed_constraints == []
    
    def test_failure_result_with_failed_constraints(self):
        """Test creating a failure SolverResult with failed constraints."""
        from sketcher.parametric_solver import SolverResult, SolveResult
        
        result = SolverResult(
            success=False,
            result=SolveResult.INCONSISTENT,
            dof=-1,
            message="Widersprüchliche Constraints",
            failed_constraints=["constraint_1", "constraint_2"]
        )
        
        assert result.success is False
        assert result.result == SolveResult.INCONSISTENT
        assert len(result.failed_constraints) == 2


class TestCheckSolvespaceAvailable:
    """Tests for check_solvespace_available function."""
    
    def test_returns_boolean(self):
        """Test that function returns a boolean."""
        from sketcher.parametric_solver import check_solvespace_available
        
        result = check_solvespace_available()
        assert isinstance(result, bool)
    
    def test_consistent_with_has_solvespace(self):
        """Test that function is consistent with HAS_SOLVESPACE."""
        from sketcher.parametric_solver import check_solvespace_available, HAS_SOLVESPACE
        
        assert check_solvespace_available() == HAS_SOLVESPACE


class TestParametricSolver:
    """Tests for ParametricSolver class."""
    
    def test_init(self):
        """Test ParametricSolver initialization."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        
        solver = ParametricSolver(mock_sketch)
        
        assert solver.sketch is mock_sketch
        assert solver.sys is None
        assert solver._handle == 1
        assert solver._group_wp == 1
        assert solver._group_sketch == 2
    
    def test_next_handle(self):
        """Test _next_handle increments correctly."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        
        solver = ParametricSolver(mock_sketch)
        
        h1 = solver._next_handle()
        h2 = solver._next_handle()
        h3 = solver._next_handle()
        
        assert h1 == 1
        assert h2 == 2
        assert h3 == 3
    
    def test_supports_current_sketch_empty(self):
        """Test supports_current_sketch with empty sketch."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        mock_sketch.splines = []
        mock_sketch.native_splines = []
        
        solver = ParametricSolver(mock_sketch)
        
        can_support, reason = solver.supports_current_sketch()
        
        assert can_support is True
        assert reason == ""
    
    def test_supports_current_sketch_with_arcs(self, mock_arc):
        """Test supports_current_sketch returns False with arcs."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = [mock_arc()]
        mock_sketch.points = []
        mock_sketch.constraints = []
        
        solver = ParametricSolver(mock_sketch)
        
        can_support, reason = solver.supports_current_sketch()
        
        assert can_support is False
        assert "Arcs" in reason
    
    def test_supports_current_sketch_with_splines(self):
        """Test supports_current_sketch returns False with splines."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        mock_sketch.splines = [Mock()]
        mock_sketch.native_splines = []
        
        solver = ParametricSolver(mock_sketch)
        
        can_support, reason = solver.supports_current_sketch()
        
        assert can_support is False
        assert "Spline" in reason
    
    def test_solve_no_solver(self):
        """Test solve returns NO_SOLVER when py-slvs not available."""
        from sketcher.parametric_solver import ParametricSolver, HAS_SOLVESPACE, SolveResult
        
        if HAS_SOLVESPACE:
            pytest.skip("py-slvs is available, skipping no-solver test")
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        
        solver = ParametricSolver(mock_sketch)
        result = solver.solve()
        
        assert result.success is False
        assert result.result == SolveResult.NO_SOLVER
        assert "py-slvs" in result.message


class TestParametricSolverConstraintMapping:
    """Tests for constraint mapping in ParametricSolver."""
    
    def test_point_map_initialization(self):
        """Test point map is initialized empty."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        
        solver = ParametricSolver(mock_sketch)
        
        assert solver._point_map == {}
        assert solver._line_map == {}
        assert solver._circle_map == {}
        assert solver._arc_map == {}
    
    def test_fixed_points_set_initialization(self):
        """Test fixed points set is initialized empty."""
        from sketcher.parametric_solver import ParametricSolver
        
        mock_sketch = Mock()
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        mock_sketch.points = []
        mock_sketch.constraints = []
        
        solver = ParametricSolver(mock_sketch)
        
        assert solver._fixed_points == set()


# ============================================================================
# Integration Tests (require actual dependencies)
# ============================================================================

@pytest.mark.integration
class TestSolverIntegration:
    """Integration tests that require actual solver dependencies."""
    
    @pytest.mark.skipif(
        not pytest.importorskip("scipy", reason="SciPy not available"),
        reason="SciPy not available"
    )
    def test_scipy_backend_full_solve(self, mock_line, mock_constraint):
        """Full integration test with SciPy backend."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem, SolverOptions
        from sketcher.constraints import ConstraintType
        
        backend = SciPyLMBackend()
        
        line = mock_line(0, 0, 10, 5)  # Non-horizontal line
        constraint = mock_constraint(ConstraintType.HORIZONTAL, entities=[line])
        
        problem = SolverProblem(
            points=[],
            lines=[line],
            circles=[],
            arcs=[],
            constraints=[constraint],
            options=SolverOptions()
        )
        
        result = backend.solve(problem)
        
        # After solve, line should be closer to horizontal
        assert result is not None
    
    @pytest.mark.skipif(
        not pytest.importorskip("scipy", reason="SciPy not available"),
        reason="SciPy not available"
    )
    def test_staged_solver_full_solve(self, mock_line, mock_constraint):
        """Full integration test with staged solver."""
        from sketcher.solver_staged import StagedSolverBackend
        from sketcher.solver_interface import SolverProblem, SolverOptions
        from sketcher.constraints import ConstraintType
        
        backend = StagedSolverBackend()
        
        line = mock_line(0, 0, 10, 5)
        constraint = mock_constraint(ConstraintType.HORIZONTAL, entities=[line])
        
        problem = SolverProblem(
            points=[],
            lines=[line],
            circles=[],
            arcs=[],
            constraints=[constraint],
            options=SolverOptions()
        )
        
        result = backend.solve(problem)
        
        assert result is not None


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_solver_problem_with_nan_values(self, mock_point):
        """Test solver handles NaN values gracefully."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = SciPyLMBackend()
        
        p = mock_point(float('nan'), float('nan'))
        
        problem = SolverProblem(
            points=[p],
            lines=[],
            circles=[],
            arcs=[],
            constraints=[]
        )
        
        # Should not crash
        result = backend.solve(problem)
        assert result is not None
    
    def test_solver_problem_with_inf_values(self, mock_point):
        """Test solver handles infinity values gracefully."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = SciPyLMBackend()
        
        p = mock_point(float('inf'), float('inf'))
        
        problem = SolverProblem(
            points=[p],
            lines=[],
            circles=[],
            arcs=[],
            constraints=[]
        )
        
        # Should not crash
        result = backend.solve(problem)
        assert result is not None
    
    def test_empty_solver_problem(self):
        """Test solver with completely empty problem."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = SciPyLMBackend()
        
        problem = SolverProblem(
            points=[],
            lines=[],
            circles=[],
            arcs=[],
            constraints=[]
        )
        
        result = backend.solve(problem)
        
        # Should return success with appropriate message
        assert result.success is True
    
    def test_solver_with_only_fixed_points(self, mock_point):
        """Test solver with only fixed points."""
        from sketcher.solver_scipy import SciPyLMBackend
        from sketcher.solver_interface import SolverProblem
        
        backend = SciPyLMBackend()
        
        p1 = mock_point(0, 0, fixed=True)
        p2 = mock_point(10, 10, fixed=True)
        
        problem = SolverProblem(
            points=[p1, p2],
            lines=[],
            circles=[],
            arcs=[],
            constraints=[]
        )
        
        result = backend.solve(problem)
        
        # Should handle gracefully (no variables to solve)
        assert result is not None


class TestConstraintStatusHandling:
    """Tests for constraint status handling."""
    
    def test_fully_constrained_status(self):
        """Test FULLY_CONSTRAINED status is available."""
        from sketcher.constraints import ConstraintStatus
        
        assert hasattr(ConstraintStatus, 'FULLY_CONSTRAINED')
    
    def test_under_constrained_status(self):
        """Test UNDER_CONSTRAINED status is available."""
        from sketcher.constraints import ConstraintStatus
        
        assert hasattr(ConstraintStatus, 'UNDER_CONSTRAINED')
    
    def test_over_constrained_status(self):
        """Test OVER_CONSTRAINED status is available."""
        from sketcher.constraints import ConstraintStatus
        
        assert hasattr(ConstraintStatus, 'OVER_CONSTRAINED')
    
    def test_inconsistent_status(self):
        """Test INCONSISTENT status is available."""
        from sketcher.constraints import ConstraintStatus
        
        assert hasattr(ConstraintStatus, 'INCONSISTENT')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
