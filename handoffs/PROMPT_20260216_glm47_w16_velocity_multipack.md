Du bist GLM 4.7 (UX/Workflow Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_altki_w14_rework_complete.md`
- `handoffs/HANDOFF_20260216_codex_validation_complete.md`
- `roadmap_ctp/03_workstreams_masterplan.md`
- `roadmap_ctp/04_workpackage_backlog.md`
- `roadmap_ctp/ROADMAP_STATUS_20260216_codex.md`

-------------------------------------------------------------------------------
MISSION W16: VELOCITY MULTIPACK (THROUGHPUT FIRST)
-------------------------------------------------------------------------------
Ziel:
Keine Mini-Lieferung mehr. Pro Rueckgabe muessen mehrere Arbeitspakete real
und testbar abgeschlossen werden. Validation-Zeit darf nicht wieder 4x hoeher
sein als Implementierungs-Fortschritt.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch-Wahrheit:
- Arbeite ausschliesslich auf `feature/v1-ux-aiB`.

2) No-Go Edits:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) Pflicht:
- Jede Claim braucht Proof (Datei + Test/Gate-Command + Ergebnis).
- Kein Placeholder-Text, kein "done" ohne reproduzierbaren Nachweis.

4) Mindest-Lieferquote:
- Deine Rueckgabe ist nur gueltig, wenn mind. 33% des Gesamtpakets fertig sind.
- Zielquote fuer "stark" ist 50%+ in einer Lieferung.
- Unter 33% gilt die Lieferung als FAIL (automatisch nachbessern statt abgeben).

-------------------------------------------------------------------------------
W16 PAKETE (GEWICHTET)
-------------------------------------------------------------------------------
Gesamt: 24 Punkte
Akzeptanz-Schwelle:
- Minimum: 8 Punkte (33%)
- Ziel: 12 Punkte (50%)

PAKET A (6 Punkte) - SU-004/SU-010 Interaction Consistency Erweiterung
- Mindestens 2 neue direkte Manipulationsfaelle in Harness/Regression.
- Cursor/drag/select Verhalten konsistent fuer diese Faelle.
- Keine neuen skip/xfail fuer Kernfaelle.

PAKET B (6 Punkte) - SU-009 Discoverability v2 Produktionsreife
- Hint/Overlay Verhalten fuer Sketch-Navigation robust (anti-spam + context aware).
- Mindestens 1 echter Produktfix in `gui/sketch_editor.py` oder zugehoerigem GUI-Layer.
- Behavior-Proof-Tests statt reine API-Existenz-Pruefungen.

PAKET C (6 Punkte) - UX-003 Error UX v2 Konsistenz komplett
- Tooltip + Notification + Statusbar konsistent fuer WARNING/BLOCKED/CRITICAL/ERROR.
- End-to-End Testfluss Trigger -> UI in Tests nachweisen.
- Mapping-Regression gegen versehentliche Prioritaetsaenderungen absichern.

PAKET D (6 Punkte) - AR-004 MainWindow Entlastung (GUI-Layer)
- Klar trennbare UI-Orchestrierung aus `gui/main_window.py` extrahieren.
- Keine Verhaltensaenderung ausser klar dokumentierte UX-Fixes.
- Regressionstests fuer extrahierte Flows.

-------------------------------------------------------------------------------
DELIVERY-REGELN (WICHTIG)
-------------------------------------------------------------------------------
1) Arbeite in grossen Chunks:
- Fertige mindestens 2 Pakete komplett ODER 1 komplett + 2 teilweise.

2) Stop-and-ship Regel:
- Wenn du 12+ Punkte erreicht hast, liefere sofort handoff + commit statt weiter
  zu streuen.

3) Qualität vor Claim:
- Unklare Teilpakete als "PARTIAL" markieren, nicht als "DONE".

-------------------------------------------------------------------------------
PFLICHT-VALIDIERUNG
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py -v

conda run -n cad_env python -m pytest -q test/harness/test_interaction_drag_isolated.py test/test_crash_containment_contract.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

Falls `scripts/generate_gate_evidence.ps1` angepasst wurde, zusaetzlich:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W16_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT (STRICT)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w16_velocity_multipack.md`

Pflichtstruktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard (Pflicht)
7. Claim-vs-Proof Matrix (Pflicht)
8. Open Items + naechste 5 Aufgaben

-------------------------------------------------------------------------------
DELIVERY SCORECARD (MUSS EXAKT SO ENTHALTEN SEIN)
-------------------------------------------------------------------------------
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| A | 6 | ... | ... |
| B | 6 | ... | ... |
| C | 6 | ... | ... |
| D | 6 | ... | ... |
| Total | 24 | ... | ... |
| Completion Ratio | X/24 = YY% | MUST BE >= 33% | |

No-Go:
- Completion Ratio < 33%
- Fehlende Commands/Resultate
- Falsche "DONE" Claims ohne Dateidiff + Testproof
