# CODEX Self Megapack W7 (Core/KERNEL)

**Date:** 2026-02-16  
**Branch Truth:** `feature/v1-ux-aiB`  
**Owner:** Codex (Core/KERNEL)

## Ziel
Ein großer eigener Lieferblock mit Fokus auf Produktionsreife:
- Golden-Model Harness verankern,
- Core-Gates erweitern,
- deterministische Core-Evidenz schaffen,
- große P0/P1-Risiken strukturiert abbauen.

## Paket C-W7A (DONE): QA-005 Golden Model Regression Harness

### Umfang
- Neue Suite `test/test_golden_model_regression_harness.py`
- Deterministische Digests über Referenzmodelle:
  - seed digest determinism,
  - summary fingerprint determinism,
  - roundtrip digest stability,
  - hard-error-state guard.

### Integration
- `scripts/gate_core.ps1` enthält Golden-Harness als Pflichtsuite.
- `scripts/generate_gate_evidence.ps1` enthält dieselbe Suite.
- `test/test_gate_runner_contract.py` prüft, dass Golden-Harness im Core-Gate enthalten ist.

### Abnahme (erreicht)
- Golden-Harness: `8 passed`
- Full core gate pack: `276 passed, 2 skipped`
- Gate runner core-contract subset: `3 passed`

---

## Paket C-W7B (DONE, P0): QA-007 Cross-Platform Baseline Contract

### Ziel
Cross-Platform-Mindestvertrag explizit machen (auch wenn lokal nur Win verfügbar ist).

### Deliverables
1. Dokumentierter Core-Contract für Win/Linux-Abweichungen:
   - tolerierte Unterschiede,
   - harte Invarianten.
2. Test-Marker/Selektion für platform-sensitive Suiten ohne Verwässerung.
3. Evidence-Vorlage für matrixfähige Läufe.

### Abnahme
- neue Contract-Doku in `roadmap_ctp/`
- mindestens 1 neuer Contract-Test oder Marker-Guard im Test-Stack

### Ergebnis
- Neue Suite: `test/test_core_cross_platform_contract.py`
- Core-Gate Integration aktiv
- Win32 Baseline + Plattform-Invarianten dokumentiert
- Doku: `roadmap_ctp/CROSS_PLATFORM_CORE_CONTRACT_W7_20260216.md`

---

## Paket C-W7C (IN_PROGRESS, P0): QA-006 Performance Regression Gate Baseline

### Ziel
Eine erste harte Baseline für Laufzeiten kritischer Core-Suiten.

### Deliverables
1. definierte Zeit-Budgets für:
   - core-gate gesamt,
   - golden-harness,
   - parametric-reference-modelset.
2. leichter Budget-Check (non-flaky) als Warn-/Fail-Mechanik.
3. Dokumentierte Ausnahmen für CI-Infrastruktur-Drift.

### Abnahme
- Budget-Doku + reproduzierbarer Check-Command
- kein false-positive Dauerrauschen

### Aktueller Lieferstand
- Runner: `scripts/check_core_gate_budget.ps1`
- Aggregator-Unterstützung: `scripts/gate_all.ps1 -EnforceCoreBudget`
- Doku: `roadmap_ctp/CORE_GATE_BUDGET_BASELINE_W7_20260216.md`

---

## Paket C-W7D (NEXT, P1): CH-009 Stability Dashboard Seed

### Ziel
Stabilitätsmetriken werden standardisiert gesammelt, nicht ad-hoc.

### Deliverables
1. konsolidierte Kernmetriken:
   - pass/fail/skip trends,
   - blocker signatures,
   - gate durations.
2. einheitliche Ausgabe über Evidence JSON.
3. minimaler Verlauf über mehrere Läufe.

### Abnahme
- dashboard_seed Doku + Beispielartefakt

---

## Operative Reihenfolge
1. C-W7B
2. C-W7C
3. C-W7D

Regel:
- Keine P1-Eskalation, bevor C-W7B/C-W7C baseline-stabil sind.
