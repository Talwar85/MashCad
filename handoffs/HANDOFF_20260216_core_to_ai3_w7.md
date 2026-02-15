# HANDOFF_20260216_core_to_ai3_w7

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release)
**ID:** core_to_ai3_w7

## Problem
Sweep-Pfad-Resolver hatte gegenüber Edge/Face noch eine Lücke: `single_ref_pair` Konflikte mit schwacher Shape-Auflösung (`geometric|geometry_hash`) konnten unnötig als harter mismatch enden.

## API/Behavior Contract
Neu:
- `_resolve_path` behandelt `single_ref_pair` robust:
  - 1 `edge_index` + 1 `path_shape_id`
  - bei weak shape conflict -> index preferred
- Drift-Signal:
  - `tnp_failure.category=drift`
  - `tnp_failure.reference_kind=edge`
  - `tnp_failure.reason=single_ref_pair_geometric_shape_conflict_index_preferred`
- `_safe_operation` mappt diesen Fall auf:
  - `status=WARNING`
  - `status_details.code=tnp_ref_drift`

Unverändert:
- Bei starker/verlässlicher Shape-Auflösung bleibt strict mismatch aktiv.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue QA-relevante Tests:
- `test_sweep_resolve_path_single_ref_pair_geometric_conflict_prefers_index`
- `test_safe_operation_emits_drift_warning_for_sweep_path_single_ref_pair_geometric_conflict`

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
- QA-Evidence/Baselines müssen auf `244 passed, 2 skipped` aktualisiert werden.
- Error-Code-Mapping sollte Drift-Fälle explizit um Sweep-Pfad erweitern.
