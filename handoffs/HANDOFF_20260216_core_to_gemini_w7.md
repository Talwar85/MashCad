# HANDOFF_20260216_core_to_gemini_w7

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** Gemini (UX/WORKFLOW)
**ID:** core_to_gemini_w7

## Problem
Bei `single_ref_pair` (ein `edge_index` + eine `edge_shape_id`) konnten Fillet/Chamfer-Rebuilds fälschlich auf `ERROR` kippen, wenn die ShapeID nur via schwachem Match (`geometric`/`geometry_hash`) aufgelöst wurde und zum Index konfliktierte.

## API/Behavior Contract
Neu im Edge-Resolver (`_resolve_edges_tnp`):
- Wenn alle Bedingungen erfüllt sind:
  - `single_ref_pair`
  - Index und Shape sind beide auflösbar
  - Konflikt zwischen Shape- und Index-Edge
  - Shape-Methode ist schwach (`geometric` oder `geometry_hash`)
- dann wird **index-basierte Referenz bevorzugt** statt hartem Mismatch-Fehler.
- Der Fall wird als Drift markiert:
  - `tnp_failure.category = drift`
  - `tnp_failure.reason = single_ref_pair_geometric_shape_conflict_index_preferred`

Neu im Envelope (`_safe_operation`):
- Erfolgreiche Operation mit pending `drift` wird als
  - `status = WARNING`
  - `status_details.code = tnp_ref_drift`
  emittiert.

Unverändert:
- Bei starkem Konflikt mit belastbarer Shape-Auflösung bleibt `tnp_ref_mismatch`/ERROR.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue Tests:
- `test_resolve_edges_tnp_single_ref_pair_geometric_conflict_prefers_index`
- `test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_conflict`

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_fillet_requires_shape_index_consistency test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_conflict
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py test/test_parametric_reference_modelset.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- targeted: `3 passed`
- regression-pack+: `121 passed, 1 skipped`
- core-gate erweitert: `240 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- Verhalten wurde an einer engen Stelle robuster gemacht (weniger false-negative ERRORs).
- UI sollte `tnp_ref_drift` weiterhin als recoverable warning behandeln.
