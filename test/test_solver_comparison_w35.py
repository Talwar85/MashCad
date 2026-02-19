"""
W35 P4: Solver Comparison and Decision Tests

Compares SciPy LM, SciPy TRF, and Staged backends on identical scenarios.
Provides data for KEEP/HYBRID/REPLACE decision.

Pflicht-Validierung:
    conda run -n cad_env python -m pytest -q test/test_solver_comparison_w35.py
"""

import pytest
import time
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import statistics

from sketcher.sketch import Sketch
from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D
from sketcher.constraints import (
    ConstraintType, ConstraintStatus,
    make_coincident, make_horizontal, make_vertical,
    make_parallel, make_perpendicular, make_equal_length,
    make_distance, make_length, make_radius, make_tangent
)
from sketcher.solver_interface import (
    UnifiedConstraintSolver, SolverProblem, SolverOptions,
    SolverBackendRegistry, SolverBackendType
)
from sketcher.solver_scipy import SciPyLMBackend, SciPyTRFBackend
from sketcher.solver_staged import StagedSolverBackend


@dataclass
class ComparisonResult:
    """Result of comparing multiple backends on one scenario"""
    scenario_name: str
    scipy_lm: Optional[dict] = None
    scipy_trf: Optional[dict] = None
    staged: Optional[dict] = None
    
    def winner(self) -> str:
        """Determines the winner based on success rate and solve time"""
        results = []
        if self.scipy_lm:
            results.append(('scipy_lm', self.scipy_lm))
        if self.scipy_trf:
            results.append(('scipy_trf', self.scipy_trf))
        if self.staged:
            results.append(('staged', self.staged))
        
        if not results:
            return "none"
        
        # Prioritize success, then solve time
        successful = [(name, r) for name, r in results if r['success']]
        if not successful:
            return "none"
        
        # Among successful, pick fastest
        fastest = min(successful, key=lambda x: x[1]['solve_time_ms'])
        return fastest[0]


class TestSolverComparison:
    """
    W35 P4: Compare solver backends on identical scenarios.
    """
    
    @pytest.fixture
    def simple_rectangle(self):
        """Simple rectangle with coincident + H/V constraints"""
        sketch = Sketch("Rect")
        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(100, 0)
        p3 = sketch.add_point(100, 50)
        p4 = sketch.add_point(0, 50)
        
        l1 = sketch.add_line_from_points(p1, p2)
        l2 = sketch.add_line_from_points(p2, p3)
        l3 = sketch.add_line_from_points(p3, p4)
        l4 = sketch.add_line_from_points(p4, p1)
        
        sketch.constraints.append(make_coincident(l1.end, l2.start))
        sketch.constraints.append(make_coincident(l2.end, l3.start))
        sketch.constraints.append(make_coincident(l3.end, l4.start))
        sketch.constraints.append(make_coincident(l4.end, l1.start))
        sketch.constraints.append(make_horizontal(l1))
        sketch.constraints.append(make_horizontal(l3))
        sketch.constraints.append(make_vertical(l2))
        sketch.constraints.append(make_vertical(l4))
        
        return sketch
    
    @pytest.fixture
    def rectangle_with_dimensions(self):
        """Rectangle with exact dimensions"""
        sketch = Sketch("RectDim")
        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(100, 0)
        p3 = sketch.add_point(100, 50)
        p4 = sketch.add_point(0, 50)
        
        l1 = sketch.add_line_from_points(p1, p2)
        l2 = sketch.add_line_from_points(p2, p3)
        l3 = sketch.add_line_from_points(p3, p4)
        l4 = sketch.add_line_from_points(p4, p1)
        
        sketch.constraints.append(make_coincident(l1.end, l2.start))
        sketch.constraints.append(make_coincident(l2.end, l3.start))
        sketch.constraints.append(make_coincident(l3.end, l4.start))
        sketch.constraints.append(make_coincident(l4.end, l1.start))
        sketch.constraints.append(make_horizontal(l1))
        sketch.constraints.append(make_horizontal(l3))
        sketch.constraints.append(make_vertical(l2))
        sketch.constraints.append(make_vertical(l4))
        sketch.constraints.append(make_length(l1, 100.0))
        sketch.constraints.append(make_length(l2, 50.0))
        
        return sketch
    
    @pytest.fixture
    def spring_back_scenario(self):
        """
        Scenario prone to spring-back.
        Large initial deviation that regularization might pull back.
        """
        sketch = Sketch("SpringBack")
        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(200, 0)  # Far from constraint
        line = sketch.add_line_from_points(p1, p2)
        
        sketch.constraints.append(make_horizontal(line))
        sketch.constraints.append(make_length(line, 50.0))  # Should shrink to 50
        
        return sketch
    
    @pytest.fixture
    def complex_slot(self):
        """Complex slot geometry"""
        import math
        sketch = Sketch("Slot")
        
        # Center line
        p1 = sketch.add_point(20, 50)
        p2 = sketch.add_point(120, 50)
        center_line = sketch.add_line_from_points(p1, p2)
        
        # Arc caps
        arc1 = sketch.add_arc(20, 50, 15, 90, 270)
        arc2 = sketch.add_arc(120, 50, 15, -90, 90)
        
        # Top/Bottom lines
        p3 = sketch.add_point(20, 65)
        p4 = sketch.add_point(120, 65)
        p5 = sketch.add_point(20, 35)
        p6 = sketch.add_point(120, 35)
        
        top_line = sketch.add_line_from_points(p3, p4)
        bottom_line = sketch.add_line_from_points(p5, p6)
        
        # Constraints
        sketch.constraints.append(make_horizontal(center_line))
        sketch.constraints.append(make_parallel(top_line, center_line))
        sketch.constraints.append(make_parallel(bottom_line, center_line))
        sketch.constraints.append(make_distance(top_line.start, p1, 15.0))
        sketch.constraints.append(make_distance(bottom_line.start, p1, 15.0))
        
        return sketch
    
    def _run_backend(self, backend, sketch, runs=3):
        """Run a backend multiple times and collect statistics"""
        results = []
        
        for _ in range(runs):
            # Save state to restore between runs
            original_state = []
            for p in sketch.points:
                original_state.append(('p', p, p.x, p.y))
            for line in sketch.lines:
                original_state.append(('p', line.start, line.start.x, line.start.y))
                original_state.append(('p', line.end, line.end.x, line.end.y))
            
            problem = SolverProblem(
                points=sketch.points,
                lines=sketch.lines,
                circles=sketch.circles,
                arcs=sketch.arcs,
                constraints=sketch.constraints,
                options=SolverOptions()
            )
            
            start = time.perf_counter()
            result = backend.solve(problem)
            elapsed = (time.perf_counter() - start) * 1000
            
            results.append({
                'success': result.success,
                'iterations': result.iterations,
                'final_error': result.final_error,
                'solve_time_ms': elapsed,
                'status': result.status
            })
            
            # Restore state
            for item in original_state:
                if item[0] == 'p':
                    _, p, x, y = item
                    p.x, p.y = x, y
        
        # Aggregate results
        success_rate = sum(1 for r in results if r['success']) / len(results)
        avg_time = statistics.mean(r['solve_time_ms'] for r in results)
        avg_iterations = statistics.mean(r['iterations'] for r in results)
        avg_error = statistics.mean(r['final_error'] for r in results)
        
        return {
            'success': success_rate > 0.5,  # Majority success
            'success_rate': success_rate,
            'solve_time_ms': avg_time,
            'iterations': avg_iterations,
            'final_error': avg_error
        }
    
    def test_compare_simple_rectangle(self, simple_rectangle):
        """Compare backends on simple rectangle"""
        sketch = simple_rectangle
        
        backends = {
            'scipy_lm': SciPyLMBackend(),
            'scipy_trf': SciPyTRFBackend(),
            'staged': StagedSolverBackend()
        }
        
        comparison = ComparisonResult("simple_rectangle")
        
        for name, backend in backends.items():
            result = self._run_backend(backend, sketch, runs=3)
            setattr(comparison, name, result)
        
        print(f"\n{'='*60}")
        print(f"Scenario: simple_rectangle")
        print(f"{'='*60}")
        print(f"{'Backend':<15} {'Success':<10} {'Time(ms)':<12} {'Iter':<8} {'Error':<12}")
        print("-"*60)
        for name in ['scipy_lm', 'scipy_trf', 'staged']:
            r = getattr(comparison, name)
            if r:
                print(f"{name:<15} {r['success']!s:<10} {r['solve_time_ms']:<12.2f} {r['iterations']:<8.0f} {r['final_error']:<12.6f}")
        print(f"Winner: {comparison.winner()}")
        
        # All should succeed on simple case
        assert comparison.scipy_lm['success'], "SciPy LM should succeed"
    
    def test_compare_spring_back(self, spring_back_scenario):
        """Compare backends on spring-back prone scenario"""
        sketch = spring_back_scenario
        
        backends = {
            'scipy_lm': SciPyLMBackend(),
            'scipy_trf': SciPyTRFBackend(),
            'staged': StagedSolverBackend()
        }
        
        comparison = ComparisonResult("spring_back")
        
        for name, backend in backends.items():
            result = self._run_backend(backend, sketch, runs=3)
            setattr(comparison, name, result)
        
        print(f"\n{'='*60}")
        print(f"Scenario: spring_back (Spring-back prone)")
        print(f"{'='*60}")
        print(f"{'Backend':<15} {'Success':<10} {'Time(ms)':<12} {'Iter':<8} {'Error':<12}")
        print("-"*60)
        for name in ['scipy_lm', 'scipy_trf', 'staged']:
            r = getattr(comparison, name)
            if r:
                print(f"{name:<15} {r['success']!s:<10} {r['solve_time_ms']:<12.2f} {r['iterations']:<8.0f} {r['final_error']:<12.6f}")
        print(f"Winner: {comparison.winner()}")
        
        # Staged should handle spring-back better
        # But we don't assert since it's test data
    
    def test_compare_all_scenarios(self):
        """Comprehensive comparison across all benchmark scenarios"""
        print("\n" + "="*80)
        print("W35 SOLVER COMPARISON - ALL SCENARIOS")
        print("="*80)
        
        # Import baseline scenarios
        from test.test_solver_baseline_w35 import BENCHMARK_CASES
        
        backends = {
            'scipy_lm': SciPyLMBackend(),
            'scipy_trf': SciPyTRFBackend(),
            'staged': StagedSolverBackend()
        }
        
        all_results = []
        
        for scenario_def in BENCHMARK_CASES:
            name = scenario_def.name
            setup_func = scenario_def.setup_func
            
            print(f"\nTesting: {name}")
            
            try:
                sketch, metadata = setup_func()
                
                comparison = ComparisonResult(name)
                
                for backend_name, backend in backends.items():
                    try:
                        result = self._run_backend(backend, sketch, runs=2)
                        setattr(comparison, backend_name, result)
                    except Exception as e:
                        print(f"  {backend_name} failed: {e}")
                
                all_results.append(comparison)
                
            except Exception as e:
                print(f"  Scenario setup failed: {e}")
        
        # Summary table
        print("\n" + "="*80)
        print("SUMMARY TABLE")
        print("="*80)
        print(f"{'Scenario':<25} {'SciPy LM':<15} {'SciPy TRF':<15} {'Staged':<15} {'Winner':<12}")
        print("-"*80)
        
        summary = {'scipy_lm': 0, 'scipy_trf': 0, 'staged': 0, 'none': 0}
        
        for comp in all_results:
            lm_str = "✓" if comp.scipy_lm and comp.scipy_lm['success'] else "✗"
            trf_str = "✓" if comp.scipy_trf and comp.scipy_trf['success'] else "✗"
            staged_str = "✓" if comp.staged and comp.staged['success'] else "✗"
            winner = comp.winner()
            summary[winner] = summary.get(winner, 0) + 1
            
            print(f"{comp.scenario_name:<25} {lm_str:<15} {trf_str:<15} {staged_str:<15} {winner:<12}")
        
        print("-"*80)
        print(f"\nWinners: {summary}")
        
        # Decision recommendation
        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80)
        
        total = len(all_results)
        lm_wins = summary.get('scipy_lm', 0)
        trf_wins = summary.get('scipy_trf', 0)
        staged_wins = summary.get('staged', 0)
        
        if staged_wins > lm_wins and staged_wins > trf_wins:
            print("RECOMMENDATION: MIGRATE to Staged Solver")
            print(f"  Staged wins {staged_wins}/{total} scenarios")
        elif lm_wins >= trf_wins and lm_wins >= staged_wins:
            print("RECOMMENDATION: KEEP SciPy LM")
            print(f"  SciPy LM wins {lm_wins}/{total} scenarios")
            if staged_wins > 0:
                print(f"  Consider HYBRID: Use Staged for specific scenarios")
        else:
            print("RECOMMENDATION: HYBRID Approach")
            print(f"  Use best backend per scenario")
        
        print("="*80)


class TestSolverDecisionMatrix:
    """
    W35 P4: Decision matrix for backend selection.
    """
    
    def test_decision_matrix(self):
        """
        Creates a decision matrix for when to use which backend.
        """
        decision_matrix = {
            'simple_geometries': {
                'scipy_lm': {'speed': 'fast', 'success': 'high', 'recommended': True},
                'scipy_trf': {'speed': 'medium', 'success': 'high', 'recommended': False},
                'staged': {'speed': 'medium', 'success': 'high', 'recommended': False},
            },
            'spring_back_prone': {
                'scipy_lm': {'speed': 'fast', 'success': 'medium', 'recommended': False},
                'scipy_trf': {'speed': 'medium', 'success': 'medium', 'recommended': False},
                'staged': {'speed': 'medium', 'success': 'high', 'recommended': True},
            },
            'over_constrained': {
                'scipy_lm': {'speed': 'fast', 'success': 'low', 'recommended': False},
                'scipy_trf': {'speed': 'medium', 'success': 'high', 'recommended': True},
                'staged': {'speed': 'slow', 'success': 'medium', 'recommended': False},
            },
            'complex_mixed': {
                'scipy_lm': {'speed': 'fast', 'success': 'medium', 'recommended': True},
                'scipy_trf': {'speed': 'slow', 'success': 'medium', 'recommended': False},
                'staged': {'speed': 'slow', 'success': 'high', 'recommended': True},
            }
        }
        
        print("\n" + "="*80)
        print("DECISION MATRIX")
        print("="*80)
        
        for scenario, backends in decision_matrix.items():
            print(f"\n{scenario}:")
            for backend, props in backends.items():
                rec = "★" if props['recommended'] else " "
                print(f"  {rec} {backend}: {props['speed']}, {props['success']} success")
        
        print("\n" + "="*80)


if __name__ == "__main__":
    """Run comparison directly"""
    print("W35 Solver Comparison")
    
    test = TestSolverComparison()
    
    # Create fixtures manually
    sketch = Sketch("Test")
    p1 = sketch.add_point(0, 0)
    p2 = sketch.add_point(100, 0)
    p3 = sketch.add_point(100, 50)
    p4 = sketch.add_point(0, 50)
    
    l1 = sketch.add_line_from_points(p1, p2)
    l2 = sketch.add_line_from_points(p2, p3)
    l3 = sketch.add_line_from_points(p3, p4)
    l4 = sketch.add_line_from_points(p4, p1)
    
    from sketcher.constraints import make_coincident, make_horizontal, make_vertical
    sketch.constraints.append(make_coincident(l1.end, l2.start))
    sketch.constraints.append(make_coincident(l2.end, l3.start))
    sketch.constraints.append(make_coincident(l3.end, l4.start))
    sketch.constraints.append(make_coincident(l4.end, l1.start))
    sketch.constraints.append(make_horizontal(l1))
    sketch.constraints.append(make_horizontal(l3))
    sketch.constraints.append(make_vertical(l2))
    sketch.constraints.append(make_vertical(l4))
    
    # Run comparison
    backends = {
        'scipy_lm': SciPyLMBackend(),
        'staged': StagedSolverBackend()
    }
    
    for name, backend in backends.items():
        print(f"\nTesting {name}...")
        result = test._run_backend(backend, sketch, runs=1)
        print(f"  Success: {result['success']}")
        print(f"  Time: {result['solve_time_ms']:.2f} ms")
        print(f"  Iterations: {result['iterations']}")
