# HANDOFF_20260216_core_to_gemini_w11

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** Gemini (UX/WORKFLOW)
**ID:** core_to_gemini_w11

## Problem
Kein neuer API-Change seit W10, aber die Sweep-Drift-Härtung wurde durch zusätzliche Regressionen abgesichert und der Core-Gate-Stand ist erneut gestiegen.

## API/Behavior Contract
Unverändert zu W10:
- Sweep-Pfad und Sweep-Profil single-ref-pair weak conflicts mappen auf drift (`tnp_ref_drift`) statt false-negative mismatch.

## Impact
Nur Testausbau:
- `test/test_tnp_v4_feature_refs.py`

Neue Tests:
- `test_sweep_resolve_path_single_ref_pair_shape_missing_prefers_index`
- `test_compute_sweep_profile_single_ref_pair_shape_missing_prefers_index`
- `test_safe_operation_emits_drift_warning_for_sweep_profile_single_ref_pair_geometric_conflict`

## Validation
Aktueller Core-Gate-Lauf:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- `248 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- UI kann weiter `tnp_ref_drift` als recoverable warning behandeln; zusätzlicher Testausbau senkt Regressionsrisiko.
