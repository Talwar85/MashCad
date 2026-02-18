"""
Debug-Skript für ARC_3POINT GUI-Verhalten.
Simuliert exakt die GUI-Schritte.
"""
import math
import sys
sys.path.insert(0, 'c:\\LiteCad')

# Importiere exakt wie in der GUI
from PySide6.QtCore import QPointF


def debug_calc_arc_3point(p1, p2, p3):
    """
    Aktuelle Implementierung aus sketch_handlers.py MIT DEBUG OUTPUT
    """
    print(f"\n{'='*60}")
    print("DEBUG _calc_arc_3point")
    print(f"Input types: p1={type(p1)}, p2={type(p2)}, p3={type(p3)}")
    
    # Konvertierung wie in der GUI
    sx, sy = float(p1.x()), float(p1.y())
    mx, my = float(p2.x()), float(p2.y())
    ex, ey = float(p3.x()), float(p3.y())
    
    print(f"Start: ({sx}, {sy})")
    print(f"Through: ({mx}, {my})")
    print(f"End: ({ex}, {ey})")

    # Berechne Umkreis durch 3 Punkte
    d = 2 * (sx * (my - ey) + mx * (ey - sy) + ex * (sy - my))
    print(f"d = {d}")
    
    if abs(d) < 1e-10:
        print("[ERROR] d too small - collinear points")
        return None
    
    ux = ((sx**2 + sy**2) * (my - ey) + (mx**2 + my**2) * (ey - sy) + (ex**2 + ey**2) * (sy - my)) / d
    uy = ((sx**2 + sy**2) * (ex - mx) + (mx**2 + my**2) * (sx - ex) + (ex**2 + ey**2) * (mx - sx)) / d
    r = math.hypot(sx - ux, sy - uy)
    
    print(f"Center: ({ux:.4f}, {uy:.4f}), radius: {r:.4f}")
    
    if r < 1e-9:
        print("[ERROR] radius too small")
        return None

    # Winkel der Punkte vom Zentrum aus
    a1 = math.degrees(math.atan2(sy - uy, sx - ux))
    a2 = math.degrees(math.atan2(my - uy, mx - ux))
    a3 = math.degrees(math.atan2(ey - uy, ex - ux))
    
    print(f"\nAngles from center:")
    print(f"  a1 (start): {a1:.2f}°")
    print(f"  a2 (through): {a2:.2f}°")
    print(f"  a3 (end): {a3:.2f}°")

    # Berechne beide mögliche Bögen (kurz CCW und kurz CW)
    ccw_short = (a3 - a1) % 360
    cw_short = -((a1 - a3) % 360)
    
    print(f"\nCandidate spans:")
    print(f"  CCW short: {ccw_short:.2f}°")
    print(f"  CW short: {cw_short:.2f}°")
    
    def point_on_arc_simple(target, start, end):
        """Prüft ob target auf dem Bogen von start nach end liegt"""
        sweep = end - start
        if abs(sweep) < 1e-9:
            return abs((target - start) % 360) < 1e-9
        
        rel_target = (target - start) % 360
        
        if sweep > 0:  # CCW
            result = rel_target <= sweep + 1e-9
            print(f"    CCW check: rel_target={rel_target:.2f} <= sweep={sweep:.2f} ? {result}")
            return result
        else:  # CW
            rel_target_cw = (start - target) % 360
            result = rel_target_cw <= abs(sweep) + 1e-9
            print(f"    CW check: rel_target_cw={rel_target_cw:.2f} <= abs(sweep)={abs(sweep):.2f} ? {result}")
            return result
    
    # Teste kurze Bögen
    candidates = [
        (a1 + ccw_short, "ccw_short"),
        (a1 + cw_short, "cw_short"),
    ]
    
    print(f"\nTesting candidates:")
    for end_angle, name in candidates:
        print(f"  {name}: end={end_angle:.2f}°")
        if point_on_arc_simple(a2, a1, end_angle):
            print(f"  -> SELECTED: {name}")
            return (ux, uy, r, a1, end_angle)
    
    print(f"  -> FALLBACK: ccw_short")
    return (ux, uy, r, a1, a1 + ccw_short)


def test_gui_simulation():
    """Simuliert die GUI-Schritte"""
    print("="*60)
    print("GUI SIMULATION: ARC_3POINT")
    print("="*60)
    
    # Schritt 1: Startpunkt (z.B. links)
    print("\n[STEP 1] User clicks START point")
    start_pos = QPointF(-50.0, 0.0)
    tool_points = [start_pos]
    print(f"  tool_points = [{start_pos.x()}, {start_pos.y()}]")
    
    # Schritt 2: Endpunkt (z.B. rechts)
    print("\n[STEP 2] User clicks END point")
    end_pos = QPointF(50.0, 0.0)
    tool_points.append(end_pos)
    print(f"  tool_points = [({tool_points[0].x()}, {tool_points[0].y()}), ({tool_points[1].x()}, {tool_points[1].y()})]")
    
    # Schritt 3: Maus bewegt sich (Preview)
    print("\n[STEP 3] Mouse moves (preview)")
    
    # Testfall A: Maus UNTEN
    print("\n--- Test A: Mouse BELOW the line ---")
    mouse_pos = QPointF(0.0, -30.0)  # Unten
    p1_start = tool_points[0]
    p2_end = tool_points[1]
    p3_through = mouse_pos
    
    result = debug_calc_arc_3point(p1_start, p3_through, p2_end)
    if result:
        cx, cy, r, start_a, end_a = result
        sweep = (end_a - start_a) % 360
        if sweep < 0.1:
            sweep = 360
        print(f"\nRESULT: Arc should go DOWN")
        print(f"  Center: ({cx:.2f}, {cy:.2f})")
        print(f"  Expected: cy should be POSITIVE (center above arc)")
        print(f"  Actual cy: {cy:.2f} -> {'OK' if cy > 0 else 'WRONG'}")
    
    # Testfall B: Maus OBEN
    print("\n" + "="*60)
    print("--- Test B: Mouse ABOVE the line ---")
    mouse_pos = QPointF(0.0, 30.0)  # Oben
    p3_through = mouse_pos
    
    result = debug_calc_arc_3point(p1_start, p3_through, p2_end)
    if result:
        cx, cy, r, start_a, end_a = result
        sweep = (end_a - start_a) % 360
        if sweep < 0.1:
            sweep = 360
        print(f"\nRESULT: Arc should go UP")
        print(f"  Center: ({cx:.2f}, {cy:.2f})")
        print(f"  Expected: cy should be NEGATIVE (center below arc)")
        print(f"  Actual cy: {cy:.2f} -> {'OK' if cy < 0 else 'WRONG'}")


if __name__ == "__main__":
    test_gui_simulation()
