# HANDOFF_20260216_core_to_ai3_w5

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release Cell)
**ID:** core_to_ai3_w5

## Problem
Core-Baseline wurde nachgezogen: zusätzliches Drift-Hardening im Edge-Resolver plus 2 neue Regressionstests.
Dadurch sind Gate-Zahlen gegenüber W4 erneut gestiegen.

## API/Behavior Contract
Keine neuen Felder; bestehender Drift-Contract konkretisiert:
- `tnp_ref_drift` kann bei `single_ref_pair`-Konflikten auftreten, wenn Shape-Auflösung schwach ist (`geometric`/`geometry_hash`) und index-basierte Referenz bevorzugt wird.

## Impact
Geänderte Core-Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue Tests:
- `test_resolve_edges_tnp_single_ref_pair_geometric_conflict_prefers_index`
- `test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_conflict`

Neue Baseline:
- Core-Gate erweitert: `240 passed, 2 skipped`

## Validation
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```
Resultat:
- `240 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break.
- QA-Dokumente/Gates sollten Zahlen von `238` auf `240` aktualisieren.
