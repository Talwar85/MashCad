# HANDOFF_20260216_core_to_glm47_w7

**Date:** 2026-02-16
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW)
**ID:** core_to_glm47_w7
**Branch:** `feature/v1-ux-aiB`

## Problem
W6 hat bereits `status_class`/`severity` eingefuehrt. Fuer CH-006 mussten OCP-API-Driftfaelle breiter klassifiziert werden (nicht nur direkte `ImportError`).

## API/Behavior Contract
### Error-Envelope Erweiterung (aktiv)
`status_details` enthaelt:
- `status_class` (`ERROR|WARNING_RECOVERABLE|BLOCKED|CRITICAL`)
- `severity` (`error|warning|blocked|critical`)

### OCP Dependency Guardrails (erweitert)
`ocp_api_unavailable` wird jetzt auch gesetzt bei:
- `AttributeError` mit OCP-API-Drift (`has no attribute`)
- wrapped dependency messages (z. B. `RuntimeError` mit `cannot import name ... from 'OCP....'`)

`runtime_dependency` bleibt:
- `kind=ocp_api`
- `exception=<ExceptionClass>`
- `detail=<original message>`

## Impact
Geaendert:
- `modeling/__init__.py`
- `test/test_feature_error_status.py`
- `test/test_feature_edit_robustness.py`

Neue Regressionen:
- OCP dependency mapping fuer `AttributeError` und wrapped import messages.
- PI-006 Burn-in: zyklische invalid/valid edit tests + blocked recovery contract.

## Validation
```powershell
conda run --no-capture-output -n cad_env python -m py_compile modeling/__init__.py test/test_feature_error_status.py test/test_feature_edit_robustness.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_error_status.py -k "dependency"
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_edit_robustness.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultate:
- dependency subset: `3 passed`
- robustness suite: `9 passed`
- core gate: `255 passed, 2 skipped`

## UX Follow-up (GLM47)
1. Tooltip/Panel Mapping optional auf `status_class` priorisieren (statt nur `code`/`status`).
2. `WARNING_RECOVERABLE` konsequent als recoverable visualisieren.
3. `BLOCKED` vs `ERROR` in UI differenzieren (z. B. blocked chip/label).
