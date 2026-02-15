# HANDOFF_20260215_core_to_gemini_w6

**Date:** 2026-02-15  
**From:** Codex (Core/KERNEL)  
**To:** Gemini (UX/WORKFLOW)  
**ID:** core_to_gemini_w6

## Problem
`PI-006` (Rollback-Konsistenz) war in den normalen Feature-Fehlerpfaden unvollständig: `status_details.rollback` wurde bisher nur in speziellen Failsafe-/Self-Heal-Pfaden gesetzt.

## API/Behavior Contract
Neu garantiert:
- Bei Feature-Status `ERROR` enthält `status_details` jetzt konsistent ein `rollback`-Objekt mit:
  - `from`
  - `to`
- Gilt auch für reguläre Operation-Fehler (z. B. Fillet/Chamfer/Hole Fehler), nicht nur für Finalize-Failsafe.

Zusätzlich:
- `blocked_by_upstream_error`-Features enthalten ebenfalls `rollback` (from/to auf den aktuellen stabilen Stand).

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_feature_error_status.py`

Neue Regressionen:
- `test_failed_fillet_exposes_rollback_metrics_in_error_envelope`
- `test_failed_hole_exposes_rollback_metrics_in_error_envelope`

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py -k rollback_metrics
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
```

Resultat:
- Rollback-Subset: `2 passed`
- Gesamt-Core-Suite: `216 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- UI/Tooltips können `status_details.rollback` bei `ERROR` nun verlässlich voraussetzen.
- UI-Interaktionsregressionen aus W4 bleiben separat offen.
