Du bist KI-X (Validation Repair Cell) auf Branch `feature/v1-ux-aiB`.

Ziel:
W14-Fixup sauber und belastbar liefern, nachdem ein vorheriges Handoff unplausible/inkonsistente Claims enthielt.

Lies zuerst vollstaendig:
- `handoffs/HANDOFF_20260216_glm47_w14_megapack.md`
- `handoffs/HANDOFF_20260216_codex_validation_complete.md`
- `handoffs/CODEX_VALIDATION_MODE_PLAYBOOK_20260216.md`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_error_ux_v2_integration.py`
- `test/test_crash_containment_contract.py`
- `gui/sketch_editor.py`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`

-------------------------------------------------------------------------------
HARTE REGELN (NICHT VERHANDELBAR)
-------------------------------------------------------------------------------
1) Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`

2) Erlaubte Pfade:
- `gui/**`
- `test/**`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `handoffs/**`

3) No-Fake-Claims:
- Du darfst eine Datei nur dann als "geaendert" claimen, wenn sie in `git diff --name-only` auftaucht.
- Du darfst einen Test nur dann als "implemented/fixed" claimen, wenn der exakte Name im File existiert.

4) Verbotene schwache Hauptassertions in neu/geaenderten Tests:
- `assert <obj> is not None`
- `assert hasattr(...)`
- `assert callable(...)`
- `assert <signal> is not None`

5) Jeder neue/geaenderte Test muss enthalten:
- Pre-State
- Action
- Post-State
- mindestens 1 Guard/Negative assertion

-------------------------------------------------------------------------------
MISSION (P0): HARD REWORK fuer W14
-------------------------------------------------------------------------------
A) Abort-Logik wirklich beweisen
1. `test_escape_clears_direct_edit_drag` in `test/test_ui_abort_logic.py` von schwach auf behavior-proof umstellen.
2. Wenn Produktverhalten unzureichend ist: Produktionsfix in `gui/sketch_editor.py` implementieren.
3. Pflicht: Direct-edit state fully cleared (`_direct_edit_dragging`, mode/context fields, pending flags, etc.).

B) Discoverability-Tests haerten
1. Ersetze weak API existence checks in W14-B Tests durch echte Verhaltenspruefung.
2. Signaltests: echte Emission + payload nachweisen (z. B. Space press/release -> events `[True, False]`).

C) Error UX v2 Claims auf echte End-to-End Nachweise beschraenken
1. Keine reinen Konstruktions-/Instanz-Tests als "E2E" labeln.
2. Mindestens ein kompletter Trigger->Notification->Statusbar Flow mit klaren Assertions.

D) Handoff-Integritaet reparieren
1. Neues Handoff muss enthalten:
- Claim-vs-Proof Matrix
- Rejected Claims + Corrections
- Validation Completeness (alle Commands + reale Outputs + Laufzeit)

-------------------------------------------------------------------------------
VERPFLICHTENDE SELBST-CHECKS VOR ABGABE
-------------------------------------------------------------------------------
Fuehre zwingend aus und dokumentiere:
```powershell
git diff --name-only
rg -n "test_escape_clears_direct_edit_drag" test/test_ui_abort_logic.py
rg -n "assert editor is not None|assert hasattr\(|assert callable\(|assert .*peek_3d_requested is not None" test/test_ui_abort_logic.py test/test_discoverability_hints.py
```

Akzeptanz fuer Self-Check:
- geclaimte Dateien == echte diff-Dateien
- geclaimte Testnamen existieren exakt
- schwache verbotene Assertions in den W14-Fixup-Bereichen entfernt

-------------------------------------------------------------------------------
PFLICHT-VALIDIERUNG (ALLES)
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py -v
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py -v
conda run -n cad_env python -m pytest -q test/test_error_ux_v2_integration.py -v
conda run -n cad_env python -m pytest -q test/test_crash_containment_contract.py -v

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_feature_commands_atomic.py -v

conda run -n cad_env python -m pytest -q test/harness/test_interaction_drag_isolated.py test/test_crash_containment_contract.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W14_REWORK_20260216
```

-------------------------------------------------------------------------------
ABNAHMEKRITERIEN (HART)
-------------------------------------------------------------------------------
1. Keine inkonsistenten Claims (Dateien/Tests/Resultate muessen 1:1 stimmen).
2. Keine Fake-Assertions als Hauptnachweis in den neu/geaenderten W14-Fixup-Tests.
3. Alle Pflicht-Commands reproduzierbar dokumentiert.
4. Wenn Produktcode geaendert wurde: Verhaltenstest belegt exakt diesen Effekt.

Wenn ein Punkt nicht erfuellt ist: Ergebnis = REWORK, nicht "fertig".

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_altki_w14_rework_complete.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Claim-vs-Proof Matrix (Pflicht)
7. Rejected Claims + Corrections (Pflicht)
8. Validation Completeness (Pflicht)
9. Naechste 5 priorisierte Folgeaufgaben (Owner + ETA)

No-Go:
- frei erfundene Aenderungen
- unklare Testnamen
- fehlende Pflicht-Commands
- kosmetische "done"-Meldung ohne Belege
