Du bist `AI-SMALL-3` auf Branch `feature/v1-ux-aiB`.

## Ziel (kleines Paket, hoher Nutzen)
Baue einen **schnellen Feedback-Gate** für kurze Iterationszyklen, damit nicht immer auf lange Suites gewartet werden muss.

Dieses Paket ist bewusst klein (ca. 30-60 min) und kollidiert nicht mit den großen W26-E/W26-F-Paketen.

## Scope (nur diese Bereiche)
- `scripts/**`
- `test/test_gate_runner_contract.py`
- optional: neue Testdatei `test/test_gate_fast_feedback_contract.py`
- optional: kurze Doku in `roadmap_ctp/**`

## NO-GO
- Keine Änderungen in `gui/**`
- Keine Änderungen in `modeling/**`
- Keine Änderungen an bestehenden großen Prompt/Handoff-Dateien
- Kein Skip/XFail hinzufügen um rote Tests zu verstecken

## Aufgaben

### 1) Neuer Script-Runner: `scripts/gate_fast_feedback.ps1`
Erstelle einen leichten Runner für schnelle lokale Verifikation.

Pflicht:
1. Script existiert und ist aufrufbar via:
   - `powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1`
2. Konfigurierbare Modi:
   - `-Profile smoke` (Default)
   - `-Profile ui_quick`
   - `-Profile core_quick`
3. Einheitliches Output-Schema analog anderer Gates:
   - Header
   - Duration
   - Test counts
   - Status
   - Exit Code
4. Exit-Code-Vertrag:
   - `0` bei PASS
   - `1` bei FAIL
5. Optionaler `-JsonOut` Support (maschinell lesbar, kleines Schema).

### 2) Schlanke Testauswahl je Profil
Vorgabe (anpassbar nur mit guter Begründung):
- `smoke`:
  - `test/test_workflow_product_leaps_w25.py`
  - `test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_all_script_exists`
- `ui_quick`:
  - `test/test_ui_abort_logic.py`
  - `test/test_discoverability_hints_w17.py`
- `core_quick`:
  - `test/test_feature_error_status.py`
  - `test/test_tnp_v4_feature_refs.py`

Wichtig:
- Kein stilles Weglassen bei Fehlern.
- Fehlende Datei/Test muss als FAIL sichtbar werden.

### 3) Contract-Tests ergänzen
Ergänze schnelle Contract-Checks:
1. Existenz von `scripts/gate_fast_feedback.ps1`
2. Output enthält `Status:` und `Exit Code:`
3. `-Profile smoke` wird akzeptiert
4. ungültiges Profil führt zu sauberem Fehlerstatus

### 4) Mini-Doku
Kurze Ergänzung in `roadmap_ctp/05_release_gates_and_quality_model.md`:
- Zweck von `gate_fast_feedback`
- empfohlene Aufrufreihenfolge für schnelle Loops

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile test/test_gate_runner_contract.py
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py -k "fast_feedback or gate_all_script_exists" -v
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile smoke
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
```

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_small3_w26_fastfeedback_gate.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (Kommandos + Ergebnisse)
5. Breaking Changes / Rest-Risiken
6. Nächste 3 Folgeaufgaben

Zusätzlich:
- Commit-Hash + Commit-Message
- 3 Zeilen „Wie das Wartezeiten reduziert“

