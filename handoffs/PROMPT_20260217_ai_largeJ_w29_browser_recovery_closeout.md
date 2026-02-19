Du bist `AI-LARGE-J-BROWSER` auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260217_ai_largeJ_w28_browser_recovery_megapack.md`
- `handoffs/HANDOFF_20260217_ai_largeM_w28_mainwindow_viewport_workflow_megapack.md`

## Ziel
W29 Browser Recovery Closeout: Browser/DetailPanel weiter produktreif machen, ohne MainWindow-Code anzufassen.

## Harte Regeln
1. Kein `skip`/`xfail`.
2. Keine Placeholders.
3. Keine Edits ausserhalb Scope.

## Scope
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
- `test/test_browser_product_leap_w26.py`
- `test/test_feature_detail_recovery_w26.py`

## NO-GO
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `gui/sketch_editor.py`
- `modeling/**`
- `scripts/**`

## Aufgaben
### 1) Error Taxonomy UX vervollstaendigen
- Alle 5 Codes (`tnp_ref_missing/mismatch/drift`, `rebuild_finalize_failed`, `ocp_api_unavailable`) muessen in UI klar unterscheiden.
- Jede Darstellung braucht konkrete Next-Action.

### 2) Recovery Action Guards
- Buttons nur aktiv, wenn Aktion technisch sinnvoll ist.
- Deaktivierte Aktionen brauchen klaren Grund im Tooltip.

### 3) Batch UX Polishing
- Batch-Menues nur in passenden Kontexten.
- Selektion/Filterwechsel darf Batch-State nicht korrupt hinterlassen.

### 4) Test-Hardening
- Mindestens 20 zusaetzliche Assertions.
- Fokus auf Rendering + Action Dispatch + Batch-Konsistenz.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/browser.py gui/widgets/feature_detail_panel.py gui/widgets/operation_summary.py gui/managers/notification_manager.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py -v
conda run -n cad_env python -m pytest -q test/test_feature_detail_recovery_w26.py -v
```

## Abgabe
Datei:
- `handoffs/HANDOFF_20260217_ai_largeJ_w29_browser_recovery_closeout.md`

Pflichtinhalte:
1. Geaenderte Dateien + Begruendung
2. Mapping Code -> Message -> Action
3. Testergebnisse
4. Restrisiken

