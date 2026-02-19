Du bist GLM 4.7 (Product UX Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_glm47_w18_recovery_closeout.md`
- `handoffs/PROMPT_20260216_glm47_w19_closeout_strict.md`

Mission-Shift:
W20 ist ein PRODUCT LEAP, nicht nur Test-Hardening.
Es muss fuer Nutzer sichtbar und spuerbar besser werden.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth:
- Nur `feature/v1-ux-aiB`.

2) No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) No fake delivery:
- Kein "DONE" ohne reale UX-Aenderung im Produktcode.
- Reine Test-Only Lieferung ist fuer W20 unzulaessig.

4) Gateway Policy:
- `scripts/gate_ui.ps1` darf NICHT wegen Timeout geskippt werden.
- Timeout -> retry/shard -> final gate result.

5) Delivery Mix (Pflicht):
- Mindestens 65% der geaenderten Zeilen in `gui/**` (Produktcode).
- Maximal 35% in `test/**` (nur Absicherung).

-------------------------------------------------------------------------------
W20 PRODUCT PACKAGES (LARGE)
-------------------------------------------------------------------------------
Gesamt: 50 Punkte
Akzeptanz:
- Minimum 25/50 (50%)
- Ziel 30+/50 (60%+)

PAKET P1 (12 Punkte) - Direct Manipulation V3 (User-visible)
Ziel:
Direktes Ziehen/Bearbeiten soll fuer zentrale 2D-Objekte konsistent und fluessig sein.

Pflicht:
1. Einheitliche Handle-Logik fuer mindestens 4 Objektarten:
- circle, line, rectangle, arc (plus ellipse/polygon wenn verfuegbar)
2. Cursor-Richtung und Handle-Symbolik muessen korrekt sein.
3. Live-Feedback waehrend Drag (Wert/Constraint-Hinweis) sichtbar.
4. Escape/Right-click Abbruch muss dieselbe Endlogik liefern.

PAKET P2 (10 Punkte) - Ellipse UX Parity (Fusion-like simplification)
Ziel:
Ellipse soll im UI als ein klares Objekt wirken, nicht als "viele Punkte".

Pflicht:
1. Ellipse-Selektion als primitaeres Objekt.
2. Sichtbare 2 Achsen als Konstruktion (major/minor), keine Punktflut.
3. Drag fuer major/minor Radius und Zentrum.
4. Deutliche visuelle States (hover, selected, direct-edit).

PAKET P3 (10 Punkte) - Rectangle/Line Constraint-aware Edit
Ziel:
Rechteck- und Linienbearbeitung wie in professionellen CAD-Sketchern.

Pflicht:
1. Kante ziehen passt relevante Laengen-Constraints an (statt solver-chaos).
2. Mittelpunkt-/Endpunkt-Drag bleibt konsistent.
3. Nach Edit keine "stuck state" Situationen.
4. Delete-Flow raeumt Hilfspunkte/Hilfslinien sauber mit auf.

PAKET P4 (8 Punkte) - Sketch Discoverability Overlay v2
Ziel:
Nutzer sollen ohne Suchen verstehen: drehen, peek, abbrechen, direct edit.

Pflicht:
1. Einblendbare Hilfe (F1) mit kontextsensitiven Hinweisen.
2. Space peek und rotation shortcut sichtbar und korrekt aktualisiert.
3. Anti-spam bleibt erhalten (keine Hinweisflut).
4. Klare Onboarding-Hinweise fuer Direct Edit.

PAKET P5 (10 Punkte) - 3D Trace Assist (User workflow boost)
Ziel:
"Nachzeichnen wie in Fusion/Solidworks" spuerbar verbessern.

Pflicht:
1. Project/Convert-Edges Workflow im Sketch klar fuehren (UX layer).
2. Temporaere visuelle Fuhrung fuer tracing (highlight + snap cue).
3. Selektion/Fokus beim Wechsel 3D<->Sketch stabil halten.
4. Mindestens 2 realistische End-to-End Nutzerflows absichern.

-------------------------------------------------------------------------------
AUSLIEFERUNGSPFLICHT (NO TEST-ONLY)
-------------------------------------------------------------------------------
Neben Tests musst du liefern:
1. Product Change Log (user-facing) mit 8-12 konkreten Verbesserungen.
2. UX Acceptance Checklist mit "vorher/nachher" Verhalten.
3. Mindestens 3 manuelle Repro-Szenarien, die die Verbesserungen zeigen.

-------------------------------------------------------------------------------
VALIDIERUNG (PFLICHT)
-------------------------------------------------------------------------------
1) Focused regression:
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_discoverability_hints.py test/test_discoverability_hints_w17.py test/test_error_ux_v2_integration.py test/test_error_ux_v2_e2e.py -v
```

2) Direct manipulation and interaction:
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py test/harness/test_interaction_direct_manipulation_w17.py test/test_selection_state_unified.py -v
```

3) Controllers and integration:
```powershell
conda run -n cad_env python -m pytest -q test/test_sketch_controller.py test/test_feature_controller.py test/test_export_controller.py -v
```

4) UI gate (mandatory):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

5) Evidence:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W20_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w20_product_leap.md`

Pflichtstruktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard
7. Claim-vs-Proof Matrix
8. Product Change Log (user-facing, Pflicht)
9. UX Acceptance Checklist (Pflicht)
10. Offene Punkte + naechste 8 Aufgaben

-------------------------------------------------------------------------------
DELIVERY SCORECARD (PFLICHT)
-------------------------------------------------------------------------------
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| P1 | 12 | ... | ... |
| P2 | 10 | ... | ... |
| P3 | 10 | ... | ... |
| P4 | 8 | ... | ... |
| P5 | 10 | ... | ... |
| Total | 50 | ... | ... |
| Completion Ratio | X/50 = YY% | MUST BE >= 50% | |

No-Go:
- Completion Ratio < 50%
- Keine klar sichtbaren UX-Verbesserungen
- Test-only Lieferung ohne starke Produktaenderung
- UI Gate skipped
