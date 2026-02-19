Du bist GLM 4.7 (UX/Workflow Recovery Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_glm47_w18_recovery_closeout.md`
- `handoffs/PROMPT_20260216_glm47_w18_recovery_closeout.md`

Kontext:
W18 hat viele echte Fixes geliefert, aber der Closeout ist noch nicht voll belastbar.
W19 ist ein strict closeout ohne "stille Luecken".

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth:
- Nur `feature/v1-ux-aiB`.

2) No-Go:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) No fake pass:
- Keine "DONE"-Claims ohne reproduzierbare Commands.
- Keine stillen 0-Test-Suites.

4) Skip-Policy:
- Keine neuen skip/xfail fuer Kern-Workflows.
- Bestehende Skips in W19-Zielbereichen nur mit harter technischer Begruendung.

-------------------------------------------------------------------------------
W19 PAKETE (STRICT CLOSEOUT)
-------------------------------------------------------------------------------
Gesamt: 24 Punkte
Akzeptanz:
- Minimum 16/24 (67%)
- Ziel 20+/24 (83%+)

PAKET S1 (8 Punkte) - Direct Manipulation Harness wirklich testbar machen
Pflicht:
1. `test/harness/test_interaction_direct_manipulation_w17.py` muss real Tests sammeln.
2. Kein Class-Shadowing:
- Testklassen und "isolated implementation" Klassen eindeutig trennen.
3. Suite muss mit pytest direkt laufen (nicht "collected 0 items").

Abnahme:
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py -v
```
Erwartung: collected > 0, keine Collection-Fehler.

PAKET S2 (8 Punkte) - ExportController Tests ent-skipped auf robustes Mocking
Pflicht:
1. Reduziere die 4 W18-Skips in `test/test_export_controller.py` deutlich.
2. Ersetze skip durch robustes mocking (QFileDialog/QMessageBox/Signalfluss) soweit sinnvoll.
3. Tests muessen in headless CI stabil laufen.

Abnahme:
```powershell
conda run -n cad_env python -m pytest -q test/test_export_controller.py -v
```
Erwartung: maximal 1 technisch begruendeter Skip, sonst gruen.

PAKET S3 (4 Punkte) - Evidence/Gate Konsistenz
Pflicht:
1. `scripts/generate_gate_evidence.ps1` auf W19 konsistent:
- Header, OutPrefix, Evidence-Level/-Version zusammenpassend.
2. Keine W14/W17-Mischmarker im W19-Flow.

PAKET S4 (4 Punkte) - W19 Vollvalidierung
Pflicht:
1. Target-Suites:
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_controller.py test/test_export_controller.py test/test_discoverability_hints_w17.py test/harness/test_interaction_direct_manipulation_w17.py test/test_error_ux_v2_e2e.py -v
```
2. Gateway:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```
3. Evidence:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W19_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w19_closeout_strict.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard
7. Claim-vs-Proof Matrix
8. Offene Punkte + naechste 5 Aufgaben

-------------------------------------------------------------------------------
DELIVERY SCORECARD (PFLICHT)
-------------------------------------------------------------------------------
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| S1 | 8 | ... | ... |
| S2 | 8 | ... | ... |
| S3 | 4 | ... | ... |
| S4 | 4 | ... | ... |
| Total | 24 | ... | ... |
| Completion Ratio | X/24 = YY% | MUST BE >= 67% | |

No-Go:
- `test_interaction_direct_manipulation_w17.py` collected 0 items
- unreflektiertes Skipgen von Kernfaellen
- inkonsistente Evidence-Metadaten
