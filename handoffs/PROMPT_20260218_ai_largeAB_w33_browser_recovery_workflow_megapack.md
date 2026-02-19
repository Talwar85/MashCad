# PROMPT_20260218_ai_largeAB_w33_browser_recovery_workflow_megapack

Du bist AI-LARGE-AB (Browser + Recovery Workflow Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere ein grosses Workflow- und Recovery-Paket ausserhalb des Sketch-Kerns:
1. bessere Problemnavigation im Browser,
2. praezisere Recovery-Steuerung,
3. stabile Batch-Aktionen ohne stale states.

## Scope
Erlaubte Dateien:
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/main_window.py` (nur workflow/recovery wiring)
- `gui/widgets/status_bar.py` (nur recovery status feedback)
- `test/test_browser_product_leap_w26.py`
- `test/test_feature_detail_recovery_w26.py`
- `test/test_main_window_w26_integration.py`
- neue Tests unter `test/` nach Bedarf

No-Go:
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `modeling/**`
- `scripts/**`

## Harte Regeln
1. Keine neuen `skip` oder `xfail`.
2. Keine Testabsenkung durch weichere Assertions.
3. Keine `.bak` oder `temp_*` Dateien erzeugen.
4. Batch-Funktionen muessen echte Datenpfade abdecken, keine no-op Showcases.

## EPIC AB1 - Recovery Decision Engine v2 (P0)
Ziel: Recovery-Aktionen je Error-Code sind klar priorisiert und nachvollziehbar.

Aufgaben:
1. Decision-Mapping fuer alle Pflichtcodes robust halten:
- `tnp_ref_missing`
- `tnp_ref_mismatch`
- `tnp_ref_drift`
- `rebuild_finalize_failed`
- `ocp_api_unavailable`
2. Primaraktion + Sekundaeraktionen eindeutig visualisieren.
3. Next-Step-Hinweis im FeatureDetail konsistent anzeigen.

## EPIC AB2 - Batch Recovery Orchestration (P0)
Ziel: Batch-Aktionen sind robust bei Mischselektion und hidden states.

Aufgaben:
1. Guard-Logik fuer invalide Selektion haerten.
2. `recover_and_focus_selected` fuer edge-cases stabilisieren:
- leere Selektion
- hidden-only
- gemischte Typen
3. Nach Batch-Aktion stale selections sicher bereinigen.

## EPIC AB3 - Problem-First Navigation Leap (P1)
Ziel: Nutzer navigiert schnell durch kritische Probleme.

Aufgaben:
1. Priorisierung kritisch > blocked > error > warning validieren.
2. Tastaturpfade stabil halten (next/prev problem).
3. Visuelles Feedback im Browser verbessern, wenn Fokus springt.

## EPIC AB4 - Workflow Sync mit MainWindow (P1)
Ziel: Browser-Aktionen triggern robuste UI-Orchestrierung.

Aufgaben:
1. Feature-Detail-Selection und Viewport-Fokus bleiben synchron.
2. Keine ghost highlights nach recovery/focus.
3. Status-Bar meldet Recovery-Resultat konsistent.

## Testpflicht
Mindestens folgende Beweise liefern:
1. Alle 5 Error-Codes haben verifizierte Action-Mappings.
2. Batch-Recovery failt kontrolliert bei invalider Selektion.
3. Recover-and-focus Verhalten mit echten Tree-Selektionen.
4. MainWindow Integration bleibt stabil.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/browser.py gui/widgets/feature_detail_panel.py gui/main_window.py gui/widgets/status_bar.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate
```

## Akzeptanzkriterien
1. Mindestens 2 sichtbare Browser/Recovery UX-Verbesserungen.
2. Keine neuen skips/xfails.
3. Keine Regression in MainWindow Integration.
4. Pflichtvalidierung komplett gruen.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeAB_w33_browser_recovery_workflow_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
