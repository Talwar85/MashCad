Du bist `AI-LARGE-K-RELEASE-OPS` auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260217_ai_largeK_w28_release_ops_acceleration_megapack.md`

## Ziel
W29 Release Ops Timeout-Proof: Gate- und Contract-Landschaft robust gegen lange Laufzeiten und Umgebungsnoise machen.

## Harte Regeln
1. Keine kosmetischen-only Aenderungen.
2. Kein `skip`/`xfail`.
3. Keine Edits ausserhalb Scope.

## Scope
- `scripts/gate_fast_feedback.ps1`
- `scripts/preflight_ui_bootstrap.ps1`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `scripts/validate_gate_evidence.ps1`
- `test/test_gate_runner_contract.py`
- `test/test_gate_evidence_contract.py`

## NO-GO
- `gui/**`
- `modeling/**`
- `config/feature_flags.py`

## Aufgaben
### 1) Timeout-feste Contract-Tests
- W28/W29 Contract-Tests so strukturieren, dass sie reproduzierbar schnell laufen.
- Keine indirekten rekursiven Gate-Aufrufe.

### 2) Preflight Diagnostik schaerfen
- `BLOCKED_INFRA` Klassifikation stabil.
- `OPENCL_NOISE` sauber von echten Fehlern trennen.

### 3) Evidence-Validator Härtung
- Robuste Behandlung alter und neuer payloads.
- Semantische Checks auf suite counts und completion ratio.

### 4) Messbare Speed-Ziele dokumentieren
- ui_ultraquick, ops_quick, preflight mit Vorher/Nachher-Werten.

## Pflicht-Validierung
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_ultraquick
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ops_quick
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestFastFeedbackProfileDefinitionsW28 -v
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestPreflightBootstrapW28 -v
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestDeliveryMetricsW28 -v
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestEvidenceValidationW28 -v
conda run -n cad_env python -m pytest -q test/test_gate_evidence_contract.py -v
```

## Abgabe
Datei:
- `handoffs/HANDOFF_20260217_ai_largeK_w29_release_ops_timeoutproof.md`

Pflichtinhalte:
1. Geaenderte Dateien + Grund
2. Laufzeitvergleich
3. Testresultate
4. Restrisiken

