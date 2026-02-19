Du bist `AI-LARGE-J-BROWSER` auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses W28 Browser/Recovery Megapack mit sichtbaren UX-Leaps.
Fokus: Feature-Transparenz, Recovery-Handlungen, Batch-Workflow.

## Harte Regeln
1. Keine Analyse-only Abgabe.
2. Kein `skip`/`xfail` als Ersatz fuer Fixes.
3. Keine Placeholders.
4. Keine Edits ausserhalb Scope.
5. Keine Git-History-Manipulation.

## Erlaubter Scope
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
- `test/test_browser_product_leap_w26.py`
- `test/test_feature_detail_recovery_w26.py`
- neue browser/recovery Tests unter `test/`

## NO-GO
- `gui/sketch_editor.py`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- `modeling/**`
- `scripts/**`

## Arbeitspaket
### Task 1: Error Taxonomy UX (tnp + dependency)
Baue in Browser/DetailPanel klare Darstellung fuer:
1. `tnp_ref_missing`
2. `tnp_ref_mismatch`
3. `tnp_ref_drift`
4. `rebuild_finalize_failed`
5. `ocp_api_unavailable`

Pflicht:
- Mapping auf konkrete Nutzerhandlung (reselect/edit/rebuild/check deps).
- Kein generisches "operation_failed" als einzige Meldung.

### Task 2: Recovery Console in DetailPanel
Implementiere robuste Recovery-Actions:
1. Reselect reference
2. Open edit flow
3. Rebuild feature
4. Accept drift (nur wenn zulassig)
5. Check dependencies

Pflicht:
- Action-Buttons mit klaren Guards (disabled bei ungueltigem Zustand).
- Ausfuehrliches visuelles Feedback (Status + Notification).

### Task 3: Batch Browser Product Leap
Verbessere Batch-Faehigkeiten:
1. Multi-select auf Features/Bodies stabil.
2. Batch isolate/unhide/focus flows.
3. Gruppierte Fehleransicht mit schnellem Drilldown.

### Task 4: Testausbau
Mindestens 25 neue Assertions:
1. Error-code rendering + badge behavior.
2. Recovery action dispatch.
3. Batch selection + batch action consistency.
4. Notification semantics (success/warn/error/info).

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/browser.py gui/widgets/feature_detail_panel.py gui/widgets/operation_summary.py gui/managers/notification_manager.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py -v
conda run -n cad_env python -m pytest -q test/test_feature_detail_recovery_w26.py -v
```

## Nachweispflicht
1. Geaenderte Dateien + Begruendung.
2. Testresultate mit Pass/Fail-Zahlen.
3. Mapping-Tabelle Code -> User Message -> Next Action.
4. Restrisiken.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeJ_w28_browser_recovery_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

