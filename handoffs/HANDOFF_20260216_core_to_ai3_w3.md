# HANDOFF_20260216_core_to_ai3_w3

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release Cell)
**ID:** core_to_ai3_w3
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
Core hat PI-010-Baseline nachgezogen: Es fehlte ein deterministisches Referenzmodellset, das mehrere edit-intensive Parametrik-Flows seriell validiert (Rebuild + Roundtrip).

## 2. API/Behavior Contract
Keine neuen Core-API-Felder.
Nur neue Regression-Abdeckung:
- 20 deterministische Referenzmodelle (seeds 0..19)
- je Modell: mehrstufige Push/Pull-Feature-Kette
- Muss stabil sein fuer:
  - lokalen Rebuild (Idempotenz)
  - Document `to_dict()/from_dict()` + Rebuild (Roundtrip)

## 3. Impact
Neue Datei:
- `test/test_parametric_reference_modelset.py`

Scope:
- PI-010 Baseline (Referenzmodellset) operationalisiert
- QA-005 Vorbereitung (Golden-Model-Harness Richtung) mit reproduzierbaren Seeds

Wichtig fuer AI-3:
- Bitte in Gate-Doku `core-gate` / `nightly-gate` aufnehmen.
- Erwartete Metrik: `20 passed` fuer diese Suite.

## 4. Validation
Ausgefuehrt:
```powershell
conda run -n cad_env python -m pytest -q test/test_parametric_reference_modelset.py
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
```

Resultat:
- `test/test_parametric_reference_modelset.py`: `20 passed`
- Core-Gate erweitert: `238 passed, 2 skipped`

## 5. Breaking Changes / Residual Risks
- Kein API-Break.
- Suite ist auf Push/Pull-Referenzmodelle fokussiert (bewusst robust gehalten).
- Fillet/Chamfer-Drift in seed-basierten Replay-Flows bleibt separater Hardening-Track (bereits durch spezialisierte Suiten abgedeckt).
