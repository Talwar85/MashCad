# HANDOFF_20260216_core_to_glm47_w11

**Date:** 2026-02-16
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW), QA
**ID:** core_to_glm47_w11
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
PI-010 deckt Referenzmodell-Rebuild/Roundtrip bereits ab, aber es fehlte ein dedizierter Golden-Harness-Block,
der Determinismus als eigene, explizite Regression absichert.

Ziel:
- deterministic geometry digest checks als eigenständiger QA-005 Baustein
- nicht nur "kein Fehler", sondern reproduzierbare Signatur-Konsistenz über unabhängige Runs

## 2. API/Behavior Contract
Neu:
- `test/test_golden_model_regression_harness.py`
  - seed digest determinism across independent runs
  - summary fingerprint determinism across independent runs
  - roundtrip rebuild digest stability
  - hard-error-state guard für Golden-Referenzmodelle

Core-Gate Contract erweitert:
- `scripts/gate_core.ps1` enthält jetzt zusätzlich:
  - `test/test_golden_model_regression_harness.py`
- `scripts/generate_gate_evidence.ps1` nutzt dieselbe Core-Suitenliste inkl. Golden-Harness.

QA Contract erweitert:
- `test/test_gate_runner_contract.py`
  - `test_gate_core_includes_golden_harness_suite`

## 3. Impact
Geändert:
- `test/test_golden_model_regression_harness.py` (neu)
- `scripts/gate_core.ps1`
- `scripts/generate_gate_evidence.ps1`
- `test/test_gate_runner_contract.py`

## 4. Validation
Ausgeführt:

```powershell
conda run --no-capture-output -n cad_env python -m pytest -q test/test_golden_model_regression_harness.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_feature_commands_atomic.py test/test_project_roundtrip_persistence.py test/test_showstopper_red_flag_pack.py test/test_golden_model_regression_harness.py test/test_parametric_reference_modelset.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_output_schema test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_includes_golden_harness_suite test/test_gate_runner_contract.py::TestGateRunnerContract::test_exit_code_contract_core
powershell -ExecutionPolicy Bypass -File scripts/gate_core.ps1
```

Resultate:
- Golden-Harness: `8 passed`
- Full core pack: `276 passed, 2 skipped`
- Gate-runner contract checks: `3 passed`
- `gate_core.ps1`: `PASS` (`276 passed, 2 skipped`)

## 5. Breaking Changes / Rest-Risiken
- Kein API-Break.
- Core-Gate Laufzeit steigt moderat durch zusätzliche Golden-Suite.
- Rest-Risiko bleibt auf UI-Gate-Infrastrukturseite (separater Track), nicht im Core-Harness selbst.
