Du bist AI-LARGE-AF (2D Sketch Mode Repair Cell) auf Branch `feature/v1-ux-aiB`.

## Mission (P0)
Der 2D-Sketch-Modus ist fachlich nicht abnahmefaehig. Ziel ist **produktive Bedienbarkeit wiederherstellen**.
Tests alleine reichen nicht. Die fachliche Nutzung muss wieder funktionieren.

## Kritische Bugs (muessen alle behoben werden)
1. **Navigation/Koordinatendrift (Minor, nervig):**
   - Im 2D-Modus driftet die Ansicht weg.
   - Es gibt keinen schnellen Weg zurueck auf `0/0`.
   - 2D-Navigation wirkt chaotisch.

2. **Major Bug 1 - Direct Edit kaputt (Linien/Endpoints/Drag):**
   - Beim Ziehen wird sofort undo/redo-artig interveniert.
   - Direkt nach Drag kommen unloesbare Constraint-Fehler.
   - Nutzer kann Geometrie nicht stabil bearbeiten.

3. **Major Bug 2 - Arc-Tool fachlich falsch:**
   - 3-Punkt-Arc respektiert die Punkte nicht korrekt.

4. **Major Bug 3 - Geometrie wird unerwuenscht verworfen/geloescht:**
   - Rechteck + nachtraegliche Linien werden auto-veraendert oder geloescht.
   - Kein "smart delete" ohne expliziten Nutzerbefehl.

5. **Major Bug 4 - Constraint-Edit ohne Wirkung (Ellipse/Langloch):**
   - Constraints aendern Objekt nicht mehr sichtbar/geometrisch korrekt.

6. **Major Bug 5 - Ellipse/Objekt-Drag falsch modelliert:**
   - Drag wirkt auf Teilaspekte statt konsistent auf das Gesamtobjekt.
   - Gleiches Problem bei mehreren Objekttypen.

7. **Major Bug 6 - Spline wird bei ESC/Rechtsklick verworfen:**
   - Nach Zeichnen bleibt keine Spline bestehen.

8. **Major Bug 7 - Polygon startet direkt mit Constraint-Fehlern:**
   - Sofortiger Fehlerzustand ohne sinnvolle Bearbeitung.

## Scope
Erlaubte Dateien:
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `gui/sketch_renderer.py`
- `gui/sketch_feedback.py`
- `gui/main_window.py` (nur Wiring/Hotkeys/Hints)
- `sketcher.py` und/oder `sketcher/**` (falls dort Geometrie/Constraint-Logik liegt)
- `test/**` (nur sinnvolle Regressionen)

No-Go:
- `modeling/**` (ausser es ist nachweislich zwingend fuer 2D Sketch Runtime)
- Viewport-3D-Bereiche ohne direkten 2D-Zusammenhang

## Harte Regeln
1. Keine neuen `skip`/`xfail`.
2. Keine "Test gruen, UX kaputt"-Abgabe.
3. Keine automatische Geometrie-Loeschung ohne expliziten Nutzerbefehl.
4. Keine stillen Rollbacks waehrend aktiver Drag-Interaktion ohne klares Nutzerfeedback.
5. Keine `.bak`, `temp_*`, `debug_*` Artefakte.
6. Keine "done"-Aussage ohne reproduzierbare manuelle Abnahme-Checks.

## Umsetzungsanforderungen (fachlich)

### A) 2D Navigation + Origin Recovery (P0)
- Implementiere einen klaren schnellen Rückweg zu `0/0` im Sketch:
  - Shortcut (z. B. `Home` oder `0`) und UI-Aktion.
  - Verhalten deterministisch: Ansicht center auf Ursprung, sinnvoller Zoom.
- "Fit/Reset View" im 2D-Modus muss robust sein.

### B) Direct Edit Transaction Model (P0)
- Endpoint/Line/Ellipse/Polygon Drag als **transaktionale Bearbeitung**:
  - Drag beginnt -> Snapshot
  - waehrend Drag keine destruktive auto-Undo-Kaskade
  - Commit am Ende nur wenn loesbar
  - sonst genau ein klarer Rollback + klare Fehlermeldung
- Kein Spam `Undo performed` waehrend normaler Nutzerinteraktion.

### C) Arc-3-Point Correctness (P0)
- Arc muss durch die drei Eingabepunkte fachlich korrekt bestimmt werden.
- Sonderfaelle (kollinear/nahe kollinear) sauber behandeln und erklaeren.

### D) No Silent Geometry Deletion (P0)
- Entferne oder entschärfe jede Logik, die Nutzer-Linien/Rechteckkanten ohne expliziten Befehl entfernt.
- Falls Konsolidierung/Heilung existiert: nur opt-in oder explizit bestaetigt.

### E) Constraint Edit Wirksamkeit (P0)
- Ellipse/Langloch/Polygon/Arc/Line: Constraint-Aenderung muss Geometrie sichtbar und korrekt aktualisieren.
- Wenn Constraint nicht loesbar: verständliche Ursache + Handlungsempfehlung.

### F) Object-Level Drag Semantics (P0)
- Drag an Ellipse/objektbezogenen Handles muss konsistent aufs Gesamtobjekt wirken.
- Handle-Bedeutung muss eindeutig (move/resize/rotate) und stabil sein.

### G) Spline Finalization (P0)
- ESC/Rechtsklick beendet Eingabe sauber und **behaelt** gueltige Spline.
- Nur unvollstaendige/invalid Inputs werden verworfen, nicht fertige Kurven.

### H) Polygon Constraint Startup (P0)
- Polygon darf nicht sofort in unloesbaren Zustand starten.
- Initiale Constraints nur minimal und loesbar setzen.

## Pflicht-Validierung (technisch)
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/sketch_renderer.py gui/sketch_feedback.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_sketch_product_leaps_w32.py test/test_line_direct_manipulation_w30.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

## Pflicht-Validierung (fachlich/manuell) - MUSS dokumentiert werden
Fuehre alle 8 Szenarien manuell aus und dokumentiere pass/fail:
1. 2D Drift reproduzieren -> mit neuer Origin/Fit-Funktion sofort recover.
2. Linie zeichnen, Endpunkt mehrfach ziehen -> keine Undo-Kaskade, stabil editierbar.
3. 3-Punkt-Arc zeichnen -> Arc geht durch alle 3 Punkte.
4. Rechteck + Zusatzlinien -> keine auto-geloeschten Linien.
5. Ellipse/Langloch Constraint editieren -> Geometrie aendert sich sichtbar korrekt.
6. Ellipse draggen -> erwartete Objekt-Semantik (move/resize) ohne Teilobjekt-Fehler.
7. Spline zeichnen + ESC/Rechtsklick -> Spline bleibt bestehen.
8. Polygon erstellen -> kein sofortiger Constraint-Kollaps.

## Deliverable
Datei: `handoffs/HANDOFF_20260218_ai_largeAF_w33_2d_sketch_mode_repair.md`

Format:
1. Problem
2. Root Cause je Bug (1-8)
3. API/Behavior Contract
4. Implementierte Fixes (Datei+Funktion)
5. Validation
   - Commands + exakte Resultate
   - Manueller 8-Punkte-Abnahmebericht (PASS/FAIL je Punkt)
6. Rest-Risiken
7. Naechste 3 priorisierte Aufgaben

## Abnahme-Kriterium
Abnahme nur bei:
- Alle technischen Pflichttests gruen
- Alle 8 manuellen Szenarien PASS
- Keine neuen Skips/Xfails
- Keine Regression bei bestehender Abort/Hint-Basis
