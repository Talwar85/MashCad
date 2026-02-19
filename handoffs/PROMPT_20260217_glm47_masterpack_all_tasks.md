Du bist GLM 4.7 (Master Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies vor Start:
- `handoffs/HANDOFF_20260216_glm47_w19_w20_unified_sprint.md`
- `handoffs/HANDOFF_20260216_altki_w21_product_leaps_hardline.md`
- `handoffs/PROMPT_20260216_glm47_w19_w20_unified_sprint.md`
- `handoffs/PROMPT_20260216_altki_w21_product_leaps_hardline.md`

Kontext:
Alle offenen Aufgaben werden jetzt in EINEM Paket an dich uebergeben.
Es gibt keine Aufteilung mehr auf zweite KI.

-------------------------------------------------------------------------------
MISSION: MASTERPACK ALL TASKS (W19 + W20 + W21)
-------------------------------------------------------------------------------
Ziel:
1. W21-Fehler reparieren (aktuell nicht abnahmefaehig).
2. W19/W20-Restarbeiten auf belastbaren Zustand bringen (nicht nur skip).
3. Sichtbare Product-Leaps liefern, nicht nur Test-Umbauten.
4. Abschliessend UI-Gate + Evidence gruener Nachweis.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth:
- Nur `feature/v1-ux-aiB`.

2) No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) No fake done:
- Kein "DONE" ohne Dateidiff + reproduzierbaren Command-Output.
- Keine manuell-verifiziert-Claims als Ersatz fuer automatisierte Proofs.

4) Skip/xfail Policy:
- In neu hinzugefuegten Tests: kein skip/xfail.
- Bestehende skips nur wenn technisch zwingend und im Handoff explizit belegt.

5) Gateway Policy:
- `scripts/gate_ui.ps1` darf nicht geskippt werden.
- Timeout/infra issue -> fix/retry -> finales verwertbares Gate-Ergebnis.

-------------------------------------------------------------------------------
ARBEITSPAKETE (ALLE PFLICHT)
-------------------------------------------------------------------------------
Gesamt: 100 Punkte
Mindestabnahme: 70/100
Ziel: 85+/100

WP-A (25 Punkte): W21 Browser/Product-Surface Recovery
Betroffene Dateien:
- `gui/browser.py`
- `test/test_browser_product_leap_w21.py`

Fix-Ziele:
1. Mock-robuste Browser-Logik (keine TypeErrors bei mock volume/status data).
2. Filter, Badge, Navigation real funktionsfaehig.
3. Tests auf behavior-proof trimmen, nicht fragile mock-overreach.

Akzeptanz:
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py -v
```
Erwartung: gruen (0 fails, 0 errors).

WP-B (20 Punkte): W21 Feature Detail / Operation Summary Recovery
Betroffene Dateien:
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `test/test_feature_detail_panel_w21.py`
- `test/test_operation_summary_w21.py`

Fix-Ziele:
1. Typrobustheit fuer mock/real input (status_message, geometry_delta, edges_total).
2. API-Kompatibilitaet in Tests und Widgets angleichen.
3. Error UX v2 Mapping bleibt konsistent und testbar.

Akzeptanz:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_detail_panel_w21.py test/test_operation_summary_w21.py -v
```
Erwartung: gruen.

WP-C (15 Punkte): W21 Notification Robustness Stabilisieren
Betroffene Dateien:
- `gui/managers/notification_manager.py`
- `test/test_notification_manager_w21.py`
- optional `gui/widgets/notification.py`

Fix-Ziele:
1. Dedup/Priority/Queue Verhalten ohne Regressionsrisiko.
2. Animation-Koordination stabil unter Burst.
3. Keine API-Breaks fuer bestehende Notification-Aufrufe.

Akzeptanz:
```powershell
conda run -n cad_env python -m pytest -q test/test_notification_manager_w21.py test/test_error_ux_v2_integration.py -v
```
Erwartung: gruen.

WP-D (20 Punkte): W19/W20 Direct Manipulation Real-Closure
Betroffene Dateien:
- `gui/sketch_editor.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/harness/test_interaction_consistency.py`

Fix-Ziele:
1. Direct-manip harness darf nicht rein skipped sein.
2. Arc direct edit (center/radius/start/end) real testbar und reproduzierbar.
3. Keine 0-item / pseudo-pass Konstellation.

Akzeptanz:
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py test/harness/test_interaction_consistency.py -v
```
Erwartung: collected > 0 und nicht komplett skip.

WP-E (10 Punkte): Export Controller Test-Qualitaet absichern
Betroffene Dateien:
- `test/test_export_controller.py`
- optional `gui/export_controller.py`

Fix-Ziele:
1. Keine "nur logik ohne echten flow" Schein-Tests.
2. Public-path behavior testen mit robustem mocking.
3. Keine UI-blocking false positives.

Akzeptanz:
```powershell
conda run -n cad_env python -m pytest -q test/test_export_controller.py test/test_feature_controller.py -v
```
Erwartung: gruen.

WP-F (10 Punkte): Gate/Evidence Endkonsistenz
Betroffene Dateien:
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`

Fix-Ziele:
1. Konsistente W19/W20/W21 Marker (keine Mischstände).
2. Evidence-Metadata und Prefix stimmen zum Masterpack.
3. Gate-Output klar und reproduzierbar.

Akzeptanz:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_MASTERPACK_20260217
```
Erwartung: verwertbarer Output, keine widerspruechlichen Marker.

-------------------------------------------------------------------------------
END-TO-END PFLICHTVALIDIERUNG (AM ENDE)
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py test/test_feature_detail_panel_w21.py test/test_operation_summary_w21.py test/test_notification_manager_w21.py -v

conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py test/test_discoverability_hints_w17.py test/harness/test_interaction_direct_manipulation_w17.py test/test_error_ux_v2_e2e.py -v

conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_error_ux_v2_integration.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_MASTERPACK_20260217
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260217_glm47_masterpack_all_tasks.md`

Pflichtstruktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Scorecard (pro WP)
7. Claim-vs-Proof Matrix
8. Product Change Log (user-facing, Pflicht)
9. Offene Punkte + naechste 8 Aufgaben

-------------------------------------------------------------------------------
SCORECARD (PFLICHT)
-------------------------------------------------------------------------------
| Workpackage | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------------|--------|--------------------------------|-------|
| WP-A | 25 | ... | ... |
| WP-B | 20 | ... | ... |
| WP-C | 15 | ... | ... |
| WP-D | 20 | ... | ... |
| WP-E | 10 | ... | ... |
| WP-F | 10 | ... | ... |
| Total | 100 | ... | ... |
| Completion Ratio | X/100 = YY% | MUST BE >= 70% | |

No-Go:
- Completion Ratio < 70%
- UI gate skipped
- Neue test-skips ohne harte technische Begruendung
- "DONE" claim ohne reproduzierbaren command output
