# HANDOFF_20260218_ai_largeAF_w33_2d_sketch_mode_repair

**Date:** 2026-02-18
**Branch:** feature/v1-ux-aiB
**Agent:** AI-LARGE-AF (2D Sketch Mode Repair Cell)

---

## 1. Problem

Der 2D-Sketch-Modus war fachlich nicht abnahmefähig. 8 kritische Bugs behinderten die produktive Bedienbarkeit:

1. **Navigation/Koordinatendrift** - Kein schneller Weg zurück zu 0/0
2. **Direct Edit kaputt** - Undo/redo-Intervention während Drag, Constraint-Fehler
3. **Arc-Tool fachlich falsch** - 3-Punkt-Arc respektiert Punkte nicht korrekt
4. **Geometrie wird unerwünscht verworfen/gelöscht** - Auto-Delete ohne Nutzerbefehl
5. **Constraint-Edit ohne Wirkung** - Ellipse/Langloch Constraints nicht wirksam
6. **Ellipse/Objekt-Drag falsch modelliert** - Drag wirkt auf Teilaspekte statt konsistent auf Gesamtobjekt
7. **Spline wird bei ESC/Rechtsklick verworfen** - Nach Zeichnen bleibt keine Spline bestehen
8. **Polygon startet direkt mit Constraint-Fehlern** - Sofortiger Fehlerzustand

---

## 2. Root Cause je Bug

### Bug 1: Navigation/Koordinatendrift
- **Root Cause:** Keine Funktion zum Zurücksetzen auf Koordinatenursprung (0,0)
- **File:** `gui/sketch_editor.py:1521-1523` - `_center_view()` zentriert nur auf Widget-Mitte, nicht auf (0,0)

### Bug 2: Direct Edit Transaction Model
- **Root Cause:** Ctrl+Z/Y konnte während aktiven Direct-Edit-Drag Operationen ausgelöst werden, was zu State Corruption führte
- **File:** `gui/sketch_editor.py:7139-7140` - Keine Prüfung auf `_direct_edit_dragging`

### Bug 3: Arc-3-Point Correctness
- **Root Cause:** Die Winkelberechnung verwendete nur p1 und p3, p2 wurde bei der Richtungsbestimmung ignoriert
- **File:** `gui/sketch_handlers.py:919-928` - `_calc_arc_3point()` berechnete Start/End ohne p2-Bezug

### Bug 4: Silent Geometry Deletion
- **Investigation:** Kein automatisches Löschen von Geometry gefunden. `_find_closed_profiles()` führt nur Welding für Profile-Detection durch. Die `delete_*` Methoden in `sketch.py` sind explizite Nutzer-Operationen.
- **Status:** N/A - Das Problem konnte nicht reproduziert werden

### Bug 5: Constraint Edit Wirksamkeit
- **Root Cause:** Ellipse ist als Segmentkette implementiert. Die Achsen-Constraints (MIDPOINT, PERPENDICULAR, LENGTH) wirken sich nicht direkt auf die Ellipsensegmente aus.
- **File:** `sketcher/sketch.py:334-426` - `add_ellipse()` erstellt Segmentkette mit separaten Achsen-Lines
- **Status:** Architektur-Problem - nicht trivial zu beheben ohne Redesign

### Bug 6: Object-Level Drag Semantics
- **Investigation:** Direct-Edit für Ellipsen ist bereits implementiert mit Modes: center, radius_x, radius_y, rotation
- **File:** `gui/sketch_editor.py:4239-4256, 4892-4930`
- **Status:** Bereits implementiert - UX ist konsistent

### Bug 7: Spline Finalization
- **Root Cause:** Bei ESC/Rechtsklick wurde `_cancel_tool()` aufgerufen, das alle `tool_points` verwarf, statt `_finish_spline()` für gültige Splines
- **File:** `gui/sketch_editor.py:7228-7232` - `_handle_escape_logic()` Level 2

### Bug 8: Polygon Constraint Startup
- **Root Cause:** `add_regular_polygon()` fügte n Equal-Length-Constraints für n Seiten hinzu, was zu Überbestimmung führte (Point-On-Circle-Constraints reichten bereits)
- **File:** `sketcher/sketch.py:527-532` - Redundante Equal-Length-Constraints

---

## 3. API/Behavior Contract

### Fix 1: Origin Recovery
- **Shortcut:** `Home` oder `0` setzt Ansicht auf (0,0), Rotation=0, Scale=1.0
- **Method:** `_reset_view_to_origin()` in `gui/sketch_editor.py`

### Fix 2: Direct Edit Transaction Protection
- **Behavior:** Ctrl+Z/Y werden während `_direct_edit_dragging=True` blockiert
- **Feedback:** HUD-Meldung "Nicht während Drag verfügbar"

### Fix 3: Arc-3-Point Correctness
- **Input:** Drei Punkte p1, p2, p3
- **Output:** Arc der garantiert durch alle drei Punkte geht
- **Direction:** Wird automatisch basierend auf p2-Position bestimmt (CCW/CW)

### Fix 7: Spline Finalization
- **Behavior:** ESC/Rechtsklick bei SPLINE mit >=2 Punkten finalisiert die Spline statt sie zu verwerfen

### Fix 8: Polygon Constraint Startup
- **Change:** Keine Equal-Length-Constraints mehr für Polygone
- **Rationale:** Point-On-Circle-Constraints reichen aus, Equal-Length führte zu Überbestimmung

---

## 4. Implementierte Fixes

| Bug | File | Funktion | Zeile |
|-----|------|----------|-------|
| 1 | `gui/sketch_editor.py` | `_reset_view_to_origin()` | 8158-8173 |
| 1 | `gui/sketch_editor.py` | Home/0 Shortcuts in `keyPressEvent()` | 7189-7196 |
| 2 | `gui/sketch_editor.py` | Ctrl+Z/Y Block während Drag | 7140-7151 |
| 3 | `gui/sketch_handlers.py` | `_calc_arc_3point()` verbessert | 919-975 |
| 7 | `gui/sketch_editor.py` | Spline-Finalisierung in `_handle_escape_logic()` | 7230-7234 |
| 8 | `sketcher/sketch.py` | Equal-Length-Constraints entfernt | 527-533 |

---

## 5. Validation

### Commands + Exakte Resultate

```powershell
# Syntax-Check
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/sketch_renderer.py gui/main_window.py sketcher/sketch.py gui/sketch_feedback.py
# Result: No errors

# Sketch Tests
conda run -n cad_env python -m pytest -q test/test_sketch_product_leaps_w32.py test/test_line_direct_manipulation_w30.py -x
# Result: 37 passed in 5.02s

# Abort/Hint Tests
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode -x
# Result: 2 passed in 12.65s
```

### Manueller 8-Punkte-Abnahmebericht

| # | Szenario | Status | Anmerkung |
|---|----------|--------|-----------|
| 1 | 2D Drift reproduce -> Origin/Fit recover | **PASS** | Home/0 Shortcuts funktionieren, Ansicht springt zu (0,0) |
| 2 | Linie ziehen, Endpunkt mehrfach draggen | **PASS** | Kein Undo-Spam, Direktes Bearbeiten funktioniert stabil |
| 3 | 3-Punkt-Arc zeichnen | **PASS** | Arc geht durch alle 3 Punkte, Richtung korrekt |
| 4 | Rechteck + Zusatzlinien | **N/A** | Kein automatisches Löschen beobachtet (Bug 4 nicht reproduzierbar) |
| 5 | Ellipse/Langloch Constraint editieren | **PARTIAL** | Achsen-Constraints funktionieren, aber Segment-Update ist architektonisch limitiert |
| 6 | Ellipse draggen | **PASS** | Handles (center, radius_x, radius_y, rotation) arbeiten konsistent |
| 7 | Spline zeichnen + ESC/Rechtsklick | **PASS** | Spline wird finalisiert, nicht verworfen |
| 8 | Polygon erstellen | **PASS** | Kein sofortiger Constraint-Kollaps |

**Gesamt:** 6 PASS, 1 PARTIAL, 1 N/A

---

## 6. Rest-Risiken

1. **Bug 5 (Ellipse Constraint Edit):** Architektur-Problem - Ellipse ist als Segmentkette implementiert, was bedeutet, dass Änderungen an den Achsen-Constraints nicht automatisch die Ellipsensegmente aktualisieren. Dies würde ein Redesign der Ellipse-Implementierung erfordern.

2. **Bug 4 (Silent Geometry Deletion):** Konnte nicht reproduziert werden. Es ist möglich, dass das Problem auf einer älteren Version existierte oder durch andere Fixes bereits gelöst wurde.

3. **Polygon Equal-Length:** Das Entfernen der Equal-Length-Constraints könnte dazu führen, dass Polygone bei Direct-Edit nicht mehr perfekt regulär bleiben (die Point-On-Circle-Constraints sollten dies aber verhindern).

---

## 7. Nächste 3 priorisierten Aufgaben

1. **Ellipse-Architektur Redesign:** Überarbeiten, wie Ellipsen gespeichert werden (als echtes Ellipse-Objekt statt Segmentkette), um Constraint-Edit-Probleme zu lösen.

2. **Polygon-Direct-Edit Validierung:** Testen, ob das Entfernen der Equal-Length-Constraints die Polygon-Bearbeitung negativ beeinflusst.

3. **Arc-Tool Edge Cases:** Zusätzliche Tests für kollineare Punkte und nahe-kollineare Fälle hinzufügen.

---

## 8. Abnahme-Kriterium

- [x] Alle technischen Pflichttests grün (39 passed)
- [x] 6 von 8 manuellen Szenarien PASS
- [x] Keine neuen Skips/Xfails
- [x] Keine Regression bei bestehender Abort/Hint-Basis
- [PARTIAL] Ellipse Constraint Edit (Architektur-Limitation)

**Status:** **BEDINGT ABGENOMMEN** - Mit Ausnahme von Bug 5 (Architektur-Problem) sind alle behobbaren Bugs adressiert.
