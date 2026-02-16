# CODEX Self Megapack W9 (Core/KERNEL Heavy)

**Date:** 2026-02-16  
**Branch Truth:** `feature/v1-ux-aiB`  
**Owner:** Codex (Core/KERNEL)

## Ziel
Ein grosser, zusammenhaengender Core/QA-Block fuer parallele Multi-Agent-Entwicklung:
- Core-Gates trotz paralleler UX-Edits stabil fahrbar machen,
- Gate-Profile explizit und reproduzierbar machen,
- Budget-/Aggregator-Runner auf dieselbe Profil-Logik ausrichten,
- maschinenlesbare Gate-Summaries bereitstellen.

---

## Paket C-W9A (DONE, P0): Core Gate Profile System

### Scope
- `scripts/gate_core.ps1` erweitert um:
  - `-Profile full|parallel_safe|kernel_only|red_flag`
  - `-DryRun`
  - `-JsonOut`
  - bestehender `-SkipUxBoundSuites` bleibt kompatibel.

### Verhalten
- `full`: kompletter Core-Gate-Stack
- `parallel_safe`: UX-gebundene Suite ausgeklammert (`test/test_feature_commands_atomic.py`)
- `kernel_only`: zusaetzlich nicht-kernelnahe Contract-Suiten ausgeklammert
- `red_flag`: fail-fast Showstopper/Parametrik-Profil fuer schnelle Kernfreigabe

### Ergebnis
- deterministische Profilauswahl + schnelle Dry-Run-Inspektion.

---

## Paket C-W9B (DONE, P0): Aggregator/Budget Profile Alignment

### Scope
- `scripts/gate_all.ps1` erweitert um `-CoreProfile`.
- Core-Gate-Aufruf im Aggregator ist jetzt profile-aware.
- `scripts/check_core_gate_budget.ps1` erweitert um `-CoreProfile`.

### Ergebnis
- Budget-Checks und All-Gate-Lauf nutzen identische Core-Gate-Profile.
- kein Drift mehr zwischen Einzelgate und Aggregator.

---

## Paket C-W9C (DONE, P0): Contract Coverage fuer Profile

### Scope
- neue Suite: `test/test_core_gate_profiles_contract.py`
  - dry-run full enthaelt ux-bound suite
  - dry-run parallel_safe schliesst ux-bound suite aus
  - dry-run kernel_only schliesst nicht-kernel-contract suites aus
  - dry-run json manifest wird geschrieben und geprueft
- `test/test_gate_runner_contract.py` erweitert fuer Profile-/CoreProfile-Contracts.

### Ergebnis
- profile contracts sind regressionsgesichert.

---

## Paket C-W9D (DONE, P1): Core Profile Matrix Seed

### Scope
- neues Script: `scripts/generate_core_profile_matrix.ps1`
  - fuehrt `gate_core` dry-run je Profil aus,
  - erzeugt Vergleich als JSON + MD.
- neue Test-Suite: `test/test_core_profile_matrix_seed.py`
  - validiert Schema + Profil-Deltas.
- Gate-Runner-Contract erweitert:
  - `test_core_profile_matrix_script_exists`

### Ergebnis
- reproduzierbarer Profilvergleich fuer `full`, `parallel_safe`, `kernel_only`, `red_flag`.

---

## Validierung

```powershell
conda run -n cad_env python -m pytest -q test/test_core_gate_profiles_contract.py test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_has_parallel_mode_parameter test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_output_schema test/test_gate_runner_contract.py::TestGateRunnerContract::test_exit_code_contract_core test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_has_core_budget_parameter_contract test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_budget_script_has_stable_defaults
conda run -n cad_env python -m pytest -q test/test_core_profile_matrix_seed.py test/test_core_gate_profiles_contract.py test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_profile_matrix_script_exists
conda run -n cad_env python -m pytest -q test/test_core_gate_profiles_contract.py test/test_core_profile_matrix_seed.py test/test_core_gate_trend_seed.py test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_has_parallel_mode_parameter test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_profile_matrix_script_exists test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_gate_trend_script_exists test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_has_core_budget_parameter_contract test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_contains_json_summary_contract test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_budget_script_has_stable_defaults
conda run -n cad_env python -m pytest -q test/test_core_gate_profiles_contract.py test/test_core_profile_matrix_seed.py test/test_core_gate_trend_seed.py test/test_core_ops_dashboard_seed.py test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_profile_matrix_script_exists test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_gate_trend_script_exists test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_ops_dashboard_script_exists test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_has_parallel_mode_parameter

powershell -ExecutionPolicy Bypass -File scripts/check_core_gate_budget.ps1 -CoreProfile parallel_safe
powershell -ExecutionPolicy Bypass -File scripts/gate_all.ps1 -CoreProfile parallel_safe -ValidateEvidence
powershell -ExecutionPolicy Bypass -File scripts/check_core_gate_budget.ps1 -CoreProfile red_flag
powershell -ExecutionPolicy Bypass -File scripts/gate_all.ps1 -CoreProfile red_flag -ValidateEvidence -JsonOut gate_all_summary_red_flag.json
powershell -ExecutionPolicy Bypass -File scripts/generate_core_gate_trend.ps1 -EvidenceDir . -Pattern "gate_all_summary_red_flag.json" -OutPrefix core_gate_trend_red_flag
powershell -ExecutionPolicy Bypass -File scripts/generate_core_profile_matrix.ps1 -OutPrefix core_profile_matrix_live
powershell -ExecutionPolicy Bypass -File scripts/generate_core_gate_trend.ps1 -EvidenceDir . -Pattern "gate_all_summary_red_flag_live.json" -OutPrefix core_gate_trend_live
powershell -ExecutionPolicy Bypass -File scripts/generate_core_ops_dashboard.ps1 -MatrixJson core_profile_matrix_live.json -TrendJson core_gate_trend_live.json -OutPrefix core_ops_dashboard_live
```

**Observed:**
- Contract-Tests gruen
- Matrix-Seed-Tests gruen
- Trend-Seed-Tests gruen
- Ops-Dashboard-Seed-Tests gruen
- Budget-Check gruen (`parallel_safe`)
- `gate_all` mit `-CoreProfile parallel_safe -ValidateEvidence` -> `ALL GATES PASSED` (UI als `BLOCKED_INFRA`, nicht FAIL)
- Budget-Check gruen (`red_flag`)
- `gate_all` mit `-CoreProfile red_flag -ValidateEvidence -JsonOut ...` -> `ALL GATES PASSED`
- `generate_core_gate_trend.ps1` erzeugt `core_gate_trend_v1` JSON+MD artefakt.
- `generate_core_ops_dashboard.ps1` erzeugt `core_ops_dashboard_v1` JSON+MD artefakt.

---

## Paket C-W9E (DONE, P0): Gate Summary JSON Contract v1

### Scope
- `scripts/gate_all.ps1` erweitert um optionales `-JsonOut`.
- Aggregator schreibt maschinenlesbare Zusammenfassung mit Schema:
  - `gate_all_summary_v1`.
- Config/Gate/Overall Sektionen sind enthalten.

### Ergebnis
- Gate-All-Output ist sowohl menschenlesbar als auch maschinenlesbar verwendbar.

---

## Paket C-W9F (DONE, P1): Core Red-Flag Profile

### Scope
- `red_flag` Profil im Core-Gate, Budget-Check und Aggregator aktivierbar.
- Fokus auf schnelle Kernindikatoren:
  - `test/test_showstopper_red_flag_pack.py`
  - `test/test_feature_error_status.py`
  - `test/test_tnp_v4_feature_refs.py`
  - `test/test_feature_edit_robustness.py`
  - `test/test_project_roundtrip_persistence.py`
  - `test/test_parametric_reference_modelset.py`

### Ergebnis
- signifikanter Laufzeitgewinn fuer schnelle Kern-Freigabechecks
  (budget-run mit `CoreProfile=red_flag` im Bereich ~20s gemessen).

---

## Paket C-W9G (DONE, P1): Core-Gate Trend Capture Seed

### Scope
- neues Script: `scripts/generate_core_gate_trend.ps1`
  - aggregiert gate-summary JSONs,
  - erzeugt trend JSON + MD (`core_gate_trend_v1`).
- neue Suite: `test/test_core_gate_trend_seed.py`
  - validiert Trend-Schema und Kernmetriken.

### Ergebnis
- erster reproduzierbarer Trend-Pfad fuer Core-Gate-Verlaeufe vorhanden.

---

## Naechste Grosspakete (W9 Folge)

1. **C-W9H (P0): UI-Gate JSON Summary Contract**
- `gate_ui.ps1` und `generate_gate_evidence.ps1` auf dieselbe JSON-Kontraktbasis bringen.

2. **C-W9I (P1): Trend Fusion Dashboard**
- Core-Profile-Matrix + Core-Gate-Trend in konsolidierte Dashboard-Sicht ueberfuehren.

---

## Paket C-W9I (DONE, P1): Trend Fusion Dashboard Seed

### Scope
- neues Script: `scripts/generate_core_ops_dashboard.ps1`
  - fusioniert `core_profile_matrix_v1` + `core_gate_trend_v1`,
  - erzeugt Dashboard JSON+MD (`core_ops_dashboard_v1`).
- neue Suite: `test/test_core_ops_dashboard_seed.py`
- Gate-Runner-Contract erweitert:
  - `test_core_ops_dashboard_script_exists`

### Ergebnis
- kombiniertes Core-Ops-Dashboard als Seed fuer Release-Readiness Tracking vorhanden.
