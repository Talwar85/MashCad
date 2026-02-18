"""
Test für den 3-Punkt Arc Algorithmus.
Prüft verschiedene Konfigurationen (oben, unten, kurz, lang).
"""
import math
import sys
sys.path.insert(0, 'c:\\LiteCad')

from PySide6.QtCore import QPointF


def calc_arc_3point(p1, p2, p3):
    """
    Aktuelle Implementierung aus sketch_handlers.py
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

    # Berechne beide möglichen Bögen (kurz und lang)
    base_span = (a3 - a1) % 360
    
    candidates = [
        (base_span, "ccw_short"),
        (base_span - 360, "ccw_long"),
        (-(360 - base_span), "cw_short"),
        (360 - base_span, "cw_long")
    ]
    
    def point_on_arc(target, start, span):
        if abs(span) < 1e-9:
            return abs((target - start) % 360) < 1e-9
        rel_target = (target - start) % 360
        if span > 0:
            if span <= 360:
                return rel_target <= span + 1e-9
            else:
                return rel_target >= 360 - (span - 360) - 1e-9 or rel_target <= 1e-9
        else:
            span_abs = abs(span)
            if span_abs <= 360:
                return rel_target >= 360 - span_abs - 1e-9 or rel_target <= 1e-9
            else:
                return rel_target >= 360 - span_abs + 360 - 1e-9
    
    for span, name in candidates:
        if point_on_arc(a2, a1, span):
            return (ux, uy, r, a1, a1 + span)
    
    return (ux, uy, r, a1, a1 + base_span)


def point_on_arc(cx, cy, r, start_angle, end_angle, px, py, tol=1e-6):
    """Prüft ob Punkt (px,py) auf dem Arc liegt"""
    # Abstand zum Zentrum
    dist = math.hypot(px - cx, py - cy)
    if abs(dist - r) > tol * r:
        return False
    
    # Winkel prüfen
    angle = math.degrees(math.atan2(py - cy, px - cx))
    
    # Normalisiere auf Bogen
    start = start_angle % 360
    end = end_angle % 360
    target = angle % 360
    
    # Prüfe ob target zwischen start und end liegt
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
    print(f"P1 (Start): ({p1.x()}, {p1.y()})")
    print(f"P2 (Through): ({p2.x()}, {p2.y()})")
    print(f"P3 (End): ({p3.x()}, {p3.y()})")
    
    result = calc_arc_3point(p1, p2, p3)
    if result is None:
        print("❌ FAILED: No arc calculated (collinear?)")
        return False
    
    cx, cy, r, start_angle, end_angle = result
    print(f"\nResult: Center=({cx:.2f}, {cy:.2f}), r={r:.2f}")
    print(f"        Start={start_angle:.2f}°, End={end_angle:.2f}°")
    
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
        print(f"  {status} {desc} ({px}, {py}): {'ON arc' if on_arc else 'NOT on arc'}")
        if not on_arc:
            all_ok = False
    
    # Berechne Sweep
    sweep = (end_angle - start_angle) % 360
    if sweep < 0.1:
        sweep = 360
    print(f"\n  Sweep: {sweep:.2f}° ({'short' if sweep <= 180 else 'LONG'} arc)")
    
    if all_ok:
        print(f"[OK] PASSED")
    else:
        print(f"[FAIL] FAILED")
    
    return all_ok


if __name__ == "__main__":
    print("3-Punkt Arc Algorithmus - Test Suite")
    print("=" * 60)
    
    tests = []
    
    # Test 1: Bogen nach UNTEN (kurzer Bogen, < 180°)
    tests.append(test_arc_config(
        "Arc nach UNTEN (kurz)",
        QPointF(-50, 0),   # Start links
        QPointF(0, -30),   # Through unten
        QPointF(50, 0),    # End rechts
        "Sollte kurzen Bogen nach unten zeichnen"
    ))
    
    # Test 2: Bogen nach OBEN (kurzer Bogen, < 180°)
    tests.append(test_arc_config(
        "Arc nach OBEN (kurz)",
        QPointF(-50, 0),   # Start links
        QPointF(0, 30),    # Through oben
        QPointF(50, 0),    # End rechts
        "Sollte kurzen Bogen nach oben zeichnen"
    ))
    
    # Test 3: Langer Bogen nach unten (> 180°)
    tests.append(test_arc_config(
        "Langer Bogen nach UNTEN",
        QPointF(-50, 0),   # Start links
        QPointF(0, 80),    # Through weit oben (erzwingt langen Bogen unten)
        QPointF(50, 0),    # End rechts
        "Sollte LANGEN Bogen nach unten zeichnen"
    ))
    
    # Test 4: Langer Bogen nach oben (> 180°)
    tests.append(test_arc_config(
        "Langer Bogen nach OBEN",
        QPointF(-50, 0),   # Start links
        QPointF(0, -80),   # Through weit unten (erzwingt langen Bogen oben)
        QPointF(50, 0),    # End rechts
        "Sollte LANGEN Bogen nach oben zeichnen"
    ))
    
    # Test 5: Vertikale Linie, Bogen nach rechts
    tests.append(test_arc_config(
        "Vertikal - Bogen nach RECHTS",
        QPointF(0, -50),   # Start unten
        QPointF(30, 0),    # Through rechts
        QPointF(0, 50),    # End oben
        "Sollte Bogen nach rechts zeichnen"
    ))
    
    # Test 6: Vertikale Linie, Bogen nach links
    tests.append(test_arc_config(
        "Vertikal - Bogen nach LINKS",
        QPointF(0, -50),   # Start unten
        QPointF(-30, 0),   # Through links
        QPointF(0, 50),    # End oben
        "Sollte Bogen nach links zeichnen"
    ))
    
    # Zusammenfassung
    print(f"\n{'='*60}")
    print(f"ERGEBNIS: {sum(tests)}/{len(tests)} Tests bestanden")
    if all(tests):
        print("✅ Alle Tests PASSED!")
    else:
        print("❌ Einige Tests FAILED - Algorithmus muss korrigiert werden")
