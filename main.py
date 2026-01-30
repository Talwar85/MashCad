#!/usr/bin/env python3
"""
LiteCAD - Schlankes parametrisches CAD für 3D-Druck
Einstiegspunkt
"""

import sys
import os

# Füge Projektverzeichnis zum Pfad hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Startet LiteCAD"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon

    # App erstellen (muss vor Splash sein)
    app = QApplication(sys.argv)
    app.setApplicationName("MashCAD")
    app.setOrganizationName("MashCAD")
    app.setApplicationVersion("0.1-alpha")

    # App-Icon setzen (für Taskleiste)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Splash Screen anzeigen
    from gui.splash_screen import MashCADSplash
    splash = MashCADSplash()
    splash.show()
    app.processEvents()

    # Bibliotheken laden mit Fortschrittsanzeige
    splash.set_progress(10, "Loading PyVista...")
    try:
        import pyvista
        splash.set_progress(30, f"PyVista {pyvista.__version__} loaded")
    except ImportError:
        splash.set_progress(30, "PyVista not available")

    splash.set_progress(40, "Loading Build123d...")
    try:
        import build123d
        splash.set_progress(60, "Build123d loaded")
    except ImportError:
        splash.set_progress(60, "Build123d not available")

    splash.set_progress(70, "Initializing GUI...")
    from gui.main_window import MainWindow

    splash.set_progress(85, "Creating main window...")
    window = MainWindow()

    splash.set_progress(100, "Ready!")
    app.processEvents()

    # Splash ausblenden und Hauptfenster zeigen
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


def test_sketcher():
    """Testet den Sketcher ohne GUI"""
    from sketcher import Sketch, ConstraintStatus
    
    print("=" * 50)
    print("LiteCAD Sketcher Test")
    print("=" * 50)
    
    # Test 1: Einfaches Rechteck mit Maßen
    print("\n[Test 1] Rechteck 40x30 mit Constraints")
    sketch = Sketch("Test1")
    
    lines = sketch.add_rectangle(0, 0, 40, 30)
    sketch.add_fixed(lines[0].start)
    sketch.add_length(lines[0], 40)
    sketch.add_length(lines[1], 30)
    
    result = sketch.solve()
    print(f"  Status: {result.status.name}")
    print(f"  Iterationen: {result.iterations}")
    print(f"  Fehler: {result.final_error:.6f}")
    
    for i, line in enumerate(lines):
        print(f"  Line {i}: ({line.start.x:.2f}, {line.start.y:.2f}) -> "
              f"({line.end.x:.2f}, {line.end.y:.2f}), L={line.length:.2f}")
    
    # Test 2: Zwei gleich lange Linien
    print("\n[Test 2] Zwei Linien mit Equal Length")
    sketch2 = Sketch("Test2")
    
    l1 = sketch2.add_line(0, 0, 30, 0)
    l2 = sketch2.add_line(0, 20, 50, 20)
    
    sketch2.add_fixed(l1.start)
    sketch2.add_fixed(l2.start)
    sketch2.add_horizontal(l1)
    sketch2.add_horizontal(l2)
    sketch2.add_equal_length(l1, l2)
    sketch2.add_length(l1, 25)
    
    result2 = sketch2.solve()
    print(f"  Status: {result2.status.name}")
    print(f"  L1: ({l1.start.x:.2f}, {l1.start.y:.2f}) -> ({l1.end.x:.2f}, {l1.end.y:.2f}), L={l1.length:.2f}")
    print(f"  L2: ({l2.start.x:.2f}, {l2.start.y:.2f}) -> ({l2.end.x:.2f}, {l2.end.y:.2f}), L={l2.length:.2f}")
    
    # Test 3: Kreis mit Radius
    print("\n[Test 3] Kreis mit Radius-Constraint")
    sketch3 = Sketch("Test3")
    
    circle = sketch3.add_circle(50, 50, 20)
    sketch3.add_fixed(circle.center)
    sketch3.add_radius(circle, 15)
    
    result3 = sketch3.solve()
    print(f"  Status: {result3.status.name}")
    print(f"  Kreis: Zentrum=({circle.center.x:.2f}, {circle.center.y:.2f}), R={circle.radius:.2f}")
    
    # Test 4: Parallele Linien
    print("\n[Test 4] Parallele Linien")
    sketch4 = Sketch("Test4")
    
    l1 = sketch4.add_line(0, 0, 30, 10)
    l2 = sketch4.add_line(0, 30, 40, 50)
    
    sketch4.add_fixed(l1.start)
    sketch4.add_fixed(l1.end)
    sketch4.add_fixed(l2.start)
    sketch4.add_parallel(l1, l2)
    
    result4 = sketch4.solve()
    print(f"  Status: {result4.status.name}")
    print(f"  L1 Winkel: {l1.angle:.2f}°")
    print(f"  L2 Winkel: {l2.angle:.2f}°")
    
    print("\n" + "=" * 50)
    print("Tests abgeschlossen!")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_sketcher()
    else:
        main()
