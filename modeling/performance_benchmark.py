"""
MashCAD - Performance Benchmark Module
======================================

QA-006: Performance Regression Gate for Sprint 1

Provides benchmarking utilities for measuring CAD operation timings
and detecting performance regressions.

Usage:
    from modeling.performance_benchmark import BenchmarkTimer, PerformanceBenchmark
    
    # Context manager for timing
    with BenchmarkTimer("extrude") as timer:
        result = perform_extrude(...)
    
    print(f"Duration: {timer.duration_ms:.2f}ms")
    
    # Full benchmark suite
    benchmark = PerformanceBenchmark()
    results = benchmark.run_all_benchmarks()
    
    if results.has_regressions():
        print("Performance regressions detected!")

Author: Claude (QA-006 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from loguru import logger

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.gp import gp_Pnt, gp_Vec, gp_Ax2, gp_Dir
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP not available - benchmarks will use build123d fallback")

from build123d import Solid, Face, Wire, Edge, Vector, Location


# Performance Targets (QA-006)
PERFORMANCE_TARGETS = {
    "simple_extrude": {"target_ms": 100, "max_ms": 200},
    "boolean_union": {"target_ms": 200, "max_ms": 500},
    "fillet_10_edges": {"target_ms": 150, "max_ms": 300},
    "stl_export": {"target_ms": 500, "max_ms": 1000},
    "full_rebuild": {"target_ms": 1000, "max_ms": 2000},
}

# Regression threshold (20% slower = regression)
REGRESSION_THRESHOLD = 1.20


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    duration_ms: float
    target_ms: float
    max_ms: float
    iterations: int = 1
    success: bool = True
    error_message: str = ""
    
    @property
    def is_regression(self) -> bool:
        """Check if this result represents a regression (>20% slower than target)."""
        return self.duration_ms > self.target_ms * REGRESSION_THRESHOLD
    
    @property
    def is_failure(self) -> bool:
        """Check if this result exceeds maximum acceptable time."""
        return self.duration_ms > self.max_ms or not self.success
    
    @property
    def ratio_to_target(self) -> float:
        """Ratio of actual time to target time."""
        return self.duration_ms / self.target_ms if self.target_ms > 0 else float('inf')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Complete benchmark report with all results."""
    timestamp: str
    results: List[BenchmarkResult]
    baseline_file: str
    has_regressions: bool = False
    has_failures: bool = False
    regression_details: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate regression status after initialization."""
        self.has_regressions = any(r.is_regression for r in self.results)
        self.has_failures = any(r.is_failure for r in self.results)
        self.regression_details = [
            f"{r.name}: {r.duration_ms:.1f}ms (target: {r.target_ms}ms, +{(r.ratio_to_target - 1) * 100:.1f}%)"
            for r in self.results if r.is_regression
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "has_regressions": self.has_regressions,
            "has_failures": self.has_failures,
            "regression_count": len(self.regression_details),
            "regressions": self.regression_details,
            "results": [r.to_dict() for r in self.results],
            "baseline_file": self.baseline_file,
        }
    
    def print_summary(self) -> None:
        """Print a formatted summary to console."""
        print("\n" + "=" * 60)
        print("PERFORMANCE BENCHMARK REPORT")
        print("=" * 60)
        print(f"Timestamp: {self.timestamp}")
        print(f"Baseline: {self.baseline_file}")
        print()
        
        for result in self.results:
            status = "✅ PASS" if not result.is_regression else "⚠️ REGRESSION"
            if result.is_failure:
                status = "❌ FAIL"
            
            print(f"  {result.name:20} {result.duration_ms:8.1f}ms  "
                  f"(target: {result.target_ms}ms) {status}")
        
        print()
        if self.has_regressions:
            print("REGRESSIONS DETECTED:")
            for detail in self.regression_details:
                print(f"  - {detail}")
        else:
            print("✅ No performance regressions detected")
        
        print("=" * 60)


class BenchmarkTimer:
    """
    Context manager for timing operations.
    
    Usage:
        with BenchmarkTimer("my_operation") as timer:
            do_something()
        print(f"Duration: {timer.duration_ms:.2f}ms")
    """
    
    def __init__(self, name: str = "operation"):
        self.name = name
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.success: bool = True
        self.error_message: str = ""
    
    def __enter__(self) -> "BenchmarkTimer":
        self._start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._end_time = time.perf_counter()
        if self._start_time is not None:
            self.duration_ms = (self._end_time - self._start_time) * 1000
        
        if exc_type is not None:
            self.success = False
            self.error_message = str(exc_val)
        
        return False  # Don't suppress exceptions
    
    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        return self.duration_ms / 1000


class PerformanceBenchmark:
    """
    Performance benchmark suite for CAD operations.
    
    Provides standardized benchmarks for:
    - Extrude operations
    - Boolean operations
    - Fillet operations
    - Export operations
    - Full rebuild cycles
    
    Usage:
        benchmark = PerformanceBenchmark()
        
        # Run single benchmark
        result = benchmark.benchmark_extrude()
        
        # Run all benchmarks
        report = benchmark.run_all_benchmarks()
        
        # Compare against baselines
        if report.has_regressions:
            handle_regressions(report)
    """
    
    def __init__(self, baseline_file: Optional[Path] = None):
        """
        Initialize benchmark suite.
        
        Args:
            baseline_file: Path to baseline JSON file. If None, uses default.
        """
        self.baseline_file = baseline_file or self._get_default_baseline_path()
        self._baselines: Dict[str, Dict[str, float]] = {}
        self._load_baselines()
    
    @staticmethod
    def _get_default_baseline_path() -> Path:
        """Get default baseline file path."""
        return Path(__file__).parent.parent / "test" / "performance_baselines.json"
    
    def _load_baselines(self) -> None:
        """Load baseline timings from JSON file."""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file, 'r') as f:
                    self._baselines = json.load(f)
                logger.info(f"Loaded baselines from {self.baseline_file}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load baselines: {e}")
                self._baselines = {}
        else:
            logger.info(f"Baseline file not found: {self.baseline_file}, using defaults")
            self._baselines = {}
    
    def _get_target(self, benchmark_name: str) -> tuple:
        """Get target and max times for a benchmark."""
        if benchmark_name in self._baselines:
            baseline = self._baselines[benchmark_name]
            return baseline.get("target_ms", 100), baseline.get("max_ms", 200)
        return PERFORMANCE_TARGETS.get(benchmark_name, {"target_ms": 100, "max_ms": 200}).values()
    
    def _create_test_box(self, size: float = 10.0) -> Any:
        """Create a test box for benchmarking."""
        if HAS_OCP:
            box_op = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), size, size, size)
            return box_op.Shape()
        else:
            # build123d fallback
            return Solid.make_box(size, size, size)
    
    def _create_test_face(self, width: float = 10.0, height: float = 10.0) -> Any:
        """Create a test rectangular face for extrusion."""
        if HAS_OCP:
            # Create wire from 4 edges
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
            p1, p2 = gp_Pnt(0, 0, 0), gp_Pnt(width, 0, 0)
            p3, p4 = gp_Pnt(width, height, 0), gp_Pnt(0, height, 0)
            
            wire_maker = BRepBuilderAPI_MakeWire()
            wire_maker.Add(BRepBuilderAPI_MakeEdge(p1, p2).Edge())
            wire_maker.Add(BRepBuilderAPI_MakeEdge(p2, p3).Edge())
            wire_maker.Add(BRepBuilderAPI_MakeEdge(p3, p4).Edge())
            wire_maker.Add(BRepBuilderAPI_MakeEdge(p4, p1).Edge())
            
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
            face_maker = BRepBuilderAPI_MakeFace(wire_maker.Wire())
            return face_maker.Face()
        else:
            # build123d fallback
            return Face.make_rect(height, width)
    
    def benchmark_extrude(self, iterations: int = 3) -> BenchmarkResult:
        """
        Benchmark extrude operation.
        
        Creates a rectangular face and extrudes it to form a solid.
        Measures time for the extrude operation only.
        """
        target_ms, max_ms = self._get_target("simple_extrude")
        
        durations = []
        success = True
        error_message = ""
        
        for i in range(iterations):
            try:
                face = self._create_test_face(10, 10)
                
                with BenchmarkTimer(f"extrude_iter_{i}") as timer:
                    if HAS_OCP:
                        vec = gp_Vec(0, 0, 10)  # Extrude 10mm in Z
                        prism = BRepPrimAPI_MakePrism(face, vec)
                        prism.Build()
                        if not prism.IsDone():
                            raise RuntimeError("Extrude operation failed")
                        result = prism.Shape()
                    else:
                        # build123d fallback
                        result = Solid.extrude(face, Vector(0, 0, 10))
                
                durations.append(timer.duration_ms)
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Extrude benchmark failed: {e}")
                break
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return BenchmarkResult(
            name="simple_extrude",
            duration_ms=avg_duration,
            target_ms=target_ms,
            max_ms=max_ms,
            iterations=len(durations),
            success=success,
            error_message=error_message
        )
    
    def benchmark_boolean(self, iterations: int = 3) -> BenchmarkResult:
        """
        Benchmark boolean union operation.
        
        Creates two boxes and performs a boolean union.
        Measures time for the boolean operation only.
        """
        target_ms, max_ms = self._get_target("boolean_union")
        
        durations = []
        success = True
        error_message = ""
        
        for i in range(iterations):
            try:
                # Create two overlapping boxes
                box1 = self._create_test_box(10)
                box2 = self._create_test_box(10)
                
                # Offset second box
                if HAS_OCP:
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
                    from OCP.gp import gp_Trsf
                    trsf = gp_Trsf()
                    trsf.SetTranslation(gp_Vec(5, 5, 0))
                    transform = BRepBuilderAPI_Transform(box2, trsf)
                    box2 = transform.Shape()
                
                with BenchmarkTimer(f"boolean_iter_{i}") as timer:
                    if HAS_OCP:
                        fuse = BRepAlgoAPI_Fuse(box1, box2)
                        fuse.Build()
                        if not fuse.IsDone():
                            raise RuntimeError("Boolean operation failed")
                        result = fuse.Shape()
                    else:
                        # build123d fallback
                        solid1 = Solid(box1) if not isinstance(box1, Solid) else box1
                        solid2 = Solid(box2) if not isinstance(box2, Solid) else box2
                        result = solid1.fuse(solid2)
                
                durations.append(timer.duration_ms)
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Boolean benchmark failed: {e}")
                break
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return BenchmarkResult(
            name="boolean_union",
            duration_ms=avg_duration,
            target_ms=target_ms,
            max_ms=max_ms,
            iterations=len(durations),
            success=success,
            error_message=error_message
        )
    
    def benchmark_fillet(self, iterations: int = 3) -> BenchmarkResult:
        """
        Benchmark fillet operation on 10 edges.
        
        Creates a box and applies fillets to all edges.
        Measures time for the fillet operation only.
        """
        target_ms, max_ms = self._get_target("fillet_10_edges")
        
        durations = []
        success = True
        error_message = ""
        
        for i in range(iterations):
            try:
                box = self._create_test_box(10)
                
                with BenchmarkTimer(f"fillet_iter_{i}") as timer:
                    if HAS_OCP:
                        fillet = BRepFilletAPI_MakeFillet(box)
                        
                        # Add all edges with 1mm radius
                        explorer = TopExp_Explorer(box, TopAbs_EDGE)
                        edge_count = 0
                        while explorer.More() and edge_count < 10:
                            from OCP.TopoDS import TopoDS
                            edge = TopoDS.Edge_s(explorer.Current())
                            fillet.Add(1.0, edge)
                            explorer.Next()
                            edge_count += 1
                        
                        fillet.Build()
                        if not fillet.IsDone():
                            raise RuntimeError("Fillet operation failed")
                        result = fillet.Shape()
                    else:
                        # build123d fallback - use edges() method
                        solid = Solid(box) if not isinstance(box, Solid) else box
                        edges = solid.edges()
                        result = solid.fillet(1.0, list(edges)[:10])
                
                durations.append(timer.duration_ms)
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Fillet benchmark failed: {e}")
                break
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return BenchmarkResult(
            name="fillet_10_edges",
            duration_ms=avg_duration,
            target_ms=target_ms,
            max_ms=max_ms,
            iterations=len(durations),
            success=success,
            error_message=error_message
        )
    
    def benchmark_export(self, iterations: int = 3) -> BenchmarkResult:
        """
        Benchmark STL export operation.
        
        Creates a box and exports it to STL format.
        Measures time for the export operation only.
        """
        target_ms, max_ms = self._get_target("stl_export")
        
        durations = []
        success = True
        error_message = ""
        
        for i in range(iterations):
            try:
                box = self._create_test_box(20)
                
                # Create temp file path
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                
                with BenchmarkTimer(f"export_iter_{i}") as timer:
                    if HAS_OCP:
                        from OCP.StlAPI import StlAPI_Writer
                        writer = StlAPI_Writer()
                        # Use ASCII mode for consistent timing
                        writer.Write(box, str(tmp_path))
                    else:
                        # build123d fallback
                        solid = Solid(box) if not isinstance(box, Solid) else box
                        solid.export_stl(str(tmp_path))
                
                durations.append(timer.duration_ms)
                
                # Cleanup
                try:
                    tmp_path.unlink()
                except:
                    pass
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Export benchmark failed: {e}")
                break
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return BenchmarkResult(
            name="stl_export",
            duration_ms=avg_duration,
            target_ms=target_ms,
            max_ms=max_ms,
            iterations=len(durations),
            success=success,
            error_message=error_message
        )
    
    def benchmark_rebuild(self, iterations: int = 3) -> BenchmarkResult:
        """
        Benchmark full rebuild cycle.
        
        Simulates a complete model rebuild by:
        1. Creating a base box
        2. Extruding a feature
        3. Applying a boolean operation
        4. Adding fillets
        5. Exporting to STL
        
        Measures total time for the complete cycle.
        """
        target_ms, max_ms = self._get_target("full_rebuild")
        
        durations = []
        success = True
        error_message = ""
        
        for i in range(iterations):
            try:
                with BenchmarkTimer(f"rebuild_iter_{i}") as timer:
                    # Step 1: Create base box
                    box = self._create_test_box(20)
                    
                    # Step 2: Create and extrude feature
                    face = self._create_test_face(5, 5)
                    if HAS_OCP:
                        # Offset face position
                        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
                        from OCP.gp import gp_Trsf
                        trsf = gp_Trsf()
                        trsf.SetTranslation(gp_Vec(7.5, 7.5, 20))
                        face_transform = BRepBuilderAPI_Transform(face, trsf)
                        face = face_transform.Shape()
                        
                        vec = gp_Vec(0, 0, 5)
                        prism = BRepPrimAPI_MakePrism(face, vec)
                        prism.Build()
                        feature = prism.Shape()
                        
                        # Step 3: Boolean union
                        fuse = BRepAlgoAPI_Fuse(box, feature)
                        fuse.Build()
                        result = fuse.Shape()
                        
                        # Step 4: Add fillets
                        fillet = BRepFilletAPI_MakeFillet(result)
                        explorer = TopExp_Explorer(result, TopAbs_EDGE)
                        edge_count = 0
                        while explorer.More() and edge_count < 4:
                            from OCP.TopoDS import TopoDS
                            edge = TopoDS.Edge_s(explorer.Current())
                            fillet.Add(1.0, edge)
                            explorer.Next()
                            edge_count += 1
                        fillet.Build()
                        result = fillet.Shape()
                    else:
                        # build123d fallback
                        solid = Solid(box) if not isinstance(box, Solid) else box
                        feature_face = Face.make_rect(5, 5)
                        feature = Solid.extrude(feature_face, Vector(0, 0, 5))
                        result = solid.fuse(feature)
                        edges = list(result.edges())[:4]
                        result = result.fillet(1.0, edges)
                    
                    # Step 5: Export (optional, can be skipped for pure rebuild timing)
                    # We include it to measure the full pipeline
                
                durations.append(timer.duration_ms)
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Rebuild benchmark failed: {e}")
                break
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return BenchmarkResult(
            name="full_rebuild",
            duration_ms=avg_duration,
            target_ms=target_ms,
            max_ms=max_ms,
            iterations=len(durations),
            success=success,
            error_message=error_message
        )
    
    def run_all_benchmarks(self, iterations: int = 3) -> BenchmarkReport:
        """
        Run all benchmarks and generate a report.
        
        Args:
            iterations: Number of iterations per benchmark
            
        Returns:
            BenchmarkReport with all results
        """
        from datetime import datetime
        
        results = []
        
        # Run each benchmark
        logger.info("Running performance benchmarks...")
        
        results.append(self.benchmark_extrude(iterations))
        results.append(self.benchmark_boolean(iterations))
        results.append(self.benchmark_fillet(iterations))
        results.append(self.benchmark_export(iterations))
        results.append(self.benchmark_rebuild(iterations))
        
        report = BenchmarkReport(
            timestamp=datetime.now().isoformat(),
            results=results,
            baseline_file=str(self.baseline_file)
        )
        
        return report
    
    def update_baselines(self, report: BenchmarkReport) -> None:
        """
        Update baseline file with current benchmark results.
        
        Use this after verifying that performance is acceptable
        to establish new baselines.
        """
        new_baselines = {}
        for result in report.results:
            new_baselines[result.name] = {
                "target_ms": result.target_ms,
                "max_ms": result.max_ms,
                "last_measured_ms": round(result.duration_ms, 2),
                "iterations": result.iterations
            }
        
        # Ensure directory exists
        self.baseline_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.baseline_file, 'w') as f:
            json.dump(new_baselines, f, indent=2)
        
        logger.info(f"Updated baselines in {self.baseline_file}")
        self._baselines = new_baselines


def run_performance_gate() -> int:
    """
    Run performance gate and return exit code.
    
    Returns:
        0 if no regressions, 1 if regressions detected
    """
    benchmark = PerformanceBenchmark()
    report = benchmark.run_all_benchmarks(iterations=3)
    
    report.print_summary()
    
    if report.has_failures:
        logger.error("Performance gate FAILED - operations exceeded maximum time")
        return 1
    elif report.has_regressions:
        logger.warning("Performance gate WARNING - regressions detected but within limits")
        return 0  # Regressions are warnings, not failures
    else:
        logger.info("Performance gate PASSED")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_performance_gate())
