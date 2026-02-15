# HANDOFF_20260215_core_to_gemini_w3

**Date:** 2026-02-15  
**From:** Codex (Core/KERNEL)  
**To:** Gemini (UX/WORKFLOW)  
**ID:** core_to_gemini_w3

## Problem
Core hat PI-001/PI-002 nachgezogen:
- TNP-Fehler werden jetzt taxonomisch klassifiziert statt nur `operation_failed`.
- Referenzauflösung (Face/Edge) wird stabil kanonisch sortiert persisted.

Damit ist der Kernel konsistenter, aber UI muss die neuen Fehlercodes sauber anzeigen.

## API/Behavior Contract
Neu im Error-Envelope (`status_details`):
- `code` kann jetzt sein:
  - `tnp_ref_missing`
  - `tnp_ref_mismatch`
  - `tnp_ref_drift`
- `tnp_failure` Zusatzobjekt:
  - `category`: `missing_ref|mismatch|drift`
  - `reference_kind`: `edge|face|...`
  - `reason`
  - `strict`
  - `next_action`
  - `expected`, `resolved` (optional)
  - `feature_id`, `feature_name`, `feature_class`

Determinismus:
- `_resolve_edges_tnp()` normalisiert `feature.edge_indices` stabil (aufsteigend, eindeutig).
- `_resolve_feature_faces()` normalisiert `feature.face_indices` stabil (aufsteigend, eindeutig).
- Persistierte ShapeIDs folgen derselben stabilen Reihenfolge.

## Impact
Betroffene Core-Files:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Empfohlene UX-Folgen (Gemini-Owner):
- UI-Fehleranzeige/Tooltips für neue `tnp_ref_*` Codes sprachlich präzisieren.
- Falls vorhanden: Badge/Panel für `tnp_failure.category` ergänzen.
- Regressionen für Tooltip-/Panel-Rendering aktualisieren.

## Validation
Ausgeführt:

```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_rebuild_fillet_invalid_edge_sets_tnp_missing_ref_error_code test/test_tnp_v4_feature_refs.py::test_rebuild_fillet_shape_index_mismatch_sets_tnp_mismatch_error_code test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_normalizes_index_order_deterministically test/test_tnp_v4_feature_refs.py::test_resolve_feature_faces_normalizes_index_order_deterministically
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py
```

Resultat:
- `155 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break auf Feature-Objekten.
- Verhalten von `status_details.code` ist präziser; UI darf nicht mehr nur auf `operation_failed` matchen.
- Zwei untracked lokale Debug-Dateien liegen weiterhin im Tree:
  - `test/debug_mainwindow.py`
  - `test/debug_qtbot.py`

