# HANDOFF_20260216_core_to_ai3_w9

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release)
**ID:** core_to_ai3_w9

## Problem
Nach PI-010/PI-011 sind zusätzliche Regressionen nötig gewesen, um den robusten `single_ref_pair`-Pfad auch für den Fall "ShapeID nicht auflösbar, Index gültig" explizit zu fixieren.

## API/Behavior Contract
Kein neuer API-Contract gegenüber W8.

Neu ist nur die abgesicherte Testabdeckung:
- Sweep-Pfad: Shape missing + Index valid -> index-preferred bleibt stabil
- Sweep-Profil: Shape missing + Index valid -> index-preferred bleibt stabil
- Safe-Operation-Warnpfad (`tnp_ref_drift`) für Sweep-Profilkonflikt explizit regressionsgesichert

## Impact
Geänderte Datei:
- `test/test_tnp_v4_feature_refs.py`

Neu hinzugefügte Tests:
- `test_sweep_resolve_path_single_ref_pair_shape_missing_prefers_index`
- `test_compute_sweep_profile_single_ref_pair_shape_missing_prefers_index`
- `test_safe_operation_emits_drift_warning_for_sweep_profile_single_ref_pair_geometric_conflict`

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_sweep_resolve_path_single_ref_pair_shape_missing_prefers_index test/test_tnp_v4_feature_refs.py::test_compute_sweep_profile_single_ref_pair_shape_missing_prefers_index test/test_tnp_v4_feature_refs.py::test_sweep_resolve_path_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_compute_sweep_profile_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_safe_operation_emits_drift_warning_for_sweep_profile_single_ref_pair_geometric_conflict
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- targeted: `5 passed`
- core-gate erweitert: `248 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- QA-Dokumente/Baselines sollten auf `248 passed, 2 skipped` aktualisiert werden.
