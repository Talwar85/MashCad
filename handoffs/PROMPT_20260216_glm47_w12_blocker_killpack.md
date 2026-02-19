Du bist GLM 4.7 (UX/WORKFLOW + QA Integration Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollstaendig:
- `handoffs/HANDOFF_20260216_glm47_w11.md`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `test/harness/test_interaction_consistency.py`
- `test/test_ui_abort_logic.py`
- `test/test_error_ux_v2_integration.py`

Aktueller Ist-Zustand (durch Codex validiert):
- 6 UI-Suites laufen gruen: `116 passed`
- `test/harness/test_interaction_consistency.py` verursacht in dieser Umgebung weiterhin `Windows fatal exception: access violation`
- `scripts/gate_ui.ps1` klassifiziert das aktuell als `BLOCKED_INFRA` mit `Blocker-Type: ACCESS_VIOLATION`

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`

2) Erlaubte Scope-Dateien:
- `gui/**` (nur UX/Workflow, kein Kernel)
- `test/**`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `handoffs/**`

3) Keine Placeholders:
- Kein "spaeter" ohne Repro-Command.
- Kein "fertig" ohne messbares Ergebnis.

4) Ziel ist P0-Stabilitaet:
- Native Crash darf den UI-Bundle-Run nicht mehr killen.
- Wenn echter Root-Fix nicht erreichbar ist, MUSS eine robuste crash-containment Loesung geliefert werden.

-------------------------------------------------------------------------------
MISSION W12: BLOCKER KILLPACK
-------------------------------------------------------------------------------
Liefer ein grosses Paket mit Prioritaet auf dem `ACCESS_VIOLATION` Blocker in
`test/harness/test_interaction_consistency.py`.

Du hast zwei akzeptierte Endzustaende:
A) Vollfix: kein nativer Crash mehr, Tests laufen deterministisch.
B) Containment-Fix: Crash kann in Child-Prozess auftreten, killt aber NICHT den Haupt-Pytest-Lauf,
   wird reproduzierbar als Known-Blocker (xfail strict + Signatur) ausgewiesen.

A oder B ist Pflicht. Ohne A/B ist W12 nicht abgeschlossen.

-------------------------------------------------------------------------------
PAKET A (P0): Native Crash Containment fuer Interaction Tests
-------------------------------------------------------------------------------
Ziel:
- Kein harter Prozessabbruch des gesamten Pytest-Runs durch die 3 Drag-Tests.

Aufgaben:
1) Entkopple riskante Drag-Cases in isolierten Ausfuehrungspfad (Subprozess oder gleichwertige Isolation),
   sodass ein nativer Crash nicht den Hauptprozess beendet.
2) Erfasse Exit-Signatur reproduzierbar:
- ACCESS_VIOLATION (Windows code 0xC0000005 / -1073741819)
- VTK/OpenGL related blocker text
3) Mappe reproduzierbar auf blocker signature:
- `ACCESS_VIOLATION_INTERACTION_DRAG`
4) Testverhalten:
- Bei stabiler Ausfuehrung: normal asserten
- Bei reproduzierbarem nativen Infra-Crash: `pytest.xfail(strict=True, reason=...)`
- Kein `skip` fuer diese drei Cases

Abnahme:
- `pytest test/harness/test_interaction_consistency.py` terminiert ohne harten Runner-Crash.

-------------------------------------------------------------------------------
PAKET B (P0): Determinismus-Verbesserung fuer world_to_screen / drag path
-------------------------------------------------------------------------------
Ziel:
- Wahrscheinlichkeit fuer echten Pass statt xfail erhoehen.

Aufgaben:
1) Harness-Haertung:
- stabile readiness checks
- koordinaten mapping helper mit validierung
- event flush helper nach press/move/release
2) Minimiere flake-Trigger:
- feste wait/profile fuer drag
- konsistente focus/activation Reihenfolge
3) Dokumentiere im Code kurz, warum jede Stabilisierung noetig ist.

Abnahme:
- Mindestens ein Drag-Case laeuft stabil (PASS) ODER
- alle 3 Cases laufen als strict xfail ohne Runner-Crash.

-------------------------------------------------------------------------------
PAKET C (P1): UI Gate / Evidence W12 Synchronisierung
-------------------------------------------------------------------------------
Ziel:
- Gate + Evidence muessen den neuen Zustand korrekt berichten.

Aufgaben:
1) `scripts/gate_ui.ps1`:
- W12 Header
- saubere Einordnung von:
  - PASS
  - BLOCKED_INFRA (nur wenn wirklich infra-blockiert)
  - FAIL
- robustes Parsing fuer xfailed interaction suite
2) `scripts/generate_gate_evidence.ps1`:
- W12 Prefix default
- blocker signature und status class sauber in JSON/MD

Abnahme:
- Gate-Ausgabe konsistent mit Testrealitaet.

-------------------------------------------------------------------------------
PAKET D (P1): Regression Contracts fuer Crash-Containment
-------------------------------------------------------------------------------
Ziel:
- W12-Verhalten wird regressionssicher.

Aufgaben:
1) Neue/erweiterte Tests fuer:
- crash code mapping
- xfail strict contract
- kein skip fallback
- evidence fields fuer blocker signature
2) Sicherstellen, dass bestehende UX v2 und Selection/Discoverability Tests nicht regressieren.

-------------------------------------------------------------------------------
PFLICHT-VALIDIERUNG (alles ausfuehren)
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -vv

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_feature_commands_atomic.py

conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_ui_output_schema_w3 test/test_gate_runner_contract.py::TestGateRunnerContract::test_gate_ui_blocked_vs_fail_distinction test/test_gate_runner_contract.py::TestGateRunnerContract::test_exit_code_contract_ui_w3

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W12_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT (verbindlich)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w12_blocker_killpack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Blocker Resolution Matrix (Pflicht)
7. Review Template (ausgefuellt)
8. Naechste 5 priorisierte Folgeaufgaben (Owner + ETA)

Pflichtinhalt Matrix:
- Testname
- Vorher-Verhalten (W11)
- Nachher-Verhalten (W12)
- Runner-Crash ja/nein
- Status (PASS/XFAIL/FAIL)
- Blocker-Signatur (falls relevant)

No-Go:
- Keine widerspruechlichen Pass/Fail Zahlen
- Keine Behauptung "Blocker geloest" ohne reproduzierbaren Beleg
