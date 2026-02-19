Du bist `AI-LARGE-K-RELEASE-OPS` auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses W28 Release-Ops Acceleration Megapack.
Fokus: schnellere Gates, keine rekursiven Runner-Fallen, bessere Diagnostik.

## Harte Regeln
1. Kein `skip`/`xfail` als Ausweg.
2. Kein stilles Ignorieren von timeouts.
3. Keine Placeholders.
4. Keine Edits ausserhalb Scope.
5. Keine History-Manipulation.

## Erlaubter Scope
- `scripts/gate_fast_feedback.ps1`
- `scripts/preflight_ui_bootstrap.ps1`
- `scripts/gate_ui.ps1`
- `scripts/gate_core.ps1`
- `scripts/generate_gate_evidence.ps1`
- `scripts/validate_gate_evidence.ps1`
- `test/test_gate_runner_contract.py`
- `test/test_gate_evidence_contract.py`
- optionale Doku in `roadmap_ctp/`

## NO-GO
- `gui/**`
- `modeling/**`
- `config/feature_flags.py`

## Arbeitspaket
### Task 1: Fast-Feedback v3
Baue Profile so, dass sie wirklich schnelle Signale liefern:
1. Kein Profil darf die komplette Contract-Datei unnoetig aufrufen.
2. Keine Rekursion (Gate testet sich nicht indirekt selbst).
3. `ui_ultraquick` Ziel < 15s lokal.
4. `ops_quick` Ziel < 12s lokal.

### Task 2: Preflight Hardening
`preflight_ui_bootstrap.ps1` verbessern:
1. Klare BLOCKED_INFRA-Klassifikation.
2. Konsistente blocker_type/root-cause Ausgabe.
3. Schutz gegen file-lock/opencl-noise.
4. Runtime-Ziel < 25s (best effort, mit Messwerten).

### Task 3: Gate Evidence Quality
Erweitere Evidence-Qualitaet:
1. delivery_metrics konsistent gefuellt.
2. Schema validation robust bei alten und neuen payloads.
3. Fehlerausgaben so, dass Ursache sofort sichtbar ist.

### Task 4: Contract Test Expansion
Mindestens 25 neue Assertions fuer:
1. Profil-Definitionen
2. Timeout-Verhalten
3. Blocker-Klassifikation
4. Evidence-Contract inkl. optional fields

## Pflicht-Validierung
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_ultraquick
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ops_quick
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py test/test_gate_evidence_contract.py -v
```

## Nachweispflicht
1. Vorher/Nachher Laufzeiten je Profil.
2. Geaenderte Dateien + Grund.
3. Exakte Testresultate.
4. Offene technische Schulden.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeK_w28_release_ops_acceleration_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 5 Folgeaufgaben

