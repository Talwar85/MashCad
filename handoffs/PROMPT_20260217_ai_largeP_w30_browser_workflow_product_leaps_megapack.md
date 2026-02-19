# PROMPT_20260217_ai_largeP_w30_browser_workflow_product_leaps_megapack

Du bist AI-LargeP auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere große, sichtbare Workflow-Leaps im Browser/MainWindow/Viewport-Zusammenspiel: weniger Klicks, klarere Recovery-Entscheidungen, robustere Massenaktionen.

## Pflicht-Read
- `handoffs/HANDOFF_20260217_ai_largeJ_w29_browser_recovery_closeout.md`
- `handoffs/HANDOFF_20260217_ai_largeM_w29_workflow_e2e_closeout.md`
- `handoffs/HANDOFF_20260217_ai_largeK_w29_release_ops_timeoutproof.md`

## Harte Grenzen
1. Keine Edits in:
- `modeling/**`
- `gui/sketch_editor.py`
- `scripts/**`

2. Fokus auf:
- `gui/browser.py`
- `gui/main_window.py`
- `gui/widgets/feature_detail_panel.py`
- optional `gui/viewport_pyvista.py` (nur für Fokus-/Highlight-Pfade)
- Tests: `test/test_browser_product_leap_w26.py`, `test/test_feature_detail_recovery_w26.py`, `test/test_main_window_w26_integration.py`

3. Verboten:
- Reine Text-/Tooltip-Änderungen ohne Workflow-Mehrwert
- Batch-Aktionen ohne Schutz gegen Mischselektion/Hidden-State

## Zielbild (DoD)
- Batch-Recovery ist ein schneller, sicherer Flow (Multi-Select -> Aktion -> eindeutiges Feedback -> konsistenter Zustand).
- Feature-Detail-Recovery zeigt nicht nur Buttons, sondern priorisierte nächste Schritte je Fehlerklasse.
- Browser/MainWindow-Events sind robust bei Filterwechsel, Hidden Bodies und teilweise ungültigen Selektionen.

## Arbeitspakete
### AP1: Recovery Decision Engine UX
- In `FeatureDetailPanel`: priorisierte Action-Empfehlung pro Error-Code (`tnp_ref_missing`, `tnp_ref_mismatch`, `tnp_ref_drift`, `rebuild_finalize_failed`, `ocp_api_unavailable`).
- Primäraktion visuell hervorheben, Sekundäraktionen klar markieren.
- Fehlerspezifische Erklärung + unmittelbarer Next-Step.

### AP2: Batch Recovery Orchestration
- In `ProjectBrowser` und `MainWindow`:
  - Batch-Rebuild, Batch-Diagnostics, Batch-Unhide, Batch-Focus in konsistentem Ablauf.
  - Teilerfolge/Teilfehler sauber berichten (nicht nur "done").
  - Selektion nach Aktion bereinigen (kein stale Batch-State).

### AP3: Workflow-Leap "Recover & Focus"
- Neue kombinierte Aktion: problematische Features sammeln -> betroffene Bodies sichtbar machen -> Viewport-Fokus -> Detailpanel öffnen.
- Muss bei leeren/inkonsistenten Inputs stabil no-op mit sinnvoller Meldung bleiben.

### AP4: Filter/Selection Robustness
- Harte Guards gegen Mischselektion, Hidden-Only-Selection, gelöschte Referenzen in laufender Session.
- Keine toten Menüpunkte, keine stillen Fehler.

### AP5: E2E-Tests mit Wert
- Erweiterte Integrations-/Workflow-Tests für reale Sequenzen, nicht nur Unit-Mocks.
- Mindestens 25 zusätzliche Assertions über Browser/MainWindow/DetailPanel-Zusammenspiel.

## Pflicht-Validierung
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m py_compile gui/browser.py gui/main_window.py gui/widgets/feature_detail_panel.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py
```

## Rückgabeformat
Erzeuge:
- `handoffs/HANDOFF_20260217_ai_largeP_w30_browser_workflow_product_leaps_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Produkt-Delta (vorher/nachher)
7. Nächste 5 Folgeaufgaben

## Qualitätslatte
- Kein "nur kosmetisch".
- Jeder neue Flow braucht mindestens einen E2E-Testpfad.
- Alle neuen Aktionen müssen safe-fail und idempotent sein.
