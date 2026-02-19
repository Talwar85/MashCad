Du bist `AI-LARGE-G-STABILIZATION` auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollstaendig:
- `handoffs/HANDOFF_20260217_ai_largeE_w26_projection_hooks.md`
- `handoffs/HANDOFF_20260217_ai_largeE_w26_recovery_hardgate.md`
- `roadmap_ctp/05_release_gates_and_quality_model.md`

## Kritischer Ist-Stand (bereits verifiziert)
Die letzte Lieferung ist NICHT abnahmefaehig. Aktuelle harte Befunde:
1. `gui/sketch_editor.py` ist im Worktree stark verkuerzt/kaputt (tausende Zeilen fehlen), dadurch fehlen Kernmethoden.
2. MainWindow-Init bricht: `AttributeError: 'SketchEditor' object has no attribute '_on_solver_finished'`.
3. Projection-Hooks sind nur definiert, nicht end-to-end verdrahtet:
- keine Emission im echten PROJECT-Flow,
- keine Connection in `main_window.py` zu Preview-Handlern,
- API-Mismatch-Risiko zu `viewport_pyvista.show_projection_preview(edges, target_plane)`.
4. `test/test_projection_trace_workflow_w26.py` ist nicht belastbar (Mock-lastig, keine echte Integration).
5. UI-Gate ist BLOCKED.

## Mission
Liefere ein STABILIZATION PACK, das den Sketch/Projection-Stack wieder releasefaehig macht.

## Harte Regeln
1. Keine Analyse-only Abgabe.
2. Kein `skip`/`xfail`, kein Abschwaechen von Assertions.
3. Keine Placeholders/TODO-Fixes.
4. Keine Edits in:
- `modeling/**`
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
5. Keine Git-History-Operationen (`reset --hard`, rebase, force-push).
6. Wenn Tests rot sind: fixen und erneut laufen lassen.

## Erlaubter Scope
- `gui/sketch_editor.py`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `test/test_projection_trace_workflow_w26.py`
- optional weitere relevante Tests unter `test/**` fuer Stabilisierung
- optional kurzer Statusreport in `roadmap_ctp/**`

## Aufgaben

### Task 0 (P0): SketchEditor wiederherstellen
Ziel: Vollstaendige, lauffaehige Klasse wiederherstellen.

Pflicht:
1. `SketchEditor` darf nicht trunkieren oder Kernmethoden verlieren.
2. `_on_solver_finished` muss wieder vorhanden und korrekt verbunden sein.
3. Basale Methoden muessen wieder existieren:
- `mouseMoveEvent`
- `mousePressEvent`
- `_find_reference_edge_at`
- `_handle_escape_logic`
4. Ergebnis: MainWindow darf beim Erzeugen von `SketchEditor()` nicht crashen.


### Task 1 (P0): Projection-Preview end-to-end verdrahten
Ziel: Echter W26-Workflow statt nur Signal-Deklaration.

Pflicht:
1. Im PROJECT-Tool bei Hover-Kantenwechsel Signal emittieren.
2. Bei Edge-Verlust / Confirm / Cancel / Toolwechsel / Sketch-Ende clear emittieren.
3. Keine Duplicate-Emission bei unveraenderter Kante.
4. In `main_window.py` Signal-Connection herstellen.
5. Adapter bauen, damit Signal-Format zu `viewport_pyvista.show_projection_preview(edges, target_plane)` passt.

Hinweis:
- Wenn Signal `(edge_tuple, projection_type)` emittiert wird, muss daraus in MainWindow ein `edges`-Array gebaut werden, das der Viewport versteht.

### Task 2 (P1): W26-Testdatei verhaerten
Ziel: Reale, belastbare Tests statt nur Mock-Attr-Checks.

Pflicht:
1. `test/test_projection_trace_workflow_w26.py` muss lauffaehig sein.
2. Keine reine Mock-Parallelwelt ohne Relevanz zur echten Pipeline.
3. Mindestabdeckung:
- Projection preview behavior (>= 6 Assertions)
- Trace/project workflow behavior (>= 5 Assertions)
- Abort/state cleanup behavior (>= 3 Assertions)
4. Tests muessen echte Verhaltensaenderung nachweisen (nicht nur `hasattr`).

### Task 3 (P0): Gate-Stabilisierung pruefen
Ziel: Nachweis, dass die Reparatur wirkt.

Pflicht:
1. Fruehe Fast-Checks gruen.
2. Relevante UI/Sketch-Suiten gruen.
3. UI-Gate nicht mehr durch `SketchEditor`-Init-Error blockiert.

## Pflicht-Validierung (exakt ausfuehren)
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/main_window.py gui/viewport_pyvista.py test/test_projection_trace_workflow_w26.py

conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py -v
conda run -n cad_env python -m pytest -q test/test_workflow_product_leaps_w25.py -v
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -v
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile smoke
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile core_quick
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

## Nachweispflicht im Handoff
Du musst liefern:
1. Geaenderte Dateien + warum.
2. Commit-Hash + Message.
3. Exakte Testkommandos + echte Zahlen.
4. Grep-Nachweis:
- Emissionsstellen von `projection_preview_requested.emit` und `projection_preview_cleared.emit`
- Connect-Stellen in `main_window.py`
- Aufrufstellen von `show_projection_preview(` (nicht nur Definition)
- Existenz von `_on_solver_finished` in `gui/sketch_editor.py`
5. Rest-Risiken klar und konkret.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeG_w26_stabilization.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

Wenn etwas nicht geht: konkret mit Datei/Zeile/Exception begruenden.
