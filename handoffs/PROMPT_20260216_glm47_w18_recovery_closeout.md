Du bist GLM 4.7 (UX/Workflow Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_glm47_w17_titanpack.md`
- `handoffs/PROMPT_20260216_glm47_w17_titanpack_no_skip_gate.md`
- `roadmap_ctp/ROADMAP_STATUS_20260216_codex.md`

WICHTIG:
W17 wurde als "complete" gemeldet, ist aber technisch noch nicht gate-ready.
Dieses Paket ist ein Recovery/Closeout fuer echte Luecken und Blocker.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth:
- Nur `feature/v1-ux-aiB`.

2) No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) No fake done:
- Kein "DONE" ohne Dateidiff + reproduzierbaren Testproof.

4) Gateway policy:
- `scripts/gate_ui.ps1` darf NICHT geskippt werden.
- Timeout/Blocker -> Fix + Retry, nicht "skip".

-------------------------------------------------------------------------------
W18 RECOVERY PAKETE (REAL FAILURE DRIVEN)
-------------------------------------------------------------------------------
Gesamt: 30 Punkte
Akzeptanz:
- Minimum 18/30 (60%)
- Ziel 24+/30 (80%+)

PAKET R1 (10 Punkte) - W17 Blocker-Kill: Failures auf Gruen bringen
Pflicht:
1. `test/test_discoverability_hints_w17.py`:
- 5 aktuelle Fails beheben (API-Mismatch, falsche Annahmen, Kontextlogik).
2. `test/test_feature_controller.py`:
- Fixture-Error (`mock_mw` in StateTransition-Tests) beheben.
3. `test/test_export_controller.py`:
- 3 Fails + 1 Error beheben (`QMessageBox` parent handling, `qtbot` fixture usage).
4. `test/harness/test_interaction_direct_manipulation_w17.py`:
- ImportError beheben (`Ellipse2D`/`Polygon2D` existieren nicht in `sketcher.__init__`).

Abnahme:
- Diese vier Suites laufen ohne Error/Fails.

PAKET R2 (8 Punkte) - Discoverability API/Behavior Vertrag stabilisieren
Pflicht:
1. Einheitliche Tutorial-API:
- Entweder bestehende API konsolidieren (`_tutorial_mode_enabled` + `set_tutorial_mode`)
- oder Kompatibilitaetsalias sauber einfuehren.
2. Navigation-Hints:
- Kontextabhaengige Unterschiede fuer sketch / direct edit / peek verifizierbar.
3. Tests:
- Keine falschen "private attr"-Annahmen mehr ohne Produktvertrag.

Abnahme:
- W17 Discoverability Tests sind behavior-proof und gruen.

PAKET R3 (6 Punkte) - Controller-Integrationsrealitaet
Pflicht:
1. Wenn `ExportController`/`FeatureController` bleiben:
- minimale, echte Integration in `gui/main_window.py` (Init + definierte Delegation) ODER
- klar dokumentierter De-Scope mit Entfernen ungenutzter Controller-Claims.
2. Tests muessen den realen Integrationsweg pruefen (nicht nur isolated mock loops).

Abnahme:
- Keine "Controller existiert nur im Test"-Sackgasse.

PAKET R4 (6 Punkte) - Gate/Evidence Konsistenz W18
Pflicht:
1. `scripts/gate_ui.ps1` auf W18 Scope abstimmen.
2. `scripts/generate_gate_evidence.ps1` auf W18 Scope abstimmen.
3. W18 Evidence erzeugen.

Abnahme:
- UI-Gate laeuft und liefert verwertbares Ergebnis (nicht BLOCKED_INFRA).

-------------------------------------------------------------------------------
EMPFOHLENE AUSFUEHRUNGSREIHENFOLGE (ANTI-TIMEOUT)
-------------------------------------------------------------------------------
1) Targeted Recovery First
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py test/test_discoverability_hints_w17.py test/harness/test_interaction_direct_manipulation_w17.py -v
```

2) Core W17 bundles
```powershell
conda run -n cad_env python -m pytest -q test/test_sketch_controller.py test/test_error_ux_v2_e2e.py -v
```

3) Gateway (mandatory, no skip)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

4) Evidence
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W18_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w18_recovery_closeout.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard
7. Claim-vs-Proof Matrix
8. Offene Punkte + naechste 6 Aufgaben

-------------------------------------------------------------------------------
DELIVERY SCORECARD (PFLICHT)
-------------------------------------------------------------------------------
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| R1 | 10 | ... | ... |
| R2 | 8 | ... | ... |
| R3 | 6 | ... | ... |
| R4 | 6 | ... | ... |
| Total | 30 | ... | ... |
| Completion Ratio | X/30 = YY% | MUST BE >= 60% | |

No-Go:
- Completion Ratio < 60%
- UI-Gate skipped
- BLOCKED_INFRA offen ohne Root-Cause-Fix
- "DONE" ohne reproduzierbare Command-Outputs
