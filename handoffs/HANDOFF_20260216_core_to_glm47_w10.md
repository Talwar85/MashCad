# HANDOFF_20260216_core_to_glm47_w10

**Date:** 2026-02-16
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW)
**ID:** core_to_glm47_w10
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
Nach W9 fehlte noch der gebuendelte CH-010 Showstopper-Regression-Block als eigener, klarer Gate-Baustein.
Ziel war, High-Impact Rueckfaelle (Finalize-Failsafe, Blocked-Chain, Drift-Warning-Semantik, Rollback-Persistenz) in einem festen Core-Pack zu verankern.

## 2. API/Behavior Contract
Bestehende Core-Contracts bleiben aktiv:
- `status_details.status_class` + `status_details.severity` sind kanonisch.
- `ocp_api_unavailable` deckt Import-/API-Drift inkl. OCP-`AttributeError` und wrapped import runtime messages ab.
- Legacy-Load migriert fehlende `status_class`/`severity` aus `code`.

Neu in CH-010 Regression Pack:
- `test/test_showstopper_red_flag_pack.py` als gebuendelter Showstopper-Contract.
- Pflichtkontrakte:
  - finalize failsafe -> `code=rebuild_finalize_failed`, `status_class=CRITICAL`
  - blocked downstream chain -> `code=blocked_by_upstream_error`, `status_class=BLOCKED`
  - drift warning -> `code=tnp_ref_drift`, `status_class=WARNING_RECOVERABLE`
  - rollback envelope + class/severity bleiben nach save/load erhalten

Gate-Integration:
- `scripts/gate_core.ps1` fuehrt Red-Flag Pack jetzt als Pflichtsuite aus.
- `scripts/generate_gate_evidence.ps1` nutzt identische Core-Suitenliste inkl. Red-Flag Pack.

## 3. Impact
Geaendert:
- `modeling/__init__.py`
- `test/test_feature_error_status.py`
- `test/test_feature_edit_robustness.py`
- `test/test_project_roundtrip_persistence.py`
- `test/test_showstopper_red_flag_pack.py` (neu)
- `scripts/gate_core.ps1`
- `scripts/generate_gate_evidence.ps1`
- `roadmap_ctp/CH010_REDFLAG_GATE_20260216.md` (neu)
- `roadmap_ctp/CODEX_MEGAPACKS_W6.md`

## 4. Validation
Ausgefuehrt:

```powershell
conda run --no-capture-output -n cad_env python -m pytest -q test/test_showstopper_red_flag_pack.py test/test_feature_error_status.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_showstopper_red_flag_pack.py test/test_parametric_reference_modelset.py
conda run --no-capture-output -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_output_schema test/test_gate_runner_contract.py::TestGateRunnerContract::test_exit_code_contract_core
```

Resultate:
- Focused pack: `39 passed`
- Full core gate pack (inkl. Red-Flag): `261 passed, 2 skipped`
- Gate-runner contract checks: `2 passed`

## 5. Breaking Changes / Rest-Risiken
- Kein API-Break.
- Core-Gate Laufzeit steigt leicht durch neue Pflichtsuite (erwartbar).
- UX-Seite sollte weiter `status_class` priorisieren und `code` nur als fallback verwenden.
