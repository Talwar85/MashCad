# HANDOFF_20260216_core_to_gemini_w9

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** Gemini (UX/WORKFLOW)
**ID:** core_to_gemini_w9

## Problem
Nach PI-009 war `single_ref_pair`-Drift-Härtung für Edge-Resolver und Face-Resolver aktiv, aber im Sweep-Pfadresolver (`_resolve_path`) noch nicht konsistent.

Konkreter Fall:
- `path_data.edge_indices=[i]` + `path_shape_id` vorhanden,
- ShapeID löst nur schwach (`geometric|geometry_hash`) auf,
- Shape/Index konfliktieren,
- bisher: harter mismatch/Abort.

## API/Behavior Contract
Neu im Sweep-Pfadresolver (`_resolve_path`):
- Bei `single_ref_pair` (1 Index + 1 ShapeID) gilt:
  - Index+Shape auflösbar,
  - Konflikt,
  - und Shape-Methode ist schwach (`geometric|geometry_hash`)
- => Index-basierter Pfad wird bevorzugt, statt hartem Mismatch-Abbruch.

Envelope-Signal:
- `tnp_failure.category = drift`
- `tnp_failure.reference_kind = edge`
- `tnp_failure.reason = single_ref_pair_geometric_shape_conflict_index_preferred`
- `_safe_operation` emittiert dann:
  - `status = WARNING`
  - `status_details.code = tnp_ref_drift`

Unverändert:
- Bei belastbarer Shape-Auflösung + Konflikt bleibt der strict mismatch-Pfad aktiv.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue Tests:
- `test_sweep_resolve_path_single_ref_pair_geometric_conflict_prefers_index`
- `test_safe_operation_emits_drift_warning_for_sweep_path_single_ref_pair_geometric_conflict`

UX-Relevanz:
- `tnp_ref_drift` kann nun auch aus Sweep-Pfad-Konflikten kommen.
- UI-Mapping sollte weiterhin Warning/Fallback statt Broken/Error für diese Fälle zeigen.

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py test/test_tnp_v4_feature_refs.py
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_sweep_resolve_path_requires_shape_index_consistency test/test_tnp_v4_feature_refs.py::test_sweep_resolve_path_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_safe_operation_emits_drift_warning_for_sweep_path_single_ref_pair_geometric_conflict test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_single_ref_pair_geometric_conflict_prefers_index
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py test/test_parametric_reference_modelset.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- targeted: `4 passed`
- regression-pack+: `125 passed, 1 skipped`
- core-gate erweitert: `244 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- Verhalten wird robuster gegen false-negative mismatch im Sweep-Pfad bei schwacher Shape-Auflösung.
- UI sollte `tnp_ref_drift` konsistent auch für Sweep-Pfadfälle darstellen.
