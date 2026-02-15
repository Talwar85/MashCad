# HANDOFF_20260216_core_to_gemini_w10

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** Gemini (UX/WORKFLOW)
**ID:** core_to_gemini_w10

## Problem
Nach PI-010 (Sweep-Pfad drift-hardened) blieb eine letzte Inkonsistenz im Sweep-Profilpfad:
- `profile_face_index` + `profile_shape_id` vorhanden,
- ShapeID nur schwach auflösbar (`geometric|geometry_hash`),
- Shape/Index konfliktieren,
- bisher: harter mismatch/Abort.

## API/Behavior Contract
Neu in `_compute_sweep` (Profilauflösung):
- Für single-ref-pair Profilreferenz gilt nun:
  - weak shape conflict (`geometric|geometry_hash`) => index-basiertes Profil bevorzugen.
- Drift-Signal:
  - `tnp_failure.category = drift`
  - `tnp_failure.reference_kind = face`
  - `tnp_failure.reason = single_ref_pair_geometric_shape_conflict_index_preferred`

Zusätzlich:
- Bei `profile_shape_id` unresolved + gültigem `profile_face_index` wird index-basiert fortgefahren.
- Profilreferenzen werden konsistent auf Index zurückgeführt/persistiert.

Unverändert:
- Bei belastbarer Shape-Auflösung + Konflikt bleibt `mismatch`/strict erhalten.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue Regression:
- `test_compute_sweep_profile_single_ref_pair_geometric_conflict_prefers_index`

Bestehende Mismatch-Härte bleibt abgedeckt durch:
- `test_compute_sweep_requires_profile_shape_index_consistency`

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py test/test_tnp_v4_feature_refs.py
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_compute_sweep_requires_profile_shape_index_consistency test/test_tnp_v4_feature_refs.py::test_compute_sweep_profile_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_sweep_resolve_path_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_safe_operation_emits_drift_warning_for_sweep_path_single_ref_pair_geometric_conflict
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py test/test_parametric_reference_modelset.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- targeted: `4 passed`
- regression-pack+: `126 passed, 1 skipped`
- core-gate erweitert: `245 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- `tnp_ref_drift` kann jetzt zusätzlich aus Sweep-Profilkonflikten kommen (`reference_kind=face`).
- UI sollte diese Fälle als recoverable warning anzeigen, nicht als hard broken.
