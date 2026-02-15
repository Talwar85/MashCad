# HANDOFF_20260216_core_to_ai3_w6

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release)
**ID:** core_to_ai3_w6

## Problem
Single-ref-pair Drift-Härtung war bisher nur für Edge-Resolver vorhanden.
Face-Resolver (`_resolve_feature_faces`) konnte bei schwacher Shape-Auflösung (`geometric|geometry_hash`) und Shape/Index-Konflikt weiterhin in harten Mismatch laufen.

Für QA/Gates bedeutet das:
- Drift-Fälle für `reference_kind=face` müssen als Warning-Verhalten stabil getestet sein.
- False-negative ERROR-Rebuilds dürfen nicht zurückkommen.

## API/Behavior Contract
Neu:
- `single_ref_pair` im Face-Resolver bevorzugt index-basierte Auflösung bei schwacher Shape-Konfliktlage.
- Drift-Metadaten:
  - `tnp_failure.category=drift`
  - `tnp_failure.reference_kind=face`
  - `tnp_failure.reason=single_ref_pair_geometric_shape_conflict_index_preferred`
- `_safe_operation` emittiert in diesem Fall:
  - `status=WARNING`
  - `status_details.code=tnp_ref_drift`

Unverändert:
- Strikte mismatch-Fehler bleiben aktiv, wenn kein schwacher Auflösungsfall vorliegt.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue QA-relevante Tests:
- `test_resolve_feature_faces_single_ref_pair_geometric_conflict_prefers_index`
- `test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_face_conflict`

## Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py test/test_tnp_v4_feature_refs.py
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_resolve_feature_faces_extrude_blocks_mismatch_even_with_legacy_shape_local_index test/test_tnp_v4_feature_refs.py::test_resolve_feature_faces_single_ref_pair_geometric_conflict_prefers_index test/test_tnp_v4_feature_refs.py::test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_face_conflict test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_single_ref_pair_geometric_conflict_prefers_index
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py test/test_parametric_reference_modelset.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- targeted: `4 passed`
- regression-pack+: `123 passed, 1 skipped`
- core-gate erweitert: `242 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- Release-Gate sollte jetzt explizit Face-Drift-Warnfälle monitoren (kein ERROR-Rückfall).
- UI-Gate kann `tnp_ref_drift`-Abdeckung für `reference_kind=face` als Pflichtcheck aufnehmen.
