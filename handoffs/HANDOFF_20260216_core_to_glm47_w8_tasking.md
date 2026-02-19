# HANDOFF_20260216_core_to_glm47_w8_tasking

**Date:** 2026-02-16
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW)
**ID:** core_to_glm47_w8_tasking
**Branch:** `feature/v1-ux-aiB`

## Scope
Neues grosses W7-Gigapaket fuer UX/Workflow wurde definiert.

Referenz-Prompt:
- `handoffs/PROMPT_20260216_glm47_w7_gigapack.md`

## Zielbild
- Direct manipulation deterministisch
- Selection-state voll migriert
- Error UX nutzt `status_class` + `severity`
- Discoverability state-driven
- UI gate reliability + W7 evidence

## Core-Vertrag fuer UX
Ab sofort liefert Core im Envelope:
- `status_details.status_class`
- `status_details.severity`

UX soll diese Felder priorisiert verwenden (mit fallback auf `code` fuer Backward-Compat).

## Validation-Expectation
GLM47 liefert nur mit reproduzierbaren Testresultaten gemaess Prompt (Pflicht-Validation).

## Review-Template (W8 Acceptance Gate)

Dieses Template wird von Codex zur Abnahme von
`handoffs/HANDOFF_20260216_glm47_w7_gigapack.md` verwendet.

### A) Vollstaendigkeit
- [ ] Pflichtstruktur 1..8 vorhanden (Problem, Read Acknowledgement, Contract, Impact, Validation, Risks, Delta, Next 5)
- [ ] Alle Pflicht-Quellen aus Prompt wurden explizit gelesen und mit Impact benannt
- [ ] W6 -> W7 Delta ist konkret und messbar

### B) Scope-Compliance
- [ ] Keine Edits in `modeling/**`
- [ ] Keine Edits in `config/feature_flags.py`
- [ ] Aenderungen liegen nur in erlaubten Bereichen (`gui/**`, `test/**`, `scripts/**`, `roadmap_ctp/**`, `handoffs/**`)

### C) Contract-Compliance (P0)
- [ ] Paket A: Direct Manipulation Determinism nachweisbar verbessert
- [ ] Paket B: Selection Full Migration umgesetzt oder sauber begruendet rest-offen
- [ ] Paket C: Error UX nutzt `status_class` + `severity` (mit Backward-Fallback)

### D) Test-Evidence
- [ ] `test/test_ui_abort_logic.py` ausgefuehrt, Resultat dokumentiert
- [ ] `test/harness/test_interaction_consistency.py` ausgefuehrt, Resultat dokumentiert
- [ ] `test/test_selection_state_unified.py` ausgefuehrt, Resultat dokumentiert
- [ ] `test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py` ausgefuehrt
- [ ] `test/test_gate_runner_contract.py` ausgefuehrt
- [ ] Bei Skips/Rot: reproduzierbarer Command + Root-Cause + naechster Fixschritt angegeben

### E) Qualitaetskriterien
- [ ] Keine Placeholders/Behauptungen ohne Command-Output
- [ ] Keine versteckten Breaking Changes
- [ ] Rest-Risiken mit Wahrscheinlichkeit/Impact/Mitigation genannt
- [ ] Naechste 5 Folgepakete mit Owner + ETA plausibel und priorisiert

### F) Ergebnis
- [ ] **GO**: W7 Gigapack merge-/weiterfuehrbar
- [ ] **CONDITIONAL GO**: nur mit benannten Auflagen
- [ ] **NO-GO**: Blocker verhindern Abnahme

### G) Reviewer-Notizen (auszufuellen)
- Entscheid:
- Kritische Findings (P0/P1):
- Auflagen bis naechster Uebergabe:
