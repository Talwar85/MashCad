"""
KORRIGIERTE Version des 3-Punkt Arc Algorithmus.
"""
import math
import sys
sys.path.insert(0, 'c:\\LiteCad')

from PySide6.QtCore import QPointF


def calc_arc_3point_fixed(p1, p2, p3):
    """
    KORRIGIERT: Berechnet einen Arc durch 3 Punkte.
    p1 = Start, p2 = Durchgangspunkt, p3 = Ende
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

    # KORREKTUR: Wir berechnen den Bogen direkt ohne komplizierte Kandidaten
    # Der gesuchte Bogen ist derjenige, bei dem a2 zwischen a1 und a3 liegt
    
    # Berechne beide möglichen Wege von a1 nach a3
    # CCW (gegen Uhrzeigersinn = positive Richtung)
    ccw_span = (a3 - a1) % 360
    
    # CW (im Uhrzeigersinn = negative Richtung)  
    cw_span = -((a1 - a3) % 360)
    
    # WICHTIG: Wir müssen prüfen, welcher Weg a2 enthält
    # Dazu vergleichen wir die Winkel relativ zu a1
    
    def angle_diff(target, start):
        """Gibt den CCW-Abstand von start zu target zurück"""
        return (target - start) % 360
    
    # Wo liegt a2 relativ zu a1?
    a2_rel = angle_diff(a2, a1)
    # Wo liegt a3 relativ zu a1?
    a3_rel = angle_diff(a3, a1)
    
    # Wenn a2_rel <= a3_rel, dann liegt a2 auf dem CCW-Weg
    if a2_rel <= a3_rel + 1e-9:
        # a2 liegt auf dem CCW-Bogen von a1 nach a3
        span = ccw_span
    else:
        # a2 liegt auf dem CW-Bogen von a1 nach a3
        span = cw_span
    
    return (ux, uy, r, a1, a1 + span)


def point_on_arc(cx, cy, r, start_angle, end_angle, px, py, tol=1e-6):
    """Prüft ob Punkt (px,py) auf dem Arc liegt"""
    # Abstand zum Zentrum
    dist = math.hypot(px - cx, py - cy)
    if abs(dist - r) > tol * r:
        return False
    
    # Winkel prüfen - vereinfachte Version
    angle = math.degrees(math.atan2(py - cy, px - cx))
    
    # Normalisiere alle Winkel
    start = start_angle % 360
    end = end_angle % 360
    target = angle % 360
    
    # Prüfe ob target zwischen start und end liegt
    if abs(end_angle - start_angle) >= 360 - 1e-9:
        # Voller Kreis
        return True
    
    if start <= end:
        return start - tol <= target <= end + tol
    else:
        # Über 0° hinweg
        return target >= start - tol or target <= end + tol


def test_arc_config(name, p1, p2, p3, expected_description):
    """Testet eine Konfiguration"""
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"Expected: {expected_description}")
    
    result = calc_arc_3point_fixed(p1, p2, p3)
    if result is None:
        print("[FAIL] Kein Arc berechnet")
        return False
    
    cx, cy, r, start_angle, end_angle = result
    print(f"Center=({cx:.2f}, {cy:.2f}), r={r:.2f}")
    print(f"Start={start_angle:.2f}°, End={end_angle:.2f}°")
    
    # Prüfe alle 3 Punkte
    checks = [
        (p1.x(), p1.y(), "Start"),
        (p2.x(), p2.y(), "Through"),
        (p3.x(), p3.y(), "End")
    ]
    
    all_ok = True
    for px, py, desc in checks:
        on_arc = point_on_arc(cx, cy, r, start_angle, end_angle, px, py)
        status = "[OK]" if on_arc else "[FAIL]"
        print(f"  {status} {desc}: {'ON' if on_arc else 'NOT on'}")
        if not on_arc:
            all_ok = False
    
    # Berechne Sweep
    sweep = (end_angle - start_angle) % 360
    if sweep < 0.1:
        sweep = 360
    print(f"  Sweep: {sweep:.2f}° ({'short' if sweep <= 180 else 'LONG'})")
    
    print(f"[OK] PASSED" if all_ok else "[FAIL] FAILED")
    return all_ok


if __name__ == "__main__":
    print("KORRIGIERTER 3-Punkt Arc Algorithmus - Test Suite")
    
    tests = []
    
    # Test 1: Bogen nach UNTEN
    tests.append(test_arc_config(
        "Arc nach UNTEN",
        QPointF(-50, 0), QPointF(0, -30), QPointF(50, 0),
        "kurzer Bogen nach unten"
    ))
    
    # Test 2: Bogen nach OBEN
    tests.append(test_arc_config(
        "Arc nach OBEN",
        QPointF(-50, 0), QPointF(0, 30), QPointF(50, 0),
        "kurzer Bogen nach oben"
    ))
    
    # Test 3: Vertikal nach RECHTS
    tests.append(test_arc_config(
        "Vertikal - RECHTS",
        QPointF(0, -50), QPointF(30, 0), QPointF(0, 50),
        "Bogen nach rechts"
    ))
    
    # Test 4: Vertikal nach LINKS
    tests.append(test_arc_config(
        "Vertikal - LINKS",
        QPointF(0, -50), QPointF(-30, 0), QPointF(0, 50),
        "Bogen nach links"
    ))
    
    print(f"\n{'='*60}")
    print(f"ERGEBNIS: {sum(tests)}/{len(tests)} Tests bestanden")
