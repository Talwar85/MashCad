# HANDOFF_20260216_core_to_ai3_w4

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release Cell)
**ID:** core_to_ai3_w4
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
Der QA-Stack ist funktional vorhanden, aber noch nicht release-hart. Es gibt drei zentrale Lücken:

1. **Stale QA-Zahlen in Reports**
- Mehrere W2-Dokumente referenzieren veraltete Ergebnisse (vor PI-008/PI-010).
- Aktueller Core-Stand ist höher als in den Reports angegeben.

2. **Gate-Runner Robustheit unvollständig**
- `scripts/gate_ui.ps1` bricht bei non-zero `conda run` vor der eigenen Summary-Ausgabe ab.
- `scripts/gate_all.ps1` markiert Hygiene aktuell häufig als PASS (weil `hygiene_check.ps1` standardmäßig nur WARNING liefert).

3. **Release-Readiness ist nicht durchgängig evidenzbasiert dokumentiert**
- Gate-Doku, Mapping-Report und Burn-Down sind teilweise nicht synchron.
- Fehlende konsolidierte QA-Evidence-Datei pro Lauf.

## 2. API/Behavior Contract
Keine neuen Core-APIs. QA-Cell Scope bleibt:
- **Allowed:** `test/**`, `roadmap_ctp/**`, `scripts/**`, optionale `.github/workflows/**`
- **Blocked:** `modeling/**`, `gui/main_window.py`, `gui/viewport_pyvista.py`

Contract-Update fuer QA:
- `tnp_ref_drift` ist jetzt im Core operationalisiert und kann als `WARNING` + `status_details.code=tnp_ref_drift` auftreten.
- Reports und Mapping muessen das explizit abbilden.

## 3. Impact
Aktuell validierte Baseline (Codex):

```powershell
conda run -n cad_env python -m pytest -q test/test_parametric_reference_modelset.py
# 20 passed

conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py test/test_parametric_reference_modelset.py
# 238 passed, 2 skipped

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py
# 11 errors, 3 skipped
```

Runner-Befund:
- `scripts/gate_core.ps1`: OK
- `scripts/gate_ui.ps1`: Exit korrekt, aber bricht vor eigener Ergebnis-Zusammenfassung ab
- `scripts/gate_all.ps1`: funktioniert, aber Hygiene-Semantik aktuell zu weich
- `scripts/hygiene_check.ps1`: violations korrekt erkannt

## 4. Validation (Codex)
Siehe Kommandos oben; Ergebnisse sind reproduzierbar.

## 5. Breaking Changes / Residual Risks
- Kein API-Break.
- Haupt-Risiko bleibt UI-Gate-Blocker (`tr` NameError).
- Sekundäres Risiko: unzuverlässige Gate-Berichtserstellung durch Runner-Abbruchverhalten.
- Doku-Risiko: falsche Priorisierung, wenn stale Zahlen nicht entfernt werden.

## W4 Mission fuer AI-3
Ziel: QA/Gates auf **release-harte Reproduzierbarkeit** bringen.

Pflicht-Lieferungen:
1. Runner-Hardening (robuste Ausgabe + verlässliche Exit-Codes)
2. Vollständige Rebaseline aller QA-Reports auf aktuellen Stand
3. Konsolidierte QA-Evidence-Datei (maschinen- und menschenlesbar)
4. Hygiene-Gate-Policy klar machen (warn vs fail) und in Gate-All sauber berücksichtigen
5. Error-Code-Mapping auf PI-008/PI-010 Stand bringen

Rueckgabe:
- `handoffs/HANDOFF_20260216_ai3_w4.md`
- + `roadmap_ctp/QA_EVIDENCE_W4_20260216.md`
- + optional `roadmap_ctp/QA_EVIDENCE_W4_20260216.json`
