"""
Testet die Preview-Logik aus sketch_renderer.py
"""
import math
import sys
sys.path.insert(0, 'c:\\LiteCad')

from PySide6.QtCore import QPointF


def test_preview_logic():
    """Testet die Preview-Logik aus dem Renderer"""
    print("Testing Preview Logic (from sketch_renderer.py)")
    print("="*60)
    
    # Simuliere: 2 Punkte gesetzt, Maus bewegt sich
    tool_points = [
        QPointF(-50, 0),   # Start
        QPointF(50, 0),    # End
    ]
    
    # Teste mit Maus UNTEN
    print("\n--- Preview: Mouse BELOW ---")
    snap = QPointF(0, -30)
    
    # Das ist die Logik aus dem Renderer:
    p1_start = tool_points[0]
    p2_end = tool_points[1]
    p3_through = snap
    
    # Importiere die tatsächliche Funktion
    sys.path.insert(0, 'c:\\LiteCad\\gui')
    from sketch_renderer import SketchRendererMixin
    
    # Erstelle eine Instanz um die Methode zu testen
    class TestRenderer(SketchRendererMixin):
        def __init__(self):
            pass
    
    renderer = TestRenderer()
    result = renderer._calc_arc_3point(p1_start, p3_through, p2_end)
    
    if result:
        cx, cy, r, start_a, end_a = result
        sweep = (end_a - start_a) % 360
        print(f"Arc center: ({cx:.2f}, {cy:.2f})")
        print(f"Expected: cy > 0 for downward arc: {'YES' if cy > 0 else 'NO'}")
        print(f"Sweep: {sweep:.2f}°")
    else:
        print("[ERROR] No arc calculated")
    
    # Teste mit Maus OBEN
    print("\n--- Preview: Mouse ABOVE ---")
    snap = QPointF(0, 30)
    p3_through = snap
    
    result = renderer._calc_arc_3point(p1_start, p3_through, p2_end)
    
    if result:
        cx, cy, r, start_a, end_a = result
        sweep = (end_a - start_a) % 360
        print(f"Arc center: ({cx:.2f}, {cy:.2f})")
        print(f"Expected: cy < 0 for upward arc: {'YES' if cy < 0 else 'NO'}")
        print(f"Sweep: {sweep:.2f}°")
    else:
        print("[ERROR] No arc calculated")


if __name__ == "__main__":
    test_preview_logic()
