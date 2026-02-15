# HANDOFF_20260215_core_to_ai3_w1

**Date:** 2026-02-15  
**From:** Codex (Core/KERNEL)  
**To:** AI-3 (QA/RELEASE)  
**ID:** core_to_ai3_w1

## Problem
Projekt ist funktional deutlich stabiler, aber V1-Risiko liegt jetzt primär in:
- UI-Test-Instabilität (Qt/PyVista Interaktion)
- fehlender Gate-Automatisierung für reproduzierbare Freigabe
- fehlender zentraler Flaky-/Skip-Burn-Down-Disziplin

Core-Seite ist aktuell auf grünem Baseline-Stand, muss aber in Release-Gates dauerhaft gehalten werden.

## Aktueller Baseline-Stand
Validiert durch Codex:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
```
Resultat:
- `214 passed, 2 skipped`

Bekannte offene UX/Test-Probleme (nicht Core):
- `test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_cancels_drag`
- `test/harness/test_interaction_consistency.py::TestInteractionConsistency::test_click_selects_nothing_in_empty_space`
- siehe zusätzlich: `handoffs/HANDOFF_20260215_core_to_gemini_w4.md`

## Scope fuer AI-3 (QA/RELEASE Cell)
### Ownership (erlaubt)
- `test/**` (QA/Gate/Regression-Infrastruktur)
- `roadmap_ctp/**` (QA-Reports, Gate-Doku)
- Build-/Gate-Skripte (falls vorhanden unter scripts/tools)

### Ownership (gesperrt)
- `modeling/**`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- keine semantischen Produktlogik-Edits in Kernel/UI ohne explizite Freigabe

## Arbeitspakete
### Q3-W1-P0: Flaky/Crash Burn-Down
- Ziel: reproduzierbare Ursachen je Flaky/Crash-Test (Timing, Render-Context, Event-Reihenfolge, State-Leak).
- Pflicht-Artefakt: Matrix in `roadmap_ctp/` mit:
  - Testname
  - Repro-Command
  - Ursache-Klasse
  - Stabilisierungsvorschlag
  - Owner (AI-2/AI-3)
  - ETA

### Q3-W1-P0: Gate-Automatisierung
- Einheitliche lokale Gate-Kommandos definieren:
  - `core-gate`
  - `ui-gate`
- Ergebnisformat standardisieren (pass/fail/skipped + Dauer + rote Tests).

### Q3-W1-P0: Regression-Pack Integration
- Sicherstellen, dass folgende Core-Regressionen im Nightly/Release-Gate enthalten sind:
  - `test/test_feature_edit_robustness.py`
  - `test/test_project_roundtrip_persistence.py`
  - `test/test_tnp_v4_feature_refs.py`
  - `test/test_feature_error_status.py`

### Q3-W1-P1: Error-Code UX Mapping QA
- Prüfen, ob UI alle relevanten `status_details.code` korrekt mapped:
  - `tnp_ref_missing`
  - `tnp_ref_mismatch`
  - `tnp_ref_drift`
  - `rebuild_finalize_failed`
  - `ocp_api_unavailable`
- Ergebnis als Mapping-Report inkl. fehlender Abdeckung.

### Q3-W1-P1: Workspace Hygiene Gates
- Untracked Debug-/Temp-Artefakte im Gate sichtbar machen (nicht still ignorieren).
- Beispielkandidaten aktuell:
  - `test/debug_mainwindow.py`
  - `test/debug_qtbot.py`
  - `test_output.txt`
  - `test_output_trace.txt`

## Abnahmebedingungen
1. Reproduzierbare QA-Dokumentation liegt vor (keine rein verbalen Aussagen).
2. `core-gate` und `ui-gate` sind lokal ausführbar dokumentiert.
3. Flaky-/Skip-Liste enthält konkrete Eigentümer + ETAs.
4. Keine Core- oder gesperrten UI-Dateien angefasst.

## Pflicht-Rueckgabe von AI-3
- Handoff: `handoffs/HANDOFF_YYYYMMDD_ai3_w1.md`
- Mit 5 Pflichtsektionen:
  1. Problem
  2. API/Behavior Contract (falls betroffen)
  3. Impact
  4. Validation (exakte Commands + Resultate)
  5. Breaking Changes / Rest-Risiken
