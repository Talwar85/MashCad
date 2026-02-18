Du bist GLM 4.7 (UX/WORKFLOW + QA Integration Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollstaendig:
- `handoffs/HANDOFF_20260216_glm47_w12_blocker_killpack.md`
- `test/harness/test_interaction_consistency.py`
- `test/harness/test_interaction_drag_isolated.py`
- `test/harness/crash_containment_helper.py`
- `test/test_crash_containment_contract.py`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`

Aktueller Ist-Stand (durch Codex validiert):
- Main Suite: `test/harness/test_interaction_consistency.py` => `1 passed, 3 skipped`
- Isolated Drag Suite: kann weiterhin mit native `ACCESS_VIOLATION` crashen
- UI Gate laeuft stabil, aber echte Drag-Testbarkeit ist noch nicht erreicht

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`

2) Fokus-Dateien:
- `test/harness/**`
- `test/test_crash_containment_contract.py`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `handoffs/**`

3) Kein kosmetischer Workaround:
- Die drei Drag-Tests duerfen am Ende NICHT `skip` sein.
- Ziel ist "testbar", nicht "ausblenden".

4) Keine unbewiesenen Claims:
- Jede Aussage im Handoff mit Command + Result belegen.

-------------------------------------------------------------------------------
MISSION W13: UNSKIP + RETEST (P0)
-------------------------------------------------------------------------------
Ziel:
Die 3 Drag-Tests muessen wieder testbar sein und im regulaeren Testfluss laufen,
ohne den gesamten Runner durch native Crashes zu zerstoeren.

Betroffene Tests:
- `test_circle_move_resize`
- `test_rectangle_edge_drag`
- `test_line_drag_consistency`

Akzeptierte Endzustaende:
A) Vollfix:
- Tests laufen direkt stabil (PASS oder reproduzierbar XFAIL strict)
- Kein Runner-Crash

B) Contained Runnable:
- Tests laufen als echte Testausfuehrung im Hauptlauf (nicht skip),
  aber intern ueber robusten Isolation-Mechanismus (Subprozess)
- Bei native crash: strict xfail mit blocker signature
- Kein Runner-Crash

A oder B ist Pflicht. "skip" ist NICHT erlaubt.

-------------------------------------------------------------------------------
PAKET A (P0): Unskip der 3 Drag-Tests
-------------------------------------------------------------------------------
Aufgaben:
1) Entferne `@pytest.mark.skip` fuer die 3 Drag-Tests.
2) Stelle sicher, dass jeder Test ausgefuehrt wird.
3) Falls Isolation noetig ist, kapsle pro Test in Subprozess und mappe Ergebnis sauber:
- PASS bei erfolgreichem Lauf
- XFAIL(strict=True) bei reproduzierbarer infra-crash signatur
- FAIL bei echten Logikfehlern

Pflicht-Signatur:
- `ACCESS_VIOLATION_INTERACTION_DRAG`

-------------------------------------------------------------------------------
PAKET B (P0): Containment robust und verifizierbar
-------------------------------------------------------------------------------
Aufgaben:
1) `crash_containment_helper.py` wirklich produktiv verwenden (nicht nur liegen lassen).
2) Exit-Code / Output-Mapping robust machen fuer:
- Windows access violation (0xC0000005 / -1073741819)
- sonstige fatal/native crashes
3) Absichern, dass bei crash der Parent-Pytest-Prozess weiterlaeuft.

-------------------------------------------------------------------------------
PAKET C (P1): Contracts und Gate-Abgleich
-------------------------------------------------------------------------------
Aufgaben:
1) `test/test_crash_containment_contract.py` aktualisieren:
- Contract MUSS pruefen, dass die 3 Tests NICHT skipped sind.
- Contract MUSS pruefen, dass Ausfuehrungspfad testbar ist (pass/xfail/fail, aber nicht skip).
2) `scripts/gate_ui.ps1` und `scripts/generate_gate_evidence.ps1` auf W13 Stand:
- korrekte Einordnung fuer xfailed vs skipped vs errors
- keine irrefuehrenden counts

-------------------------------------------------------------------------------
PFLICHT-VALIDIERUNG
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -vv

conda run -n cad_env python -m pytest -q test/test_crash_containment_contract.py -vv

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_feature_commands_atomic.py

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W13_20260216
```

W13 Mindestakzeptanz:
- `test_interaction_consistency.py`: keine `skipped` fuer die 3 Drag-Tests
- Kein nativer Runner-Absturz

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w13_unskip_retest.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Unskip Resolution Matrix (Pflicht)
7. Review Template (ausgefuellt)
8. Naechste 5 priorisierte Folgeaufgaben (Owner + ETA)

Pflicht in Matrix:
- Testname
- W12 Status
- W13 Status
- Skip entfernt (ja/nein)
- Runner-Crash (ja/nein)
- Ergebnis (PASS/XFAIL/FAIL)
- Blocker-Signatur (falls XFAIL)

No-Go:
- Skip bleibt bestehen
- Runner crash wird nicht isoliert
- Handoff ohne reproduzierbare Commands
