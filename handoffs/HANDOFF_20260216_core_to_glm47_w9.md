# HANDOFF_20260216_core_to_glm47_w9

**Date:** 2026-02-16
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW)
**ID:** core_to_glm47_w9
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
W7/W8 hat `status_class`/`severity` eingefuehrt, aber Persistenz musste fuer Legacy-Dateien robust nachgezogen werden.
Zusatzlich wurde PI-006/PI-007 im Edit+Roundtrip-Stress weiter gehaertet.

## 2. API/Behavior Contract
Neu/Erweitert:
- `Body._normalize_status_details_for_load(...)`
  - Legacy `status_details` mit `code`, aber ohne `status_class`/`severity`, werden beim Laden automatisch migriert.
  - Nicht-dict `status_details` werden defensiv zu `{}` normalisiert.

- Einheitliche Klassifikation via `Body._classify_error_code(...)`:
  - `WARNING_RECOVERABLE` / `warning`
  - `BLOCKED` / `blocked`
  - `CRITICAL` / `critical`
  - `ERROR` / `error`

- CH-006 Guardrail erweitert:
  - `ocp_api_unavailable` deckt jetzt auch OCP-`AttributeError` und wrapped import-messages ab.

## 3. Impact
Geaendert:
- `modeling/__init__.py`
- `test/test_feature_error_status.py`
- `test/test_feature_edit_robustness.py`
- `test/test_project_roundtrip_persistence.py`

Neue/erweiterte Regressionen:
- Dependency-Mapping fuer OCP API Drift (`ImportError`, `AttributeError`, wrapped RuntimeError)
- PI-006 edit cycles + blocked recovery contract
- PI-007 Roundtrip-Migration von legacy status_details und Persistenz der neuen Felder

## 4. Validation
```powershell
conda run --no-capture-output -n cad_env python -m py_compile modeling/__init__.py test/test_feature_error_status.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_project_roundtrip_persistence.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultate:
- `test_feature_error_status.py + test_project_roundtrip_persistence.py`: `26 passed`
- Core-Gate erweitert: `257 passed, 2 skipped`

## 5. Breaking Changes / Rest-Risiken
- Kein API-Break.
- UX sollte `status_class` priorisiert verwenden (mit `code`-fallback), da Legacy-Daten nun beim Laden konsistent migriert werden.
- Rest-Risiko: UI-Flaechen, die weiterhin nur auf alten `status`-String schauen, verschenken den neuen Semantikgewinn.
