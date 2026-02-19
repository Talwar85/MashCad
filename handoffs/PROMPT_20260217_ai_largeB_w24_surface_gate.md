Du bist KI-LARGE-B (Surface Reliability + Gate Cell) auf Branch `feature/v1-ux-aiB`.

MISSION (sehr großes Paket):
Product-Surface Robustheit + Gate/Evidence Konsistenz auf Abnahme-Niveau bringen.

WICHTIG: Dieses Paket DARF sich NICHT mit KI-LARGE-A überschneiden.

ERLAUBTE DATEIEN (nur diese Bereiche):
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
- `test/test_browser_product_leap_w21.py`
- `test/test_feature_detail_panel_w21.py`
- `test/test_operation_summary_w21.py`
- `test/test_notification_manager_w21.py`
- `test/test_error_ux_v2_integration.py`
- `test/test_export_controller.py`
- `test/test_feature_controller.py`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`

NO-GO:
- Kein Edit in `gui/sketch_editor.py`
- Kein Edit in `test/harness/test_interaction_*`
- Kein Edit in `test/test_ui_abort_logic.py`
- Kein Edit in `test/test_discoverability_hints*.py`
- Kein Edit in `modeling/**`

ZIELE:
1) Browser/FeaturePanel/OperationSummary/Notification robust gegen Mock/None/teilweise Payloads.
2) Testzahlen und Handoff-Zahlen müssen exakt zusammenpassen (keine kosmetischen Claims).
3) Error UX v2 Priorität überall gleich: status_class > severity > legacy level.
4) Gate/Evidence konsistent auf W22-Labeling, keine alten W14/W18 Marker mehr.
5) Controller-Tests belastbar halten (keine zu lockeren Assertions).

MINDEST-ABNAHME:
- Alle 6 Ziel-Suiten grün.
- Gate UI ausführbar, Evidence erzeugbar.
- Keine neuen skips/xfails.

PFLICHT-VALIDIERUNG:
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py test/test_feature_detail_panel_w21.py test/test_operation_summary_w21.py test/test_notification_manager_w21.py test/test_export_controller.py test/test_feature_controller.py -v
conda run -n cad_env python -m pytest -q test/test_error_ux_v2_integration.py -v
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W24_LARGEB_20260217
```

RUECKGABE:
- Datei: `handoffs/HANDOFF_20260217_ai_largeB_w24_surface_gate.md`
- Struktur:
  1. Problem
  2. API/Behavior Contract
  3. Impact
  4. Validation (exakte Commands + Zahlen)
  5. Breaking Changes / Rest-Risiken
  6. Scorecard pro Teilbereich
  7. Claim-vs-Proof Matrix
  8. Product Change Log (user-facing)
