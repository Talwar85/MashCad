#!/usr/bin/env python
"""Debug Script für Ellipse Issues - Ergebnisse der Fixes"""

print("=" * 60)
print("ELLIPSE DEBUG & FIX VALIDATION")
print("=" * 60)

print("""
PROBLEME UND FIXES:
===================

1. PROBLEM: Nur ein Punkt (rechter Major-Punkt) war selektierbar
   URSACHE: Die Konstruktionslinien (Achsen) blockierten die Selektion
   
   FIX: gui/sketch_editor.py
   - _entity_passes_selection_filter(): Ellipsen-Achsen return False
   - _entity_pick_priority(): Ellipsen-Achsen haben Priorität 100 (niedrigst)
   - _pick_direct_edit_handle(): Prüft jetzt auch tatsächliche Achsen-Endpunkte
   - ellipse_hit_radius = hit_radius * 1.5 (größerer Hit-Bereich)

2. PROBLEM: Constraint-Änderungen hatten keine Auswirkung auf Ellipse
   URSACHE: _update_ellipse_geometry() aktualisierte nur Ellipse → Achsen
   
   FIX: sketcher/sketch.py
   - _update_ellipse_geometry() komplett umgeschrieben
   - Berechnet Ellipse-Parameter aus Achsen-Endpunkten (umgekehrt!)
   - Center = Mittelpunkt der Achsen
   - radius_x = Länge(Major-Achse) / 2
   - radius_y = Länge(Minor-Achse) / 2
   - rotation = Winkel der Major-Achse

3. PROBLEM: Center-Drag (grünes Quadrat) funktionierte nicht
   URSACHE: Pick-Logik prüfte nicht den tatsächlichen _center_point
   
   FIX: gui/sketch_editor.py
   - _pick_direct_edit_handle() prüft jetzt:
     * Berechnetes Center (ellipse.center)
     * Tatsächlichen _center_point (ellipse._center_point)
   - Beide führen zu mode="center" für Drag

TESTS:
======
""")

# Test 1: Import-Check
try:
    from sketcher.geometry import Ellipse2D, Point2D
    print("✓ sketcher.geometry import OK")
except Exception as e:
    print(f"✗ sketcher.geometry import FAILED: {e}")

# Test 2: Handle Attribute Check
try:
    from sketcher import Sketch
    sketch = Sketch()
    ellipse = sketch.add_ellipse(0, 0, 10, 5, angle_deg=0)
    
    checks = [
        ("_center_point", hasattr(ellipse, "_center_point")),
        ("_major_axis", hasattr(ellipse, "_major_axis")),
        ("_minor_axis", hasattr(ellipse, "_minor_axis")),
        ("_major_pos", hasattr(ellipse, "_major_pos")),
        ("_major_neg", hasattr(ellipse, "_major_neg")),
        ("_minor_pos", hasattr(ellipse, "_minor_pos")),
        ("_minor_neg", hasattr(ellipse, "_minor_neg")),
    ]
    
    print("\n✓ Handle Attributes:")
    for name, result in checks:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
        
except Exception as e:
    print(f"\n✗ Handle Attribute Check FAILED: {e}")

# Test 3: Axis Markers
try:
    major_axis = ellipse._major_axis
    minor_axis = ellipse._minor_axis
    
    print("\n✓ Axis Line Markers:")
    print(f"  major_axis._ellipse_axis: {getattr(major_axis, '_ellipse_axis', None)}")
    print(f"  minor_axis._ellipse_axis: {getattr(minor_axis, '_ellipse_axis', None)}")
    print(f"  major_axis._ellipse_bundle: {getattr(major_axis, '_ellipse_bundle', None) is ellipse}")
    
except Exception as e:
    print(f"\n✗ Axis Markers Check FAILED: {e}")

# Test 4: GUI Selection Filter
try:
    from gui.sketch_editor import SketchEditor
    editor = SketchEditor()
    
    ellipse2 = editor.sketch.add_ellipse(100, 0, 10, 5, angle_deg=0)
    major_axis = ellipse2._major_axis
    
    passes = editor._entity_passes_selection_filter(major_axis)
    priority = editor._entity_pick_priority(major_axis)
    
    print("\n✓ GUI Selection Filter:")
    print(f"  Axis selectable: {passes} (expected: False)")
    print(f"  Axis priority: {priority} (expected: 100)")
    
    if not passes and priority == 100:
        print("  ✓ PASS: Axis ist nicht selektierbar")
    else:
        print("  ✗ FAIL: Axis ist immer noch selektierbar")
        
except Exception as e:
    print(f"\n✗ GUI Selection Filter Check FAILED: {e}")
    print(f"  (GUI benötigt PySide6 - im Headless-Modus nicht verfügbar)")

print("""
ZUSAMMENFASSUNG DER FIXES:
==========================

Datei: sketcher/sketch.py
- _update_ellipse_geometry(): Berechnet Ellipse aus Achsen (bidirektional)

Datei: gui/sketch_editor.py  
- _entity_passes_selection_filter(): Blockiert Ellipsen-Achsen
- _entity_pick_priority(): Niedrigste Priorität für Achsen
- _pick_direct_edit_handle(): Größerer Hit-Radius, prüft alle Handles
- _start_direct_edit_drag(): Speichert Ellipse für Drag
- _apply_direct_edit_drag(): Wendet Drag auf Ellipse an

ERWARTETES VERHALTEN:
====================
✓ Alle 5 Handles sind selektierbar (grün, 2x rosa, 2x rot)
✓ Constraint-Änderungen an Achsen aktualisieren die Ellipse
✓ Center-Drag verschiebt die ganze Ellipse
✓ Achsen-Längen-Änderungen skalieren die Ellipse
✓ Achsen-Rotation dreht die Ellipse
""")

print("=" * 60)
print("Run this in GUI mode to test actual interactions!")
print("=" * 60)
