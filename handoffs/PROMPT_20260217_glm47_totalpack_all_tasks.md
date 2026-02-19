Du bist GLM 4.7 (Primary Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies vor Start (Pflicht):
- `handoffs/HANDOFF_20260216_glm47_w19_w20_unified_sprint.md`
- `handoffs/HANDOFF_20260216_altki_w21_product_leaps_hardline.md`
- `handoffs/HANDOFF_20260216_codex_validation_complete.md`
- `handoffs/PROMPT_20260217_glm47_masterpack_all_tasks.md`
- `roadmap_ctp/03_workstreams_masterplan.md`
- `roadmap_ctp/04_workpackage_backlog.md`
- `roadmap_ctp/ROADMAP_STATUS_20260216_codex.md`

-------------------------------------------------------------------------------
MISSION: ONE-PROMPT TOTAL DELIVERY (W19 + W20 + W21 + Recovery)
-------------------------------------------------------------------------------
Du bekommst ALLE offenen Aufgaben in einem Paket.
Keine Aufteilung auf weitere KIs.
Ziel ist nicht nur Test-Gruen, sondern sichtbare Produktverbesserung.

Gesamtpunkte: 140
Mindestabnahme: 95/140
Ziel: 115+/140

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth
- Nur `feature/v1-ux-aiB`.

2) No-Go Dateien
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) Claim Policy
- Kein "done" ohne Dateidiff + reproduzierbaren Command-Output.
- Keine "manuell getestet" Aussage als Ersatz fuer automatisierte Nachweise.

4) Skip/Xfail Policy
- Keine neuen skip/xfail in neuen Tests.
- Bestehende Skips nur mit harter technischer Begruendung + Repro.
- UI-Gateway darf NICHT wegen Timeout geskippt werden.

5) Delivery Policy
- Nur grosse Chunks: mindestens 3 WPs wirklich abschliessen.
- Kein Handoff unter 95/140 Punkten.

-------------------------------------------------------------------------------
WORKPACKAGES (ALLE PFLICHT)
-------------------------------------------------------------------------------
WP-A (25): W21 Browser Recovery + Product Leap
Dateien:
- `gui/browser.py`
- `test/test_browser_product_leap_w21.py`

Muss liefern:
1. Type-robuste Browser-Renderpfade (keine Mock-Compare TypeErrors).
2. Filter (`all/errors/warnings/blocked`) korrekt inkl. Badge-Counts.
3. Keyboard-Navigation zu Problem-Items stabil (Ctrl+N/P/Ctrl+Up/Down).
4. Refresh ohne Flackern, ohne state-loss.

Abnahme:
`conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py -v`
Erwartung: gruen, keine errors.

WP-B (20): W21 Feature Detail Panel Recovery
Dateien:
- `gui/widgets/feature_detail_panel.py`
- `test/test_feature_detail_panel_w21.py`

Muss liefern:
1. Diagnostik-Section robust fuer echte und gemockte Inputs.
2. Copy-Diagnostics stabil (Clipboard-Pfad + Fallback).
3. TNP/Edge-Darstellung ohne Absturz bei partiellen Daten.
4. Kritische Fehler visuell priorisiert (Error UX v2 konsistent).

Abnahme:
`conda run -n cad_env python -m pytest -q test/test_feature_detail_panel_w21.py -v`

WP-C (15): W21 Operation Summary Recovery
Dateien:
- `gui/widgets/operation_summary.py`
- `test/test_operation_summary_w21.py`

Muss liefern:
1. Status-Farbzuordnung strikt nach Prioritaet: status_class > severity > level.
2. Robuste Darstellung auch bei unvollstaendigem payload.
3. Keine TypeErrors bei geometry_delta/status_message edge cases.

Abnahme:
`conda run -n cad_env python -m pytest -q test/test_operation_summary_w21.py -v`

WP-D (15): W21 Notification Manager Stabilitaet
Dateien:
- `gui/managers/notification_manager.py`
- `test/test_notification_manager_w21.py`
- optional `gui/widgets/notification.py`

Muss liefern:
1. Dedup-Fenster (5s) stabil und nachvollziehbar testbar.
2. Priority Queue inkl. pinned/critical ordering reproduzierbar.
3. Burst-Faelle ohne Animation overlap / race.
4. Kompatibilitaet zu `test/test_error_ux_v2_integration.py` erhalten.

Abnahme:
`conda run -n cad_env python -m pytest -q test/test_notification_manager_w21.py test/test_error_ux_v2_integration.py -v`

WP-E (25): Direct Manipulation Closure (W19/W20 Rest)
Dateien:
- `gui/sketch_editor.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/harness/test_interaction_consistency.py`
- optional `test/test_ui_abort_logic.py`

Muss liefern:
1. Arc Direct Edit (center/radius/start/end) belastbar abschliessen.
2. Ellipse/Rectangle/Line drag-resize parity weiterziehen (sichtbares UX-Delta).
3. Escape/Right-Click Abort-Contracts in allen direkten Drag-Modi konsistent.
4. Harness darf nicht als "collected aber komplett skipped" durchgehen.

Abnahme:
`conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py test/harness/test_interaction_consistency.py test/test_ui_abort_logic.py -v`

WP-F (10): Export/Feature Controller Testqualitaet
Dateien:
- `test/test_export_controller.py`
- `test/test_feature_controller.py`
- optional `gui/export_controller.py`

Muss liefern:
1. Kein reines Mock-Theater: Tests muessen public behavior belegen.
2. Keine stillen regressions durch zu lockere assertions.
3. Bestehende gruenen Pfade stabil halten.

Abnahme:
`conda run -n cad_env python -m pytest -q test/test_export_controller.py test/test_feature_controller.py -v`

WP-G (20): Discoverability + User Guidance v2 (sichtbarer Product Leap)
Dateien:
- `gui/sketch_editor.py`
- `gui/main_window.py` (nur wenn zwingend)
- `test/test_discoverability_hints.py`
- `test/test_discoverability_hints_w17.py`

Muss liefern:
1. Klar sichtbare Hinweise fuer Rotate + Peek (Space) im 2D-Modus.
2. Hint-Cooldown/Anti-spam weiterhin robust.
3. Behavior-proof Tests fuer die sichtbaren Hinweise.

Abnahme:
`conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v`

WP-H (10): Gate + Evidence Hardline (No Skip)
Dateien:
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`

Muss liefern:
1. Einheitliche Marker fuer dieses Gesamtpaket.
2. Retry-Strategie dokumentiert und genutzt, falls Gate timeoutet.
3. Evidence-Dateien konsistent, nachvollziehbar, mit Zeitstempel.

Abnahme:
`powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1`
`powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W22_TOTALPACK_20260217`

-------------------------------------------------------------------------------
EMPFOHLENE LAUFREIHENFOLGE (ANTI-TIMEOUT)
-------------------------------------------------------------------------------
1) Quick shards
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py test/test_feature_detail_panel_w21.py -v
conda run -n cad_env python -m pytest -q test/test_operation_summary_w21.py test/test_notification_manager_w21.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py test/harness/test_interaction_consistency.py -v
```

2) Mid-pack suite
```powershell
conda run -n cad_env python -m pytest -q test/test_export_controller.py test/test_feature_controller.py test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
```

3) Pflicht: Full master validation
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py test/test_feature_detail_panel_w21.py test/test_operation_summary_w21.py test/test_notification_manager_w21.py test/test_feature_controller.py test/test_export_controller.py test/test_discoverability_hints.py test/test_discoverability_hints_w17.py test/harness/test_interaction_direct_manipulation_w17.py test/harness/test_interaction_consistency.py test/test_error_ux_v2_integration.py test/test_error_ux_v2_e2e.py -v
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W22_TOTALPACK_20260217
```

Timeout-Regel:
Wenn `gate_ui.ps1` timeoutet, sofort Retry mit Logdatei, danach final erneut Gate starten:
```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1 *>&1 | Tee-Object -FilePath "roadmap_ctp/_w22_gate_retry_$ts.log"
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT (STRICT)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260217_glm47_totalpack_all_tasks.md`

Pflichtstruktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (mit echten Outputs)
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard
7. Claim-vs-Proof Matrix
8. Product Change Log (user-facing, Pflicht)
9. Offene Punkte + naechste 10 Aufgaben

Pflicht-Scorecard:
| WP | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|----|--------|-------------------------------|-------|
| A | 25 | ... | ... |
| B | 20 | ... | ... |
| C | 15 | ... | ... |
| D | 15 | ... | ... |
| E | 25 | ... | ... |
| F | 10 | ... | ... |
| G | 20 | ... | ... |
| H | 10 | ... | ... |
| Total | 140 | ... | ... |
| Completion Ratio | X/140 = YY% | MUSS >= 95/140 | |

No-Go:
- Completion < 95/140
- Gate skipped / kein verwertbares Gate-Ergebnis
- "DONE" ohne Diff + Command-Proof
- Neue skip/xfail ohne harte technische Begruendung
