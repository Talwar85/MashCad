# HANDOFF_20260216_core_to_glm47_w6

**Date:** 2026-02-16
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW)
**ID:** core_to_glm47_w6
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
Der Error-Envelope hatte bisher nur `code` + `next_action`. Fuer UI-Entscheidungen (Error vs Warning vs Blocked) fehlte eine direkte Klassifikation.

## 2. API/Behavior Contract
Ergaenzt in `status_details` (schema `error_envelope_v1`):
- `status_class`
- `severity`

Mapping:
- `tnp_ref_drift`, `fallback_used` -> `status_class=WARNING_RECOVERABLE`, `severity=warning`
- `blocked_by_upstream_error`, `fallback_blocked_strict` -> `status_class=BLOCKED`, `severity=blocked`
- `rebuild_finalize_failed` -> `status_class=CRITICAL`, `severity=critical`
- alle anderen Codes (z. B. `operation_failed`, `ocp_api_unavailable`) -> `status_class=ERROR`, `severity=error`

Zusatz:
- `fallback_used` hat jetzt einen expliziten Default-`next_action` im Envelope.

Kompatibilitaet:
- Kein API-Break; bestehende Felder bleiben unveraendert.

## 3. Impact
Geaenderte Dateien:
- `modeling/__init__.py`
- `test/test_feature_error_status.py`

Neue/erweiterte Regressionen:
- Envelope-Klassifikation fuer `operation_failed`, `ocp_api_unavailable`, `fallback_used`, `tnp_ref_drift`, `blocked_by_upstream_error`, `rebuild_finalize_failed`.

## 4. Validation
Ausgefuehrt:
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py test/test_feature_error_status.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py -k "single_ref_pair"
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultate:
- `test/test_feature_error_status.py`: `12 passed`
- `test/test_tnp_v4_feature_refs.py -k single_ref_pair`: `10 passed`
- Core-Gate erweitert: `250 passed, 2 skipped`

## 5. Breaking Changes / Rest-Risiken
- Kein Breaking Change.
- UI kann sofort optional auf `status_class`/`severity` umstellen (bevorzugt), bleibt aber kompatibel mit reinem `code`-Mapping.
- Rest-Risiko: Falls UI weiterhin nur auf `status`-String schaut, geht der neue Nutzen vorerst verloren, aber Verhalten bricht nicht.
