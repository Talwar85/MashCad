Du bist GLM 4.7 (UX/WORKFLOW Reliability Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollstaendig:
- `handoffs/HANDOFF_20260216_glm47_w14_megapack.md`
- `handoffs/CODEX_VALIDATION_MODE_PLAYBOOK_20260216.md`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_error_ux_v2_integration.py`
- `test/test_crash_containment_contract.py`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`

Kontext (bereits von Codex verifiziert):
- W14 ist technisch weitgehend gruen, aber aktuell nur **B (ready-with-fixups)**.
- Grund: mehrere schwache Tests und ueberzogene Claims.

-------------------------------------------------------------------------------
MISSION: W14-HARDLINE FIXUP (EXPECTATION HARDENING)
-------------------------------------------------------------------------------
Ziel:
W14 von **B -> A (merge-ready)** heben.
Keine neuen Themen starten, bevor die Qualitaetsluecken aus W14 geschlossen sind.

-------------------------------------------------------------------------------
HARTE REGELN (NICHT VERHANDELBAR)
-------------------------------------------------------------------------------
1) Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`

2) Erlaubte Fokus-Pfade:
- `gui/**`
- `test/**`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `handoffs/**`

3) Verbotene "Fake-Assertions" in neuen/geaenderten Tests:
- `assert <obj> is not None` als Hauptnachweis
- `assert hasattr(...)` als Hauptnachweis
- `assert callable(...)` als Hauptnachweis
- `assert <signal> is not None` statt Emissionsnachweis

4) Jede neue/geaenderte Regression muss enthalten:
- klaren Pre-State,
- Action,
- Post-State,
- mindestens 1 negative/guard assertion (Regression-Schutz).

5) Keine ueberschriebenen Claims:
- Wenn keine Produktivdatei (`gui/**`) geaendert wurde, darfst du NICHT "Stream komplett implementiert" claimen.

6) Keine unvollstaendige Validation:
- Alle Pflicht-Commands muessen wirklich laufen.
- Im Handoff muessen reale Resultate stehen (keine TBD, keine Schaetzwerte ohne Command).

-------------------------------------------------------------------------------
P0 FIXUP-BLOCK A: Abort-Tests von "Weak" auf "Behavior-Proof"
-------------------------------------------------------------------------------
Pflicht:
1) Ersetze schwache Abort-Tests durch harte Zustandsassertions.
2) Speziell beheben:
- `test_escape_clears_direct_edit_drag` darf NICHT nur `assert editor is not None` enthalten.
3) Wenn aktuelles Produktverhalten den Test nicht erfuellt:
- Produktionsfix in `gui/sketch_editor.py` implementieren.

Mindestnachweis:
- Direct-edit drag state: `True -> False` auf Escape/Abort (oder begruendetes alternatives Contract-Verhalten mit explizitem Test).

-------------------------------------------------------------------------------
P0 FIXUP-BLOCK B: Discoverability-Tests von API-Pruefung auf echte Interaktion
-------------------------------------------------------------------------------
Pflicht:
1) Ersetze `hasattr/callable`-Pseudo-Tests durch echte Verhaltenstests.
2) Signaltests muessen reale Emission + Payload pruefen (z. B. Space press/release -> events `[True, False]`).
3) Cooldown-/Priority-Tests muessen stateful verifiziert werden (nicht nur Funktionsaufruf).

-------------------------------------------------------------------------------
P0 FIXUP-BLOCK C: Error UX v2 Claims auf echte End-to-End-Nachweise schraenken
-------------------------------------------------------------------------------
Pflicht:
1) Tests muessen echte Flows verifizieren, nicht nur Objektkonstruktion.
2) Falls "End-to-End" behauptet wird, muss mindestens ein kompletter Ablauf von Trigger -> Notification -> Statusbar validiert sein.
3) Ueberzogene Begriffe im Handoff entfernen, falls kein entsprechender Produktionscode geaendert wurde.

-------------------------------------------------------------------------------
P1 FIXUP-BLOCK D: Handoff-Qualitaet auf Audit-Niveau
-------------------------------------------------------------------------------
Pflicht:
1) Neues Handoff muss eine **Claim-vs-Proof Matrix** enthalten:
- Claim
- Geaenderte Datei(n)
- Repro-Command
- Ergebnis
- Rest-Risiko

2) Pflichtsektion "Rejected Claims":
- Welche alten W14-Claims waren zu stark?
- Wie wurden sie korrigiert?

3) Pflichtsektion "Validation Completeness":
- Vollstaendige Command-Liste + reale Outputs + Laufzeiten.

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
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W14_FIXUP_20260216
```

-------------------------------------------------------------------------------
ABNAHMEKRITERIEN (A-RATING ODER REWORK)
-------------------------------------------------------------------------------
A-Rating nur wenn alle Punkte erfuellt:
1. Keine verbotenen Fake-Assertions in neu/geaenderten W14-Fixup-Tests.
2. Alle Pflicht-Commands gruen/reproduzierbar (Hygiene darf separat failen, muss aber klar ausgewiesen sein).
3. Handoff-Claims streng auf geaenderten Code und verifizierte Runs begrenzt.
4. Mindestens 1 reale Produktivcode-Verbesserung in `gui/**`, falls ein Verhalten vorher nicht beweisbar war.

Sonst automatisch: REWORK.

-------------------------------------------------------------------------------
RUECKGABEFORMAT (VERBINDLICH)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w14_fixup_hardline.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Claim-vs-Proof Matrix (Pflicht)
7. Rejected Claims + Corrections (Pflicht)
8. W14->A Readiness Checkliste (Pflicht)
9. Naechste 5 priorisierte Folgeaufgaben (Owner + ETA)

No-Go:
- Nicht reproduzierbare Zahlen
- Unbelegte "complete" Claims
- Fake-Assertions statt Verhaltensnachweis
- Nur Testnamen hinzufuegen ohne echten Contract-Nutzen
