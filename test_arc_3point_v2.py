"""
KORRIGIERTE Version 2 - Einfacherer Ansatz.
"""
import math
import sys
sys.path.insert(0, 'c:\\LiteCad')

from PySide6.QtCore import QPointF


def calc_arc_3point_v2(p1, p2, p3):
    """
    Berechnet einen Arc durch 3 Punkte.
    Einfacher Ansatz: Berechne beide mögliche Bögen und wähle den,
    dessen Mittelpunkt näher am Durchgangspunkt liegt.
    """
    sx, sy = float(p1.x()), float(p1.y())
    mx, my = float(p2.x()), float(p2.y())
    ex, ey = float(p3.x()), float(p3.y())

    # Berechne Umkreis durch 3 Punkte
    d = 2 * (sx * (my - ey) + mx * (ey - sy) + ex * (sy - my))
    if abs(d) < 1e-10:
        return None
    
    ux = ((sx**2 + sy**2) * (my - ey) + (mx**2 + my**2) * (ey - sy) + (ex**2 + ey**2) * (sy - my)) / d
    uy = ((sx**2 + sy**2) * (ex - mx) + (mx**2 + my**2) * (sx - ex) + (ex**2 + ey**2) * (mx - sx)) / d
    r = math.hypot(sx - ux, sy - uy)
    
    if r < 1e-9:
        return None

    # Winkel der Punkte vom Zentrum aus
    a1 = math.degrees(math.atan2(sy - uy, sx - ux))
    a2 = math.degrees(math.atan2(my - uy, mx - ux))
    a3 = math.degrees(math.atan2(ey - uy, ex - ux))

    # Berechne beide mögliche Bögen (kurz und lang)
    # Kurzer Bogen CCW
    ccw_short = (a3 - a1) % 360
    # Kurzer Bogen CW (negativ)
    cw_short = -((a1 - a3) % 360)
    
    # Langer Bogen = kurzer Bogen mit umgekehrtem Vorzeichen + 360 bzw -360
    ccw_long = ccw_short + 360 if ccw_short < 180 else ccw_short - 360
    cw_long = cw_short - 360 if cw_short > -180 else cw_short + 360
    
    def point_on_arc_simple(target, start, end):
        """Prüft ob target auf dem Bogen von start nach end liegt (end kann > 360 oder < 0 sein)"""
        # Berechne den Sweep
        sweep = end - start
        
        # Normalisiere target relativ zu start
        rel_target = (target - start) % 360
        
        # Wenn sweep positiv (CCW)
        if sweep > 0:
            return rel_target <= sweep + 1e-9
        else:  # sweep negativ (CW)
            # Für CW müssen wir in die andere Richtung prüfen
            rel_target_cw = (start - target) % 360
            return rel_target_cw <= abs(sweep) + 1e-9
    
    # Teste alle 4 Varianten
    candidates = [
        (a1 + ccw_short, "ccw_short"),
        (a1 + cw_short, "cw_short"),
    ]
    
    # Füge lange Bögen nur hinzu, wenn sie wirklich anders sind
    if abs(ccw_long) > 180:
        candidates.append((a1 + ccw_long, "ccw_long"))
    if abs(cw_long) > 180:
        candidates.append((a1 + cw_long, "cw_long"))
    
    for end_angle, name in candidates:
        if point_on_arc_simple(a2, a1, end_angle):
            return (ux, uy, r, a1, end_angle)
    
    # Fallback
    return (ux, uy, r, a1, a1 + ccw_short)


def point_on_arc(cx, cy, r, start_angle, end_angle, px, py, tol=1e-6):
    """Prüft ob Punkt auf dem Arc liegt"""
    dist = math.hypot(px - cx, py - cy)
    if abs(dist - r) > tol * r:
        return False
    
    angle = math.degrees(math.atan2(py - cy, px - cx))
    
    # Berechne Sweep
    sweep = (end_angle - start_angle)
    
    # Normalisiere target
    rel_target = (angle - start_angle) % 360
    
    if sweep > 0:  # CCW
        return rel_target <= sweep + tol or rel_target >= 360 - tol
    else:  # CW
        rel_target_cw = (start_angle - angle) % 360
        return rel_target_cw <= abs(sweep) + tol or rel_target_cw >= 360 - tol


def test_arc_config(name, p1, p2, p3, expected):
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    
    result = calc_arc_3point_v2(p1, p2, p3)
    if result is None:
        print("[FAIL] Kein Arc")
        return False
    
    cx, cy, r, start_angle, end_angle = result
    print(f"Center=({cx:.2f}, {cy:.2f}), r={r:.2f}")
    print(f"Angles: {start_angle:.2f}° -> {end_angle:.2f}°")
    
    checks = [
        (p1.x(), p1.y(), "Start"),
        (p2.x(), p2.y(), "Through"),
        (p3.x(), p3.y(), "End")
    ]
    
    all_ok = True
    for px, py, desc in checks:
        on_arc = point_on_arc(cx, cy, r, start_angle, end_angle, px, py)
        status = "[OK]" if on_arc else "[FAIL]"
        print(f"  {status} {desc}: {'ON' if on_arc else 'NOT'}")
        if not on_arc:
            all_ok = False
    
    sweep = abs(end_angle - start_angle) % 360
    if sweep < 0.1:
        sweep = 360
    print(f"  Sweep: {sweep:.2f}°")
    
    print("[OK] PASSED" if all_ok else "[FAIL] FAILED")
    return all_ok


if __name__ == "__main__":
    print("3-Punkt Arc - Version 2 - Test Suite")
    
    tests = []
    
    # Alle Testfälle
    test_cases = [
        ("Arc UNTEN", QPointF(-50, 0), QPointF(0, -30), QPointF(50, 0)),
        ("Arc OBEN", QPointF(-50, 0), QPointF(0, 30), QPointF(50, 0)),
        ("Vertikal RECHTS", QPointF(0, -50), QPointF(30, 0), QPointF(0, 50)),
        ("Vertikal LINKS", QPointF(0, -50), QPointF(-30, 0), QPointF(0, 50)),
        ("Horizontal UNTEN", QPointF(-50, 0), QPointF(0, -40), QPointF(50, 0)),
        ("Horizontal OBEN", QPointF(-50, 0), QPointF(0, 40), QPointF(50, 0)),
    ]
    
    for name, p1, p2, p3 in test_cases:
        tests.append(test_arc_config(name, p1, p2, p3, ""))
    
    print(f"\n{'='*60}")
    print(f"ERGEBNIS: {sum(tests)}/{len(tests)} Tests bestanden")
