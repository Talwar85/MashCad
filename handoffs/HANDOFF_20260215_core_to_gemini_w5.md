# HANDOFF_20260215_core_to_gemini_w5

**Date:** 2026-02-15  
**From:** Codex (Core/KERNEL)  
**To:** Gemini (UX/WORKFLOW)  
**ID:** core_to_gemini_w5

## Problem
Core hat weitere P0-Härtung nachgezogen:
- `PI-005` Edit-Robustheit für Kernfeatures jetzt als Regressionstests abgedeckt.
- `PI-007` Persistenz-Roundtrip für nachgelagerte Feature-Edits (Fillet/Chamfer/Shell) zusätzlich abgesichert.

Die bereits gemeldeten UI-Blocker aus `HANDOFF_20260215_core_to_gemini_w4.md` bleiben inhaltlich bestehen.

## API/Behavior Contract
Keine neuen Error-Codes oder Envelope-Felder gegenüber W3/W4.

Neu abgesicherte Verhaltensgarantien (tests):
- Feature-Edit-Zyklen bleiben robust über `invalid -> recover -> rebuild` für:
  - Extrude, Fillet, Chamfer, Hole, Draft, Shell
- Save/Load-Roundtrip bleibt referenzstabil, wenn danach folgende Feature-Parameter editiert und rebuilt werden:
  - Fillet `radius`
  - Chamfer `distance`
  - Shell `thickness`

## Impact
Neue/erweiterte Core-Tests:
- `test/test_feature_edit_robustness.py` (neu)
- `test/test_project_roundtrip_persistence.py` (erweitert)

UI-seitig keine neuen Pflichtanpassungen durch API-Änderung.

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_edit_robustness.py
conda run -n cad_env python -m pytest -q test/test_project_roundtrip_persistence.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
```

Resultat:
- `214 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- UI-Blocker aus W4 (Right-Click Abort/Selection in Viewport) weiterhin offen bis Gemini-Fix.
