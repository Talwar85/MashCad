Du bist `AI-LARGE-M-WORKFLOW` auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260217_ai_largeM_w28_mainwindow_viewport_workflow_megapack.md`
- `handoffs/HANDOFF_20260217_ai_largeJ_w28_browser_recovery_megapack.md`

## Ziel
W29 Workflow E2E Closeout: MainWindow/Viewport Integrationsluecken schliessen und echte End-to-End-Flows haerten.

## Harte Regeln
1. Kein `skip`/`xfail`.
2. Keine Analyse-only Lieferung.
3. Keine Edits ausserhalb Scope.

## Scope
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `test/test_main_window_w26_integration.py`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_discoverability_hints_w17.py`

## NO-GO
- `gui/sketch_editor.py`
- `gui/browser.py`
- `gui/widgets/**`
- `modeling/**`
- `scripts/**`

## Aufgaben
### 1) Browser-Batch Integration E2E
- Falls Browser-Signale fuer batch focus/unhide existieren: in MainWindow robuste Handler anbinden.
- Kein Leak oder stale state nach Batch-Aktion.

### 2) Abort-Parity Real-Flow
- Escape und Right-Click parity fuer echte Interaktionsketten.
- Priority stack behavior mit reproduzierbaren Tests absichern.

### 3) Discoverability UX
- Hinweise fuer Rotate und Space-Peek klar, kontextsensitiv, ohne spam.
- Tooltip/HUD Verhalten bei schnellen Kontextwechseln stabil.

### 4) Stabiler Testmodus
- Tests sollen in Headless-Umgebung reproduzierbar bleiben (z.B. QT_OPENGL software nur testseitig).

## Pflicht-Validierung
```powershell
$env:QT_OPENGL='software'
conda run -n cad_env python -m py_compile gui/main_window.py gui/viewport_pyvista.py test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py -v
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py -v
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
```

## Abgabe
Datei:
- `handoffs/HANDOFF_20260217_ai_largeM_w29_workflow_e2e_closeout.md`

Pflichtinhalte:
1. Geaenderte Dateien + Grund
2. E2E-Flows (vorher/nachher)
3. Testergebnisse
4. Restrisiken

