# PROMPT_20260218_ai_largeAA_w33_sketch_constraints_solver_megapack

Du bist AI-LARGE-AA (Sketch Constraints + Solver Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere ein grosses, sichtbares Sketch-Qualitaetspaket mit Fokus auf:
1. robustes Constraint-Verhalten,
2. klare Solver-Fehlerrueckmeldung,
3. stabile und performante Direct-Edit-Workflows.

## Scope
Erlaubte Dateien:
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `gui/sketch_renderer.py`
- `gui/sketch_feedback.py`
- `test/test_sketch_product_leaps_w32.py`
- `test/test_line_direct_manipulation_w30.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- neue Tests unter `test/` nach Bedarf

No-Go:
- `modeling/**`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `gui/browser.py`

## Harte Regeln
1. Keine neuen `skip` oder `xfail`.
2. Keine bestehenden Assertions abschwaechen.
3. Keine `.bak` oder `temp_*` Dateien erzeugen.
4. Keine Mock-only Testillusionen als Hauptnachweis.
5. Jede UX-Aenderung braucht mindestens einen echten Verhaltenstest.

## EPIC AA1 - Constraint Edit Semantics (P0)
Ziel: Beim Ziehen von Geometrie bleibt das Verhalten konsistent und vorhersagbar.

Aufgaben:
1. Stabilisiere Line/Rectangle/Arc/Ellipse Drag unter Constraints.
2. Bei Konflikt: kein inkonsistenter Zwischenzustand, sauberer Rollback.
3. Ein Drag-Commit soll genau einen Undo-Eintrag erzeugen.
4. Keine stillen Constraint-Verletzungen.

## EPIC AA2 - Solver Feedback Product Leap (P0)
Ziel: Fehlerhinweise sind konkret und handlungsorientiert.

Aufgaben:
1. `format_solver_failure_message` im Sketch-Workflow konsequent nutzen.
2. HUD/Statustext fuer typische Konflikte verbessern:
- over-constrained
- conflicting dimensions
- fixed geometry cannot move
3. Meldungen sollen konkrete Next Action enthalten.

## EPIC AA3 - Direct Edit Handle Reliability (P1)
Ziel: Handle-Auswahl und Drag-Modi sind eindeutig.

Aufgaben:
1. Arc center/radius handle Trennung robust machen.
2. Ellipse active vs idle handles klar trennen, keine Handle-Flut.
3. Polygon vertex drag robust halten, inklusive edge-cases bei kleinem Zoom.

## EPIC AA4 - Interaktionsperformance im Solver-Hotpath (P1)
Ziel: Fluessige Bearbeitung bei vielen Constraints.

Aufgaben:
1. Unnoetige solve/repaint-Aufrufe im Drag-Hotpath reduzieren.
2. Debounce/Throttle dort einsetzen, wo UX-neutral.
3. Final solve bei Drag-Ende erzwingen.

## Testpflicht
Mindestens folgende Bereiche abdecken:
1. Constraint-Rollback bei unloesbarem Drag.
2. Undo-Granularitaet pro Drag-Session.
3. Arc/Ellipse Handle-Picking mit echten Editor-Staenden.
4. Solver-Fehlertext enthaelt nutzbare Hinweise.
5. Keine Regression in bereits gruener Direct-Manipulation Suite.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/sketch_renderer.py gui/sketch_feedback.py
conda run -n cad_env python -m pytest -q test/test_sketch_product_leaps_w32.py
conda run -n cad_env python -m pytest -q test/test_line_direct_manipulation_w30.py test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate
```

## Akzeptanzkriterien
1. Keine neuen skips/xfails in geaenderten Tests.
2. Mindestens 2 sichtbare UX-Verbesserungen im Sketch-Verhalten.
3. Solver-Fehlerrueckmeldung ist klarer als vorher und testbar belegt.
4. Pflichtvalidierung komplett gruener Durchlauf.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeAA_w33_sketch_constraints_solver_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
