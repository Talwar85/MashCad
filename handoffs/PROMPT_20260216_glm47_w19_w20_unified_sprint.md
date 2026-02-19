Du bist GLM 4.7 (Product UX Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_glm47_w18_recovery_closeout.md`
- `handoffs/PROMPT_20260216_glm47_w19_closeout_strict.md`
- `handoffs/PROMPT_20260216_glm47_w20_product_leap.md`

Dieses Dokument ersetzt die getrennten W19/W20-Prompts durch einen
einzigen, zusammenhaengenden Sprint.

-------------------------------------------------------------------------------
MISSION: W19 + W20 UNIFIED SPRINT
-------------------------------------------------------------------------------
Ziel:
1. W19-Closeout wirklich abschliessen (keine stillen Luecken, keine 0-Test-Suites).
2. Danach W20 Product Leap liefern (sichtbare UX/Produktverbesserungen).
3. Keine Test-only Lieferung. Produktcode muss klar sichtbar wachsen.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth:
- Nur `feature/v1-ux-aiB`.

2) No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) No fake done:
- Kein "DONE" ohne Dateidiff + reproduzierbaren Command-Output.
- Kein verschleiertes "collected 0 items".

4) Gateway Policy:
- `scripts/gate_ui.ps1` darf NICHT geskippt werden.
- Timeout/infra issue -> fix/retry/shard -> finaler Gate-Output ist Pflicht.

5) Delivery Mix:
- Mindestens 60% der geaenderten Zeilen in `gui/**` (produktseitig).
- Maximal 40% in `test/**` (Absicherung).

-------------------------------------------------------------------------------
PHASE A - W19 CLOSEOUT (BLOCKER FIRST)
-------------------------------------------------------------------------------
Gesamt Phase A: 24 Punkte
Mindestziel Phase A: 18/24

S1 (8 Punkte) Direct Manipulation Harness real testbar
- `test/harness/test_interaction_direct_manipulation_w17.py` muss Tests sammeln.
- Kein Class-Shadowing, keine stillen Ueberschreibungen.
- pytest-Lauf darf nicht "collected 0 items" liefern.

S2 (8 Punkte) ExportController Tests ent-skipped
- Skips in `test/test_export_controller.py` reduzieren.
- QFileDialog/QMessageBox per Mocking in headless stabil testen.
- Nur technische Rest-Skips mit harter Begruendung.

S3 (4 Punkte) Evidence/Gate Konsistenz
- `scripts/generate_gate_evidence.ps1` Header/Prefix/Version konsistent auf W19+W20.
- Keine W14/W17/W18 Marker-Mischung im finalen Flow.

S4 (4 Punkte) Closeout-Validierung
- Target-Suites muessen reproduzierbar laufen.

Phase-A Pflicht-Command:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py test/test_discoverability_hints_w17.py test/harness/test_interaction_direct_manipulation_w17.py test/test_error_ux_v2_e2e.py -v
```

-------------------------------------------------------------------------------
PHASE B - W20 PRODUCT LEAP (USER-VISIBLE IMPROVEMENTS)
-------------------------------------------------------------------------------
Gesamt Phase B: 50 Punkte
Mindestziel Phase B: 25/50
Ziel Phase B: 30+/50

P1 (12 Punkte) Direct Manipulation V3
- Einheitliche Handle-Logik fuer mindestens 4 Objektarten (circle, line, rectangle, arc).
- Korrekte Cursor-Symbolik und stabile Drag-Endzustaende.
- Live-Feedback waehrend Drag (Wert/Constraint-Hinweis).

P2 (10 Punkte) Ellipse UX Parity
- Ellipse als klares Primitaerobjekt selektierbar.
- Sichtbare major/minor Achsen statt Punktflut.
- Drag fuer center/major/minor klar bedienbar.

P3 (10 Punkte) Rectangle/Line Constraint-aware Edit
- Kanten-Drag passt relevante Constraints sinnvoll an.
- Kein stuck state nach Edit/Abort/Delete.
- Delete raeumt Hilfsgeometrie konsistent auf.

P4 (8 Punkte) Discoverability Overlay v2
- F1-Hilfe mit kontextsensitiven Hinweisen.
- Space peek / rotation shortcuts klar kommuniziert.
- Anti-spam bleibt wirksam.

P5 (10 Punkte) 3D Trace Assist UX
- Project/convert-edge Workflow im Sketch klar fuehren.
- Sichtbares Tracing-Feedback (highlight + snap cue).
- 2 echte End-to-End Userflows absichern.

-------------------------------------------------------------------------------
AUSLIEFERUNGSLOGIK
-------------------------------------------------------------------------------
1) Reihenfolge ist strikt:
- Erst Phase A (W19 closeout), dann Phase B (W20 leap).

2) Mindestabnahme fuer Gesamtlieferung:
- Phase A >= 18/24 UND Phase B >= 25/50
- Gesamt >= 43/74

3) Stop-and-ship:
- Wenn Phase A gruener closeout + Phase B >= 30/50 erreicht ist, sofort liefern.

-------------------------------------------------------------------------------
VALIDIERUNG (PFLICHT)
-------------------------------------------------------------------------------
1) Phase-A Kern:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py test/test_discoverability_hints_w17.py test/harness/test_interaction_direct_manipulation_w17.py test/test_error_ux_v2_e2e.py -v
```

2) W20 UX/Interaction:
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_discoverability_hints.py test/test_discoverability_hints_w17.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py -v
```

3) Controller/Integration:
```powershell
conda run -n cad_env python -m pytest -q test/test_sketch_controller.py test/test_feature_controller.py test/test_export_controller.py -v
```

4) UI Gate:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

5) Evidence:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W19_W20_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w19_w20_unified_sprint.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Scorecard Phase A (W19)
7. Scorecard Phase B (W20)
8. Combined Scorecard
9. Claim-vs-Proof Matrix
10. Product Change Log (user-facing, Pflicht)
11. UX Acceptance Checklist (Pflicht)
12. Offene Punkte + naechste 8 Aufgaben

-------------------------------------------------------------------------------
SCORECARDS (PFLICHT)
-------------------------------------------------------------------------------
Phase A:
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| S1 | 8 | ... | ... |
| S2 | 8 | ... | ... |
| S3 | 4 | ... | ... |
| S4 | 4 | ... | ... |
| Total A | 24 | ... | ... |
| Completion A | X/24 = YY% | MUST BE >= 75% | |

Phase B:
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| P1 | 12 | ... | ... |
| P2 | 10 | ... | ... |
| P3 | 10 | ... | ... |
| P4 | 8 | ... | ... |
| P5 | 10 | ... | ... |
| Total B | 50 | ... | ... |
| Completion B | X/50 = YY% | MUST BE >= 50% | |

Combined:
| Total | 74 | ... | ... |
| Completion | X/74 = YY% | MUST BE >= 58% | |

No-Go:
- Phase A nicht abgeschlossen
- UI Gate skipped
- Test-only Lieferung ohne deutlich sichtbare UX-Verbesserung
