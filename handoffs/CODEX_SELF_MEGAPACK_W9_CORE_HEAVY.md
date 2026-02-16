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
  - `-Profile full|parallel_safe|kernel_only`
  - `-DryRun`
  - `-JsonOut`
  - bestehender `-SkipUxBoundSuites` bleibt kompatibel.

### Verhalten
- `full`: kompletter Core-Gate-Stack
- `parallel_safe`: UX-gebundene Suite ausgeklammert (`test/test_feature_commands_atomic.py`)
- `kernel_only`: zusaetzlich nicht-kernelnahe Contract-Suiten ausgeklammert

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
- reproduzierbarer Profilvergleich fuer `full`, `parallel_safe`, `kernel_only`.

---

## Validierung

```powershell
conda run -n cad_env python -m pytest -q test/test_core_gate_profiles_contract.py test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_has_parallel_mode_parameter test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_core_output_schema test/test_gate_runner_contract.py::TestGateRunnerContract::test_exit_code_contract_core test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_has_core_budget_parameter_contract test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_budget_script_has_stable_defaults
conda run -n cad_env python -m pytest -q test/test_core_profile_matrix_seed.py test/test_core_gate_profiles_contract.py test/test_gate_runner_contract.py::TestGateRunnerContract::test_core_profile_matrix_script_exists

powershell -ExecutionPolicy Bypass -File scripts/check_core_gate_budget.ps1 -CoreProfile parallel_safe
powershell -ExecutionPolicy Bypass -File scripts/gate_all.ps1 -CoreProfile parallel_safe -ValidateEvidence
```

**Observed:**
- Contract-Tests gruen
- Matrix-Seed-Tests gruen
- Budget-Check gruen (`parallel_safe`)
- `gate_all` mit `-CoreProfile parallel_safe -ValidateEvidence` -> `ALL GATES PASSED` (UI als `BLOCKED_INFRA`, nicht FAIL)

---

## Naechste Grosspakete (W9 Folge)

1. **C-W9E (P0): Gate Summary JSON Contract v1**
- `gate_all.ps1` und `gate_ui.ps1` bekommen optionales JSON-Output mit stabiler Schema-Version.

2. **C-W9F (P1): Core Red-Flag Profile**
- dediziertes Profil fuer Showstopper/CH-010 mit schnellen Fail-Fast-Checks.

3. **C-W9G (P1): Core-Gate Trend Capture**
- automatischer Laufvergleich (last-good vs current) fuer Passrate/Dauer pro Profil.
