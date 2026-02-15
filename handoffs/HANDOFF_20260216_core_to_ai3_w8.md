# HANDOFF_20260216_core_to_ai3_w8

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release)
**ID:** core_to_ai3_w8

## Problem
Sweep war nach W7 nur für Pfad robust. Profil-Referenzen konnten bei single-ref-pair + schwacher Shape-Auflösung weiterhin unnötig mit mismatch abbrechen.

## API/Behavior Contract
Neu:
- `_compute_sweep` behandelt Profil-konflikte robust:
  - `profile_face_index` + `profile_shape_id`
  - weak shape conflict (`geometric|geometry_hash`)
  - => index-preferred + drift statt mismatch.
- Drift-Metadaten:
  - `category=drift`
  - `reference_kind=face`
  - `reason=single_ref_pair_geometric_shape_conflict_index_preferred`

Unverändert:
- harte mismatch-Fälle mit belastbarer Shape-Auflösung bleiben ERROR.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue QA-Regressionsabdeckung:
- `test_compute_sweep_profile_single_ref_pair_geometric_conflict_prefers_index`

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
- QA-Rebaseline sollte auf `245 passed, 2 skipped` aktualisiert werden.
- Error-Code-Mapping muss Drift-Fälle jetzt für `reference_kind=edge` und `reference_kind=face` im Sweep-Kontext berücksichtigen.
