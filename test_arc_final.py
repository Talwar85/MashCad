"""
Finale Test für den korrigierten ARC_3POINT Algorithmus.
"""
import math
import sys
sys.path.insert(0, 'c:\\LiteCad')

from PySide6.QtCore import QPointF


def calc_arc_3point_fixed(p1, p2, p3):
    """
    KORRIGIERTE Version aus sketch_handlers.py
    Für CW Bögen werden Start/End vertauscht, damit der Sweep immer positiv ist.
    """
    sx, sy = float(p1.x()), float(p1.y())
    mx, my = float(p2.x()), float(p2.y())
    ex, ey = float(p3.x()), float(p3.y())

    d = 2 * (sx * (my - ey) + mx * (ey - sy) + ex * (sy - my))
    if abs(d) < 1e-10:
        return None
    
    ux = ((sx**2 + sy**2) * (my - ey) + (mx**2 + my**2) * (ey - sy) + (ex**2 + ey**2) * (sy - my)) / d
    uy = ((sx**2 + sy**2) * (ex - mx) + (mx**2 + my**2) * (sx - ex) + (ex**2 + ey**2) * (mx - sx)) / d
    r = math.hypot(sx - ux, sy - uy)
    
    if r < 1e-9:
        return None

    a1 = math.degrees(math.atan2(sy - uy, sx - ux))
    a2 = math.degrees(math.atan2(my - uy, mx - ux))
    a3 = math.degrees(math.atan2(ey - uy, ex - ux))

    ccw_short = (a3 - a1) % 360
    cw_short = -((a1 - a3) % 360)
    
    def point_on_arc_simple(target, start, span):
        if abs(span) < 1e-9:
            return abs((target - start) % 360) < 1e-9
        rel_target = (target - start) % 360
        span_abs = abs(span)
        if span > 0:
            return rel_target <= span + 1e-9
        else:
            return rel_target >= (360 - span_abs) - 1e-9
    
    if point_on_arc_simple(a2, a1, ccw_short):
        # CCW: Normal ausgeben
        return (ux, uy, r, a1, a1 + ccw_short)
    else:
        # CW: Start/End vertauschen!
        return (ux, uy, r, a3, a1)


def test_arc(name, p1, p2, p3, expected_desc):
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"Expected: {expected_desc}")
    
    result = calc_arc_3point_fixed(p1, p2, p3)
    if not result:
        print("[FAIL] No result")
        return False
    
    cx, cy, r, start, end = result
    sweep = (end - start) % 360
    
    print(f"Center: ({cx:.2f}, {cy:.2f}), r={r:.2f}")
    print(f"Start: {start:.2f}°, End: {end:.2f}°")
    print(f"Sweep: {sweep:.2f}°")
    
    # Prüfe ob alle 3 Punkte auf dem Kreis liegen
    for pt, desc in [(p1, "Start"), (p2, "Through"), (p3, "End")]:
        dist = math.hypot(pt.x() - cx, pt.y() - cy)
        on_circle = abs(dist - r) < 1e-6
        print(f"  {desc}: {'ON circle' if on_circle else 'NOT on circle'}")
    
    # Validierung
    if sweep > 180:
        print(f"[WARN] Long arc ({sweep:.1f}°) - might be wrong")
    else:
        print(f"[OK] Short arc ({sweep:.1f}°)")
    
    return True


if __name__ == "__main__":
    print("ARC_3POINT Final Test")
    
    tests = []
    
    # Arc UNTEN
    tests.append(test_arc(
        "Arc UNTEN",
        QPointF(-50, 0), QPointF(0, -30), QPointF(50, 0),
        "Bogen nach unten, Center Y > 0"
    ))
    
    # Arc OBEN
    tests.append(test_arc(
        "Arc OBEN", 
        QPointF(-50, 0), QPointF(0, 30), QPointF(50, 0),
        "Bogen nach oben, Center Y < 0"
    ))
    
    print(f"\n{'='*60}")
    print(f"All tests completed")
