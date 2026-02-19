Du bist `AI-LARGE-M-WORKFLOW` auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses W28 MainWindow/Viewport Workflow Megapack.
Fokus: robuste Moduswechsel, Discoverability, klare Abort-Parity, weniger Actor-Leaks.

## Harte Regeln
1. Keine Analyse-only Lieferung.
2. Kein `skip`/`xfail` als Ausweg.
3. Kein Edit ausserhalb Scope.
4. Keine Placeholders.
5. Keine Git-History-Manipulation.

## Erlaubter Scope
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `test/test_main_window_w26_integration.py`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_discoverability_hints_w17.py`
- `test/harness/test_interaction_consistency.py`
- optionale workflow-tests unter `test/`

## NO-GO
- `gui/sketch_editor.py`
- `gui/browser.py`
- `gui/widgets/**`
- `modeling/**`
- `scripts/**`

## Arbeitspaket
### Task 1: Mode-Transition Integrity
Haerte Transition-Pfade:
1. 3d -> sketch
2. sketch -> 3d
3. component switch
4. sketch exit while transient previews active

Pflicht:
- kein preview/actor leak
- keine stale selection states
- klare status messages

### Task 2: Abort-Parity Global
Sicherstellen:
1. Escape und Right-Click ins Leere sind semantisch gleich.
2. Prioritaetsstack bleibt konsistent (drag > dialog > tool > selection > idle).
3. Keine regressions bei panel/dialog focus.

### Task 3: Discoverability Product Leap
Verbessere Sichtbarkeit fuer:
1. rotate controls in sketch mode
2. space-peek hint
3. projection/trace hints auf workflow-ebene

Pflicht:
- Hinweise sind kontextsensitiv.
- Keine Hint-Spam (cooldown/priority).

### Task 4: Integration Tests
Mindestens 25 neue Assertions:
1. mode transition cleanup
2. abort parity
3. discoverability hints
4. integration around main window workflow entry points

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/main_window.py gui/viewport_pyvista.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py -v
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py -v
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -v
```

## Nachweispflicht
1. Geaenderte Dateien + Begruendung.
2. Cleanup-Matrix fuer alle Modewechsel.
3. Testresultate mit Zahlen.
4. Offene Restrisiken.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeM_w28_mainwindow_viewport_workflow_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

