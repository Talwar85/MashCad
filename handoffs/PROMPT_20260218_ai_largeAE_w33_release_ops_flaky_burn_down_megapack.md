# PROMPT_20260218_ai_largeAE_w33_release_ops_flaky_burn_down_megapack

Du bist AI-LARGE-AE (Release Ops + Flaky Burn-Down Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere ein grosses Delivery-Beschleunigungspaket mit Fokus auf:
1. gate-profile Belastbarkeit,
2. flaky test burn-down,
3. timeout-proof execution,
4. strictere workspace hygiene enforcement.

## Scope
Erlaubte Dateien:
- `scripts/gate_fast_feedback.ps1`
- `scripts/preflight_ui_bootstrap.ps1`
- `scripts/gate_all.ps1`
- `scripts/hygiene_check.ps1`
- `scripts/validate_gate_evidence.ps1`
- `test/test_gate_runner_contract.py`
- `test/test_gate_evidence_contract.py`
- `test/test_discoverability_hints.py` (nur falls fuer flaky fix zwingend)
- `test/test_ui_abort_logic.py` (nur falls fuer flaky fix zwingend)
- neue ops/flaky tests unter `test/` nach Bedarf

No-Go:
- `modeling/**`
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`

## Harte Regeln
1. Keine neuen `skip` oder `xfail` als Timeout-Workaround.
2. Kein Gate-Schoenrechnen durch weniger Coverage ohne Dokumentation.
3. Keine `.bak` oder `temp_*` Dateien erzeugen.
4. Jede Script-Aenderung braucht Contract-Test.

## EPIC AE1 - Gate Profile Realism v2 (P0)
Ziel: Profile sind schnell, aber aussagekraeftig.

Aufgaben:
1. Profile sauber staffeln:
- ultraquick
- quick
- core
- recovery
- optional smoke
2. Fuer jedes Profil:
- klares Target in Sekunden
- explizite Suite-Liste
- Resultat mit pass/fail/skip/error Countern
3. JSON evidence Felder konsistent halten.

## EPIC AE2 - Flaky Burn-Down (P0)
Ziel: Wiederholbarkeit fuer kritische UI-Smokes verbessern.

Aufgaben:
1. Identifiziere mindestens 2 flaky Kandidaten.
2. Behebe Root Cause (timing/focus/state leakage), nicht nur retries erhoehen.
3. Nachweis ueber wiederholte Runs (mind. 5x) fuer betroffene Tests.

## EPIC AE3 - Timeout-proof Run Strategy (P1)
Ziel: keine "skip wegen timeout"-Kultur.

Aufgaben:
1. Definiere reproduzierbare Chunk-Strategie fuer laengere UI-Suiten.
2. Scripts sollen bei Blockern eindeutig klassifizieren statt haengen.
3. Doku im Handoff: empfohlene Reihenfolge fuer lokale Ausfuehrung.

## EPIC AE4 - Hygiene Gate Hardening (P1)
Ziel: Backup/temp/debug Artefakte frueh sichtbar und bei strict mode blocker.

Aufgaben:
1. `hygiene_check.ps1` deckt kritische Artefakte robust ab.
2. Strict-Mode Verhalten klar: Verletzungen => fail.
3. Contract-Tests pruefen Output-Schema und strict semantics.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py test/test_gate_evidence_contract.py
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts/hygiene_check.ps1
powershell -ExecutionPolicy Bypass -File scripts/hygiene_check.ps1 -FailOnUntracked
```

Falls fuer Flaky-Nachweis noetig, zusaetzlich:
```powershell
for /l %i in (1,1,5) do conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate
for /l %i in (1,1,5) do conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

## Akzeptanzkriterien
1. Mindestens 1 echte Ops-Verbesserung im Gate-Verhalten.
2. Mindestens 2 flaky Verbesserungen mit Wiederholungsnachweis.
3. Keine neuen skips/xfails.
4. Pflichtvalidierung komplett gruen.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeAE_w33_release_ops_flaky_burn_down_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
