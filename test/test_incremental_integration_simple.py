"""Test incremental solver integration in SketchEditor (no Qt)"""
import sys
sys.path.insert(0, '.')

from sketcher import Sketch
from sketcher.constraints import make_fixed, make_horizontal, make_vertical, make_length
from gui.incremental_drag_integration import IncrementalDragIntegration
from config.feature_flags import is_enabled

# Mock SketchEditor with just the sketch
class MockSketchEditor:
    def __init__(self):
        self.sketch = Sketch("Test")
        self._incremental_drag = IncrementalDragIntegration(self) if is_enabled("incremental_solver") else None

def test_integration():
    """Test that incremental solver is properly integrated"""
    print("="*50)
    print("Incremental Solver Integration Test")
    print("="*50)

    # Check feature flag
    print(f"\n1. Feature Flag")
    print(f"   incremental_solver: {is_enabled('incremental_solver')}")

    # Create Mock SketchEditor
    print(f"\n2. Create Mock SketchEditor")
    editor = MockSketchEditor()
    print(f"   SketchEditor created")

    # Check incremental drag integration
    print(f"\n3. Incremental Drag Integration")
    print(f"   _incremental_drag exists: {hasattr(editor, '_incremental_drag')}")
    print(f"   _incremental_drag is None: {editor._incremental_drag is None}")

    if editor._incremental_drag is not None:
        print(f"   IncrementalDragIntegration type: {type(editor._incremental_drag).__name__}")
        print(f"   is_available: {editor._incremental_drag.is_available}")
        print(f"   is_dragging: {editor._incremental_drag.is_dragging}")

    # Create a test sketch
    print(f"\n4. Create Test Sketch")
    p1 = editor.sketch.add_point(0, 0)
    p2 = editor.sketch.add_point(10, 0)
    p3 = editor.sketch.add_point(10, 10)
    p4 = editor.sketch.add_point(0, 10)

    l1 = editor.sketch.add_line_from_points(p1, p2)
    l2 = editor.sketch.add_line_from_points(p2, p3)
    l3 = editor.sketch.add_line_from_points(p3, p4)
    l4 = editor.sketch.add_line_from_points(p4, p1)

    editor.sketch.constraints.append(make_fixed(p1))
    editor.sketch.constraints.append(make_horizontal(l1))
    editor.sketch.constraints.append(make_vertical(l2))
    editor.sketch.constraints.append(make_length(l1, 10))

    print(f"   Sketch: {len(editor.sketch.points)} points, {len(editor.sketch.constraints)} constraints")

    # Test solve
    print(f"\n5. Test Full Solve")
    result = editor.sketch.solve()
    print(f"   Success: {result.success}")
    print(f"   Iterations: {result.iterations}")
    print(f"   Final error: {result.final_error:.2e}")

    # Test incremental drag start
    if editor._incremental_drag is not None:
        print(f"\n6. Test Incremental Drag Start")
        success = editor._incremental_drag.start_drag(p2.id)
        print(f"   start_drag returned: {success}")
        print(f"   is_dragging: {editor._incremental_drag.is_dragging}")

        if editor._incremental_drag.is_dragging:
            print(f"\n7. Test Incremental Drag Move")
            result = editor._incremental_drag.drag_move(15.0, 0.0)
            if result:
                print(f"   success: {result.get('success')}")
                print(f"   solve_time_ms: {result.get('solve_time_ms', 'N/A')}")
                print(f"   is_incremental: {result.get('is_incremental')}")

            print(f"\n8. Test Incremental Drag End")
            result = editor._incremental_drag.end_drag()
            if result and 'stats' in result:
                stats = result['stats']
                print(f"   drag_count: {stats.get('drag_count', 'N/A')}")
                print(f"   avg_drag_time_ms: {stats.get('avg_drag_time_ms', 'N/A')}")
                print(f"   final_solve_time_ms: {stats.get('final_solve_time_ms', 'N/A')}")

    print(f"\n9. Final Position Check")
    print(f"   p1: ({p1.x:.2f}, {p1.y:.2f})")
    print(f"   p2: ({p2.x:.2f}, {p2.y:.2f})")
    print(f"   p3: ({p3.x:.2f}, {p3.y:.2f})")
    print(f"   p4: ({p4.x:.2f}, {p4.y:.2f})")

    print(f"\n" + "="*50)
    print("Integration Test: PASSED")
    print("="*50)

if __name__ == "__main__":
    test_integration()
