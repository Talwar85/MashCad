"""
W35 P2: Solver abstraction layer.

Provides a unified interface for selectable solver backends while keeping
backend selection and fallback behavior explicit in the returned result.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from .constraints import Constraint, ConstraintStatus


class SolverBackendType(Enum):
    """Available solver backends."""

    SCIPY_LM = "scipy_lm"
    SCIPY_TRF = "scipy_trf"
    STAGED = "staged"
    INCREMENTAL = "incremental"


@dataclass
class SolverOptions:
    """Configuration for solver backends."""

    tolerance: float = 1e-6
    max_iterations: int = 1000
    regularization: float = 0.01
    verbose: bool = False
    pre_validation: bool = False
    smooth_penalties: bool = False


@dataclass
class SolverProblem:
    """Geometry and constraint bundle passed to backends."""

    points: List[Any]
    lines: List[Any]
    circles: List[Any]
    arcs: List[Any]
    constraints: List[Constraint]
    options: SolverOptions = field(default_factory=SolverOptions)
    spline_control_points: List[Any] = field(default_factory=list)


@dataclass
class SolverResult:
    """Unified solver result."""

    success: bool
    iterations: int
    final_error: float
    status: ConstraintStatus
    message: str = ""
    backend_used: str = ""
    solve_time_ms: float = 0.0
    n_variables: int = 0
    n_constraints: int = 0
    dof: int = -1
    error_code: str = ""
    requested_backend: str = ""
    selection_detail: str = ""


class ISolverBackend(ABC):
    """Common backend contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name used for diagnostics."""
        ...

    @abstractmethod
    def solve(self, problem: SolverProblem) -> SolverResult:
        """Solve the given problem."""
        ...

    def can_solve(self, problem: SolverProblem) -> Tuple[bool, str]:
        """Return whether this backend can solve the problem."""
        return True, ""


class SolverBackendRegistry:
    """Registry of available solver backends."""

    _backends: Dict[str, ISolverBackend] = {}

    @classmethod
    def register(cls, backend_type: SolverBackendType, backend: ISolverBackend):
        cls._backends[backend_type.value] = backend

    @classmethod
    def get(cls, backend_type: Union[str, SolverBackendType]) -> Optional[ISolverBackend]:
        if isinstance(backend_type, SolverBackendType):
            backend_type = backend_type.value
        return cls._backends.get(backend_type)

    @classmethod
    def get_default(cls) -> ISolverBackend:
        from .solver_scipy import SciPyLMBackend

        return cls._backends.get(SolverBackendType.SCIPY_LM.value) or SciPyLMBackend()

    @classmethod
    def list_available(cls) -> List[str]:
        return list(cls._backends.keys())


class UnifiedConstraintSolver:
    """Selects the configured solver backend and makes fallbacks explicit."""

    def __init__(self, backend: Optional[ISolverBackend] = None):
        self._backend = backend
        self._fallback_chain = [
            SolverBackendType.SCIPY_LM,
            SolverBackendType.SCIPY_TRF,
        ]

    def _read_configured_backend_name(self) -> Tuple[str, str]:
        try:
            from config.feature_flags import FEATURE_FLAGS
        except Exception as exc:
            logger.warning(f"[Solver] Feature flags unavailable, defaulting to scipy_lm: {exc}")
            return SolverBackendType.SCIPY_LM.value, "feature flags unavailable"

        backend_name = str(FEATURE_FLAGS.get("solver_backend", SolverBackendType.SCIPY_LM.value) or "").strip()
        if not backend_name:
            return SolverBackendType.SCIPY_LM.value, "empty solver_backend flag"

        return backend_name, ""

    def _select_backend(self, problem: SolverProblem) -> Tuple[ISolverBackend, str, str]:
        if self._backend is not None:
            return self._backend, self._backend.name, "backend injected explicitly"

        backend_name, config_note = self._read_configured_backend_name()
        selection_notes: List[str] = []
        if config_note:
            selection_notes.append(config_note)

        backend = SolverBackendRegistry.get(backend_name)
        if backend is not None:
            try:
                can_solve, reason = backend.can_solve(problem)
            except Exception as exc:
                can_solve = False
                reason = f"backend can_solve failed: {exc}"

            if can_solve:
                return backend, backend_name, "; ".join(selection_notes)

            selection_notes.append(f"requested backend '{backend_name}' cannot solve: {reason}")
            logger.warning(f"[Solver] Backend '{backend_name}' cannot solve: {reason}")
        else:
            selection_notes.append(f"requested backend '{backend_name}' is not registered")
            logger.warning(f"[Solver] Backend '{backend_name}' is not registered")

        for fallback_type in self._fallback_chain:
            fallback_name = fallback_type.value
            backend = SolverBackendRegistry.get(fallback_type)
            if backend is None:
                selection_notes.append(f"fallback backend '{fallback_name}' not registered")
                continue

            try:
                can_solve, reason = backend.can_solve(problem)
            except Exception as exc:
                can_solve = False
                reason = f"backend can_solve failed: {exc}"

            if can_solve:
                selection_notes.append(f"fell back to '{fallback_name}'")
                logger.warning(f"[Solver] Falling back to {fallback_name}")
                return backend, backend_name, "; ".join(selection_notes)

            selection_notes.append(f"fallback backend '{fallback_name}' cannot solve: {reason}")

        default_backend = SolverBackendRegistry.get_default()
        selection_notes.append(f"using default backend '{default_backend.name}' after exhausting fallbacks")
        logger.error(f"[Solver] Exhausted backend selection, using default '{default_backend.name}'")
        return default_backend, backend_name, "; ".join(selection_notes)

    def solve(
        self,
        points,
        lines,
        circles,
        arcs,
        constraints,
        spline_control_points=None,
        progress_callback=None,
        callback_interval=10,
    ) -> SolverResult:
        del progress_callback
        del callback_interval

        if spline_control_points is None:
            spline_control_points = []

        options = SolverOptions()
        try:
            from config.feature_flags import is_enabled
        except Exception as exc:
            logger.warning(f"[Solver] Feature flags unavailable for options: {exc}")
        else:
            options.pre_validation = is_enabled("solver_pre_validation")
            options.smooth_penalties = is_enabled("solver_smooth_penalties")

        problem = SolverProblem(
            points=points,
            lines=lines,
            circles=circles,
            arcs=arcs,
            constraints=constraints,
            options=options,
            spline_control_points=spline_control_points,
        )

        backend, requested_backend, selection_detail = self._select_backend(problem)

        start_time = time.perf_counter()
        result = backend.solve(problem)
        result.solve_time_ms = (time.perf_counter() - start_time) * 1000
        result.backend_used = backend.name
        result.requested_backend = requested_backend
        result.selection_detail = selection_detail

        if selection_detail:
            base_message = str(getattr(result, "message", "") or "").strip()
            if selection_detail not in base_message:
                result.message = f"{base_message} | {selection_detail}" if base_message else selection_detail

        return result


def _register_backends():
    """Register all available solver backends."""
    try:
        from .solver_scipy import SciPyLMBackend, SciPyTRFBackend
    except ImportError as exc:
        logger.warning(f"[Solver] SciPy backends not available: {exc}")
    else:
        SolverBackendRegistry.register(SolverBackendType.SCIPY_LM, SciPyLMBackend())
        SolverBackendRegistry.register(SolverBackendType.SCIPY_TRF, SciPyTRFBackend())

    try:
        from .solver_staged import StagedSolverBackend
    except ImportError as exc:
        logger.warning(f"[Solver] Staged backend not available: {exc}")
    else:
        SolverBackendRegistry.register(SolverBackendType.STAGED, StagedSolverBackend())


_register_backends()
