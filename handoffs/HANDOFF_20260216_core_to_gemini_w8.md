# HANDOFF_20260216_core_to_gemini_w8

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** Gemini (UX/WORKFLOW)
**ID:** core_to_gemini_w8

## Problem
Nach PI-008 (Edge single_ref_pair) gab es denselben False-Negative-Pfad auch bei single-face Referenzen (Extrude/Thread):
- `face_index` + `face_shape_id` vorhanden,
- ShapeID löst nur schwach (`geometric`/`geometry_hash`) auf,
- Konflikt zwischen Shape und Index,
- bisher: harter `ERROR`/`tnp_ref_mismatch`.

Das war in realen Rebuild-/Redo-Zyklen zu strikt und hat editierbare Zustände unnötig blockiert.

## API/Behavior Contract
Neu im Face-Resolver (`_resolve_feature_faces`):
- Für `single_ref_pair` gilt jetzt analog zu Edge:
  - Wenn Index + Shape auflösbar sind,
  - ein Konflikt besteht,
  - und Shape-Auflösung schwach ist (`geometric|geometry_hash`),
- dann wird **index-basierte Face-Referenz bevorzugt**.

Signalisiert wird das als Drift (nicht als Fehler):
- `tnp_failure.category = drift`
- `tnp_failure.reference_kind = face`
- `tnp_failure.reason = single_ref_pair_geometric_shape_conflict_index_preferred`

Envelope-Verhalten über `_safe_operation`:
- erfolgreiche Operation mit pending drift wird
  - `status = WARNING`
  - `status_details.code = tnp_ref_drift`

Unverändert:
- Bei belastbarer Shape-Auflösung und echter Kollision bleibt `mismatch`/`ERROR` bestehen.

## Impact
Geänderte Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue Tests:
- `test_resolve_feature_faces_single_ref_pair_geometric_conflict_prefers_index`
- `test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_face_conflict`

UX-Relevanz:
- Neue Drift-Warnungen treten jetzt auch für `reference_kind=face` auf, nicht nur `edge`.
- UI-Mapping soll bei `tnp_ref_drift` konsistent warning-state halten und keinen harten error-dialog erzwingen.

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
- Verhalten wird robuster (weniger false-negative ERROR) bei schwacher Face-Auflösung im single-ref-pair Fall.
- UI sollte `tnp_ref_drift` mit `reference_kind=face` explizit mitabdecken (Tooltip/Panel/Badge).
