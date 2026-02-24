"""
W35 P2: Solver Abstraction Layer

Einheitliche Schnittstelle für verschiedene Solver-Backends.
Ermöglicht kontrolliertes Experimentieren mit alternativen Solvern.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum, auto
import time
from loguru import logger

from .constraints import Constraint, ConstraintStatus


class SolverBackendType(Enum):
    """Verfügbare Solver-Backends"""
    SCIPY_LM = "scipy_lm"           # SciPy Levenberg-Marquardt (default)
    SCIPY_TRF = "scipy_trf"         # SciPy Trust Region Reflective
    STAGED = "staged"               # W35 Experimental: Staged solver


@dataclass
class SolverOptions:
    """Konfigurationsoptionen für Solver"""
    tolerance: float = 1e-6
    max_iterations: int = 1000
    regularization: float = 0.01
    verbose: bool = False
    # P1 Features
    pre_validation: bool = False
    smooth_penalties: bool = False


@dataclass
class SolverProblem:
    """Problem-Definition für Solver"""
    points: List[Any]
    lines: List[Any]
    circles: List[Any]
    arcs: List[Any]
    constraints: List[Constraint]
    options: SolverOptions = field(default_factory=SolverOptions)
    # W35: Spline Control Points für Constraints
    spline_control_points: List[Any] = field(default_factory=list)


@dataclass
class SolverResult:
    """Ergebnis des Constraint-Solvers"""
    success: bool
    iterations: int
    final_error: float
    status: ConstraintStatus
    message: str = ""
    # Zusätzliche Metadaten
    backend_used: str = ""
    solve_time_ms: float = 0.0
    n_variables: int = 0
    n_constraints: int = 0
    dof: int = -1


class ISolverBackend(ABC):
    """
    Abstract Base Class für Solver-Backends.
    
    Jedes Backend muss diese Schnittstelle implementieren,
    um in der Solver-Factory verwendet werden zu können.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name des Backends für Logging/Debugging"""
        pass
    
    @abstractmethod
    def solve(self, problem: SolverProblem) -> SolverResult:
        """
        Löst das Constraint-System.
        
        Args:
            problem: SolverProblem mit Geometrie und Constraints
            
        Returns:
            SolverResult mit Erfolg/Misserfolg und Details
        """
        pass
    
    def can_solve(self, problem: SolverProblem) -> Tuple[bool, str]:
        """
        Prüft, ob dieses Backend das Problem lösen kann.
        
        Args:
            problem: Zu prüfendes Problem
            
        Returns:
            (kann_lösen, grund_wenn_nicht)
        """
        # Default: kann alle Probleme lösen
        return True, ""


class SolverBackendRegistry:
    """
    Registry für verfügbare Solver-Backends.
    
    Ermöglicht dynamische Backend-Auswahl via Feature-Flags.
    """
    
    _backends: Dict[str, ISolverBackend] = {}
    
    @classmethod
    def register(cls, backend_type: SolverBackendType, backend: ISolverBackend):
        """Registriert ein Backend"""
        cls._backends[backend_type.value] = backend
    
    @classmethod
    def get(cls, backend_type: Union[str, SolverBackendType]) -> Optional[ISolverBackend]:
        """Holt ein Backend by type"""
        if isinstance(backend_type, SolverBackendType):
            backend_type = backend_type.value
        return cls._backends.get(backend_type)
    
    @classmethod
    def get_default(cls) -> ISolverBackend:
        """Holt das Default-Backend (SciPy LM)"""
        # Import hier um circular imports zu vermeiden
        from .solver_scipy import SciPyLMBackend
        return cls._backends.get(SolverBackendType.SCIPY_LM.value) or SciPyLMBackend()
    
    @classmethod
    def list_available(cls) -> List[str]:
        """Listet alle verfügbaren Backends auf"""
        return list(cls._backends.keys())


class UnifiedConstraintSolver:
    """
    W35 P2: Unified Solver mit Backend-Auswahl.
    
    Diese Klasse ersetzt den direkten Aufruf von ConstraintSolver
    und ermöglicht Feature-Flag-gesteuerte Backend-Auswahl.
    """
    
    def __init__(self, backend: Optional[ISolverBackend] = None):
        """
        Args:
            backend: Spezifisches Backend (oder None für Auto-Auswahl)
        """
        self._backend = backend
        self._fallback_chain = [
            SolverBackendType.SCIPY_LM,
            SolverBackendType.SCIPY_TRF,
        ]
    
    def _select_backend(self, problem: SolverProblem) -> ISolverBackend:
        """
        Wählt das passende Backend basierend auf Feature-Flags.
        """
        if self._backend is not None:
            return self._backend
        
        # Versuche Feature-Flag zu lesen
        try:
            from config.feature_flags import is_enabled, FEATURE_FLAGS
            
            # Prüfe ob solver_backend explizit gesetzt ist
            backend_name = FEATURE_FLAGS.get("solver_backend", "scipy_lm")
            
            # Hole Backend aus Registry
            backend = SolverBackendRegistry.get(backend_name)
            if backend is not None:
                # Prüfe ob Backend das Problem lösen kann
                can_solve, reason = backend.can_solve(problem)
                if can_solve:
                    return backend
                
                # Backend kann nicht lösen -> Fallback
                logger.warning(f"[Solver] Backend '{backend_name}' cannot solve: {reason}")
            
            # Fallback-Kette durchlaufen
            for fallback_type in self._fallback_chain:
                backend = SolverBackendRegistry.get(fallback_type)
                if backend is not None:
                    can_solve, _ = backend.can_solve(problem)
                    if can_solve:
                        logger.warning(f"[Solver] Falling back to {fallback_type.value}")
                        return backend
            
        except Exception as e:
            logger.error(f"[Solver] Error selecting backend: {e}")
        
        # Ultimate fallback: Default Backend
        return SolverBackendRegistry.get_default()
    
    def solve(self,
              points, lines, circles, arcs, constraints,
              spline_control_points=None,
              progress_callback=None, callback_interval=10) -> SolverResult:
        """
        Löst das Constraint-System mit dem ausgewählten Backend.

        Args:
            points: Liste aller Punkte
            lines: Liste aller Linien
            circles: Liste aller Kreise
            arcs: Liste aller Bögen
            constraints: Liste aller Constraints
            spline_control_points: Liste der Spline-Control-Punkte (optional)
            progress_callback: Optional callback für Fortschritt
            callback_interval: Callback-Intervall in Iterationen

        Returns:
            SolverResult mit Ergebnis
        """
        if spline_control_points is None:
            spline_control_points = []

        # Baue Problem
        options = SolverOptions()

        # Lese P1 Feature-Flags
        try:
            from config.feature_flags import is_enabled
            options.pre_validation = is_enabled("solver_pre_validation")
            options.smooth_penalties = is_enabled("solver_smooth_penalties")
        except Exception:
            pass

        problem = SolverProblem(
            points=points,
            lines=lines,
            circles=circles,
            arcs=arcs,
            constraints=constraints,
            options=options,
            # W35: Spline Control Points für Constraints
            spline_control_points=spline_control_points
        )
        
        # Wähle Backend
        backend = self._select_backend(problem)
        
        # Zeitmessung
        start_time = time.perf_counter()
        
        # Löse
        result = backend.solve(problem)
        
        # Metadaten ergänzen
        result.solve_time_ms = (time.perf_counter() - start_time) * 1000
        result.backend_used = backend.name
        
        return result


# Import und Registrierung der Backends
def _register_backends():
    """Registriert alle verfügbaren Backends"""
    try:
        from .solver_scipy import SciPyLMBackend, SciPyTRFBackend
        SolverBackendRegistry.register(SolverBackendType.SCIPY_LM, SciPyLMBackend())
        SolverBackendRegistry.register(SolverBackendType.SCIPY_TRF, SciPyTRFBackend())
    except ImportError:
        pass  # SciPy nicht verfügbar
    
    try:
        from .solver_staged import StagedSolverBackend
        SolverBackendRegistry.register(SolverBackendType.STAGED, StagedSolverBackend())
    except ImportError:
        pass  # Staged solver nicht verfügbar


# Auto-Registrierung beim Import
_register_backends()
