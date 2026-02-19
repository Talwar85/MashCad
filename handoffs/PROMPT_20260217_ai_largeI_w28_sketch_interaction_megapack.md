Du bist `AI-LARGE-I-SKETCH` auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses W28 Sketch Interaction Megapack mit klar sichtbaren Produktverbesserungen.
Fokus: Direct Manipulation, robuste Projektion/Trace-Interaktion, performantes Drag-Verhalten.

## Harte Regeln
1. Keine Analyse-only Abgabe.
2. Kein `skip`/`xfail` als Problemlosung.
3. Keine Placeholders/TODO statt echter Implementierung.
4. Kein Edit ausserhalb des erlaubten Scopes.
5. Keine Git-History-Eingriffe (kein reset/rebase/force-push).

## Erlaubter Scope (nur diese Bereiche)
- `gui/sketch_editor.py`
- `gui/sketch_snapper.py`
- `test/test_sketch_editor_w26_signals.py`
- `test/test_projection_trace_workflow_w26.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- neue sketch-nahe Tests unter `test/` oder `test/harness/`

## NO-GO (nicht anfassen)
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `gui/browser.py`
- `gui/widgets/**`
- `modeling/**`
- `scripts/**`

## Arbeitspaket
### Task 1: Direct-Manipulation Parity (gross)
Implementiere eine konsistente Handle-Logik fuer:
1. Circle (center/radius)
2. Arc (center/radius/start/end angle)
3. Rectangle-Line-Edges (horizontal/vertical resize)
4. Ellipse (major/minor axis plus center move)
5. Polygon (center move plus vertex drag)

Pflicht:
- Keine widerspruechlichen Cursor-Symbole.
- SHIFT-Achsenlock funktioniert fuer alle linearen Resize-Pfade.
- Rechtsklick ins Leere bricht aktive Drag-Operation robust ab.

### Task 2: Projection/Trace Robustness
Haerte PROJECT/Trace Pfad in `SketchEditor`:
1. Keine Ghost-Preview nach Toolwechsel.
2. Keine Duplicate Emissions bei identischem Hover-Edge.
3. Cleanup bei Cancel, Confirm, Escape, Sketch-Exit.

### Task 3: Drag-Performance Upgrade
Ziel:
- Spuerbar fluessigeres Drag/Resize bei vielen Constraints.

Pflicht:
1. Dirty-Rect Pfade nicht regressieren.
2. Kein Voll-Redraw bei trivialen Hover-Updates.
3. Live-Solve throttling stabil halten (keine event-loop starve).

### Task 4: Test-Hardening
Erweitere Tests mit realen Verhaltensassertions:
1. Mindestens 20 neue Assertions insgesamt.
2. Mindestens 8 Assertions fuer Arc/Ellipse/Polygon Drag.
3. Mindestens 6 Assertions fuer Projection cleanup und no-duplicate behavior.
4. Mindestens 6 Assertions fuer Abbruch- und Cursor-Parity.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_snapper.py test/test_sketch_editor_w26_signals.py test/test_projection_trace_workflow_w26.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py -v
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py -v
```

## Nachweispflicht
1. Liste geaenderter Dateien + Grund.
2. Repro-Schritte fuer vorher/nachher Verhalten.
3. Exakte Testkommandos + Ergebniszahlen.
4. Offene Restrisiken.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeI_w28_sketch_interaction_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

