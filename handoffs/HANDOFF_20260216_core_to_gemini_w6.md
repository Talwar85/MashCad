# HANDOFF_20260216_core_to_gemini_w6

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** Gemini (UX/WORKFLOW)
**ID:** core_to_gemini_w6

## Problem
`tnp_ref_drift` war im Error-Code-Mapping vorhanden, wurde aber in einem zentralen Recovery-Pfad nicht aktiv als Runtime-Warning emittiert.

Konkret: Wenn Topologie-Referenzen (ShapeID/Index) brechen, `strict_topology_fallback_policy=False` ist und ein Geometric-Selector den Treffer recovern kann, lief der Kernel bisher oft still erfolgreich weiter.

## API/Behavior Contract
Neu abgesichert:
- `_resolve_edges_tnp()` markiert erfolgreichen Selector-Recovery nach gebrochener Topologie jetzt als `tnp_failure.category="drift"`.
- `_safe_operation()` mappt eine solche Drift bei erfolgreicher Operation auf:
  - `status = "WARNING"`
  - `status_details.code = "tnp_ref_drift"`
  - `status_details.tnp_failure` mit Kategorie/Referenztyp/Reason.

Unveraendert:
- Harte Fehlerfaelle bleiben `tnp_ref_missing` / `tnp_ref_mismatch`.
- Bei `strict_topology_fallback_policy=True` bleibt Recovery blockiert.

## Impact
Betroffene Core-Dateien:
- `modeling/__init__.py`
- `test/test_tnp_v4_feature_refs.py`

Neue/angepasste Regressionen:
- `test_resolve_edges_tnp_allows_selector_recovery_when_strict_policy_disabled`
  - validiert jetzt explizit `drift` Notice.
- `test_safe_operation_emits_tnp_ref_drift_warning_after_selector_recovery` (neu)
  - validiert `WARNING + code=tnp_ref_drift` End-to-End im `_safe_operation` Envelope.

## Validation
Ausgefuehrt:
```powershell
conda run -n cad_env python -m pytest -q test/test_tnp_v4_feature_refs.py::test_resolve_edges_tnp_allows_selector_recovery_when_strict_policy_disabled test/test_tnp_v4_feature_refs.py::test_safe_operation_emits_tnp_ref_drift_warning_after_selector_recovery
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
```

Resultat:
- targeted: `2 passed`
- regression pack: `99 passed, 1 skipped`
- core gate: `218 passed, 2 skipped`

## Breaking Changes / Rest-Risiken
- Kein API-Break an Feature-Datenmodellen.
- Behavior-Änderung: einige bisher `SUCCESS`-Faelle werden bei Drift-Recovery jetzt als `WARNING` mit `tnp_ref_drift` sichtbar.
- UI sollte `WARNING + tnp_ref_drift` nicht als hard-fail behandeln, aber klar visualisieren.
