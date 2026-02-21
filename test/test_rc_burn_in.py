"""
RC Burn-in Test Suite - QA-010
==============================

Extended stress tests for V1.0 Release Candidate validation.
Tests memory leaks, long-running stability, and repeated operation cycles.

Usage:
    pytest test/test_rc_burn_in.py -v
    pytest test/test_rc_burn_in.py -v -k stress
    pytest test/test_rc_burn_in.py -v --iterations=1000
"""

import gc
import os
import sys
import time
import tracemalloc
import pytest
from typing import List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.feature_flags import is_enabled, set_flag


# Note: pytest_addoption, iterations, and memory_samples fixtures
# are now defined in test/conftest.py for global availability


@pytest.fixture
def enable_burn_in_mode():
    """Enable RC burn-in mode for tests."""
    original = is_enabled("rc_burn_in_mode")
    set_flag("rc_burn_in_mode", True)
    yield
    set_flag("rc_burn_in_mode", original)


class TestMemoryStability:
    """Memory leak detection and stability tests."""
    
    def test_memory_no_leak_basic_operations(self, iterations: int, memory_samples: int):
        """
        Test that basic modeling operations don't leak memory.
        
        Creates and destroys objects repeatedly, sampling memory
        to detect leaks.
        """
        try:
            from OCP.TopoDS import TopoDS_Shape
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.gp import gp_Pnt
        except ImportError:
            pytest.skip("OCP not available")
        
        tracemalloc.start()
        baseline_samples = []
        
        # Warmup phase
        for _ in range(10):
            box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(10, 10, 10))
            shape = box.Shape()
            del box, shape
        
        gc.collect()
        
        # Baseline measurement
        for _ in range(memory_samples):
            current, _ = tracemalloc.get_traced_memory()
            baseline_samples.append(current)
            time.sleep(0.1)
        
        baseline_avg = sum(baseline_samples) / len(baseline_samples)
        
        # Stress test phase
        test_samples = []
        for i in range(iterations):
            box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(10 + i, 10, 10))
            shape = box.Shape()
            del box, shape
            
            if i % (iterations // memory_samples) == 0:
                gc.collect()
                current, _ = tracemalloc.get_traced_memory()
                test_samples.append(current)
        
        gc.collect()
        
        # Final measurement
        final_samples = []
        for _ in range(memory_samples):
            current, _ = tracemalloc.get_traced_memory()
            final_samples.append(current)
            time.sleep(0.1)
        
        final_avg = sum(final_samples) / len(final_samples)
        
        tracemalloc.stop()
        
        # Allow 10% growth tolerance
        max_acceptable = baseline_avg * 1.10
        assert final_avg < max_acceptable, (
            f"Memory leak detected: baseline={baseline_avg / 1024:.1f}KB, "
            f"final={final_avg / 1024:.1f}KB, "
            f"growth={((final_avg / baseline_avg) - 1) * 100:.1f}%"
        )
    
    def test_memory_boolean_operations(self, iterations: int):
        """Test memory stability during repeated boolean operations."""
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
            from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
        except ImportError:
            pytest.skip("OCP not available")
        
        tracemalloc.start()
        
        # Initial measurement
        gc.collect()
        initial_mem, _ = tracemalloc.get_traced_memory()
        
        for i in range(iterations):
            # Create two shapes
            box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(20, 20, 20))
            cyl_axis = gp_Ax2(gp_Pnt(10, 10, 0), gp_Dir(0, 0, 1))
            cyl = BRepPrimAPI_MakeCylinder(cyl_axis, 5, 25)
            
            # Boolean cut
            cut = BRepAlgoAPI_Cut(box.Shape(), cyl.Shape())
            result = cut.Shape()
            
            del box, cyl, cut, result
            
            if i % 50 == 0:
                gc.collect()
        
        gc.collect()
        final_mem, _ = tracemalloc.get_traced_memory()
        
        tracemalloc.stop()
        
        # Allow 5MB growth
        growth = final_mem - initial_mem
        assert growth < 5 * 1024 * 1024, (
            f"Excessive memory growth in boolean ops: {growth / 1024 / 1024:.1f}MB"
        )


class TestLongRunningStability:
    """Tests for long-running operation stability."""
    
    def test_extended_tessellation_stability(self, iterations: int):
        """Test tessellation doesn't degrade over many operations."""
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.gp import gp_Pnt
        except ImportError:
            pytest.skip("OCP not available")
        
        failure_count = 0
        timeouts = 0
        
        for i in range(iterations):
            try:
                sphere = BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, 0), 10 + (i % 10))
                shape = sphere.Shape()
                
                # Tessellate
                mesh = BRepMesh_IncrementalMesh(shape, 0.1)
                mesh.Perform()
                
                if not mesh.IsDone():
                    failure_count += 1
                
                del sphere, shape, mesh
                
            except Exception as e:
                if "timeout" in str(e).lower():
                    timeouts += 1
                failure_count += 1
        
        failure_rate = failure_count / iterations * 100
        assert failure_rate < 1.0, (
            f"Tessellation failure rate too high: {failure_rate:.1f}% "
            f"({failure_count}/{iterations})"
        )
    
    def test_filleting_stability(self, iterations: int):
        """Test fillet operations remain stable over many iterations."""
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.gp import gp_Pnt
        except ImportError:
            pytest.skip("OCP not available")
        
        failures = []
        
        for i in range(min(iterations, 50)):  # Cap at 50 for fillets
            try:
                size = 10 + (i % 5)
                box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(size, size, size))
                shape = box.Shape()
                
                fillet = BRepFilletAPI_MakeFillet(shape)
                
                # Add all edges
                explorer = TopExp_Explorer(shape, TopAbs_EDGE)
                edge_count = 0
                while explorer.More():
                    fillet.Add(1.0, explorer.Current())
                    explorer.Next()
                    edge_count += 1
                
                fillet.Build()
                
                if not fillet.IsDone():
                    failures.append(f"Iteration {i}: Fillet not done")
                
                del box, shape, fillet
                
            except Exception as e:
                failures.append(f"Iteration {i}: {str(e)}")
        
        failure_rate = len(failures) / min(iterations, 50) * 100
        assert failure_rate < 5.0, (
            f"Fillet failure rate too high: {failure_rate:.1f}%\n"
            f"Failures: {failures[:5]}"
        )


class TestRepeatedOperationCycles:
    """Tests for repeated create/destroy cycles."""
    
    def test_create_destroy_cycle_stability(self, iterations: int):
        """Test stability of repeated object creation and destruction."""
        try:
            from OCP.BRepPrimAPI import (
                BRepPrimAPI_MakeBox,
                BRepPrimAPI_MakeCylinder,
                BRepPrimAPI_MakeSphere,
                BRepPrimAPI_MakeCone
            )
            from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
        except ImportError:
            pytest.skip("OCP not available")
        
        errors = []
        
        for i in range(iterations):
            try:
                # Create various primitives
                box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(10, 10, 10))
                cyl = BRepPrimAPI_MakeCylinder(
                    gp_Ax2(gp_Pnt(5, 5, 0), gp_Dir(0, 0, 1)), 3, 10
                )
                sphere = BRepPrimAPI_MakeSphere(gp_Pnt(5, 5, 5), 4)
                cone = BRepPrimAPI_MakeCone(
                    gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 5, 2, 10
                )
                
                # Get shapes
                shapes = [
                    box.Shape(),
                    cyl.Shape(),
                    sphere.Shape(),
                    cone.Shape()
                ]
                
                # Verify shapes are valid
                for shape in shapes:
                    if shape.IsNull():
                        errors.append(f"Iteration {i}: Null shape created")
                
                # Explicit cleanup
                del box, cyl, sphere, cone, shapes
                
            except Exception as e:
                errors.append(f"Iteration {i}: {str(e)}")
            
            # Periodic garbage collection
            if i % 100 == 0:
                gc.collect()
        
        error_rate = len(errors) / iterations * 100
        assert error_rate < 0.5, (
            f"Create/destroy error rate too high: {error_rate:.2f}%\n"
            f"Errors: {errors[:5]}"
        )
    
    def test_sketch_cycle_stability(self, iterations: int):
        """Test sketch creation/destruction cycles."""
        try:
            from sketcher.sketch import Sketch
            from sketcher.geometry import Point, Line, Circle
        except ImportError:
            pytest.skip("Sketcher not available")
        
        errors = []
        
        for i in range(min(iterations, 100)):  # Cap at 100 for sketches
            try:
                sketch = Sketch()
                
                # Add geometry
                points = [
                    Point(0, 0),
                    Point(10, 0),
                    Point(10, 10),
                    Point(0, 10)
                ]
                
                for pt in points:
                    sketch.add_point(pt)
                
                # Add lines
                for j in range(len(points)):
                    line = Line(points[j], points[(j + 1) % len(points)])
                    sketch.add_line(line)
                
                # Add circle
                circle = Circle(Point(5, 5), 3)
                sketch.add_circle(circle)
                
                # Verify
                if len(sketch.points) != 4:
                    errors.append(f"Iteration {i}: Wrong point count")
                if len(sketch.lines) != 4:
                    errors.append(f"Iteration {i}: Wrong line count")
                
                del sketch, points, circle
                
            except Exception as e:
                errors.append(f"Iteration {i}: {str(e)}")
        
        error_rate = len(errors) / min(iterations, 100) * 100
        assert error_rate < 2.0, (
            f"Sketch cycle error rate too high: {error_rate:.1f}%\n"
            f"Errors: {errors[:5]}"
        )


class TestFeatureFlagStability:
    """Test feature flag behavior under stress."""
    
    def test_feature_flag_toggle_stability(self, iterations: int):
        """Test that feature flag toggles don't cause issues."""
        test_flags = [
            "sketch_debug",
            "extrude_debug",
            "viewport_debug",
        ]
        
        errors = []
        
        for i in range(iterations):
            try:
                for flag in test_flags:
                    original = is_enabled(flag)
                    set_flag(flag, not original)
                    new_value = is_enabled(flag)
                    
                    if new_value == original:
                        errors.append(f"Iteration {i}: Flag {flag} didn't toggle")
                    
                    # Restore
                    set_flag(flag, original)
                    
            except Exception as e:
                errors.append(f"Iteration {i}: {str(e)}")
        
        assert len(errors) == 0, f"Feature flag errors: {errors[:5]}"
    
    def test_concurrent_flag_access(self, iterations: int):
        """Test that flag access is thread-safe (basic test)."""
        from config.feature_flags import get_all_flags
        
        errors = []
        
        for i in range(iterations):
            try:
                flags = get_all_flags()
                
                if not isinstance(flags, dict):
                    errors.append(f"Iteration {i}: get_all_flags didn't return dict")
                
                if len(flags) == 0:
                    errors.append(f"Iteration {i}: Empty flags dict")
                    
            except Exception as e:
                errors.append(f"Iteration {i}: {str(e)}")
        
        assert len(errors) == 0, f"Concurrent access errors: {errors[:5]}"


class TestExportStability:
    """Test export operations under stress."""
    
    def test_stl_export_stability(self, iterations: int):
        """Test STL export stability over many iterations."""
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.StlAPI import StlAPI_Writer
            from OCP.gp import gp_Pnt
            import tempfile
        except ImportError:
            pytest.skip("OCP not available")
        
        errors = []
        
        for i in range(min(iterations, 20)):  # Cap at 20 for file I/O
            try:
                # Create shape
                box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(10, 10, 10))
                shape = box.Shape()
                
                # Tessellate
                mesh = BRepMesh_IncrementalMesh(shape, 0.1)
                mesh.Perform()
                
                # Write STL
                with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
                    temp_path = f.name
                
                writer = StlAPI_Writer()
                writer.Write(shape, temp_path)
                
                # Verify file was created
                if not os.path.exists(temp_path):
                    errors.append(f"Iteration {i}: STL file not created")
                elif os.path.getsize(temp_path) == 0:
                    errors.append(f"Iteration {i}: Empty STL file")
                
                # Cleanup
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                
                del box, shape, mesh, writer
                
            except Exception as e:
                errors.append(f"Iteration {i}: {str(e)}")
        
        error_rate = len(errors) / min(iterations, 20) * 100
        assert error_rate < 10.0, (
            f"STL export error rate too high: {error_rate:.1f}%\n"
            f"Errors: {errors[:5]}"
        )


class TestNumericalStability:
    """Test numerical precision under stress."""
    
    def test_boolean_precision_stability(self, iterations: int):
        """Test that boolean operations maintain precision."""
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
            from OCP.BRepCheck import BRepCheck_Analyzer
            from OCP.gp import gp_Pnt
        except ImportError:
            pytest.skip("OCP not available")
        
        invalid_count = 0
        
        for i in range(min(iterations, 50)):
            try:
                # Create two overlapping boxes
                box1 = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(10, 10, 10))
                box2 = BRepPrimAPI_MakeBox(gp_Pnt(5, 5, 5), gp_Pnt(15, 15, 15))
                
                # Boolean fuse
                fuse = BRepAlgoAPI_Fuse(box1.Shape(), box2.Shape())
                result = fuse.Shape()
                
                # Validate result
                analyzer = BRepCheck_Analyzer(result)
                if not analyzer.IsValid():
                    invalid_count += 1
                
                del box1, box2, fuse, result, analyzer
                
            except Exception:
                invalid_count += 1
        
        invalid_rate = invalid_count / min(iterations, 50) * 100
        assert invalid_rate < 2.0, (
            f"Boolean invalid result rate too high: {invalid_rate:.1f}%"
        )


# Stress test markers
@pytest.mark.stress
class TestHighLoadScenarios:
    """High-load stress tests for extended burn-in."""
    
    @pytest.mark.slow
    def test_sustained_high_load(self, iterations: int):
        """
        Test sustained high load over extended period.
        This test is marked slow and may take significant time.
        """
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
            from OCP.gp import gp_Pnt
        except ImportError:
            pytest.skip("OCP not available")
        
        # Use 10x iterations for sustained load test
        sustained_iterations = iterations * 10
        
        start_time = time.time()
        operations_completed = 0
        errors = []
        
        for i in range(sustained_iterations):
            try:
                box1 = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(20, 20, 20))
                box2 = BRepPrimAPI_MakeBox(gp_Pnt(5, 5, 5), gp_Pnt(15, 15, 15))
                
                cut = BRepAlgoAPI_Cut(box1.Shape(), box2.Shape())
                _ = cut.Shape()
                
                operations_completed += 1
                del box1, box2, cut
                
                # Periodic cleanup
                if i % 100 == 0:
                    gc.collect()
                    
            except Exception as e:
                errors.append(str(e))
                if len(errors) > 10:
                    break
        
        end_time = time.time()
        duration = end_time - start_time
        ops_per_second = operations_completed / duration if duration > 0 else 0
        
        error_rate = len(errors) / sustained_iterations * 100
        
        # Log performance metrics
        print(f"\nSustained load test results:")
        print(f"  Operations: {operations_completed}/{sustained_iterations}")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Ops/sec: {ops_per_second:.1f}")
        print(f"  Error rate: {error_rate:.2f}%")
        
        assert error_rate < 1.0, f"High load error rate: {error_rate:.2f}%"
        assert ops_per_second > 10, f"Performance too low: {ops_per_second:.1f} ops/sec"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
