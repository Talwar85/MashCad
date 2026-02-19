Du bist GLM 4.7 (UX/Workflow Delivery Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_glm47_w16_velocity_multipack.md`
- `handoffs/HANDOFF_20260216_altki_w14_rework_complete.md`
- `roadmap_ctp/03_workstreams_masterplan.md`
- `roadmap_ctp/04_workpackage_backlog.md`
- `roadmap_ctp/ROADMAP_STATUS_20260216_codex.md`

-------------------------------------------------------------------------------
MISSION W17: TITANPACK (LARGE-CHUNK DELIVERY + ZERO GATE SKIP)
-------------------------------------------------------------------------------
Ziel:
Grosses, zusammenhaengendes Lieferpaket mit echtem Fortschritt in UX/Workflow.
Keine Mini-Wellen, keine "nur Tests". Mindestens 40% Paketfortschritt pro Lieferung.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Branch Truth:
- Nur `feature/v1-ux-aiB`.

2) No-Go Edits:
- Kein Edit in `modeling/**`
- Kein Edit in `config/feature_flags.py`

3) Claim Policy:
- Kein "done" ohne Dateidiff + Test/Gate-Proof.
- Kein "groesstenteils" ohne konkrete Zahlen.

4) Gateway Hardline (Pflicht):
- UI-Gateway darf NICHT wegen Timeout geskippt werden.
- Wenn ein Lauf timeoutet: Retry/Shard-Strategie fahren, dann finalen Gateway-Run erneut ausfuehren.
- "No Gate Result = No Handoff".

-------------------------------------------------------------------------------
W17 TITANPAKETE (GEWICHTET)
-------------------------------------------------------------------------------
Gesamt: 40 Punkte
Akzeptanz:
- Minimum: 16 Punkte (40%)
- Ziel: 20+ Punkte (50%+)

PAKET A (8 Punkte) - SU-004/SU-010 Direct Manipulation Erweiterung
- Mindestens 3 neue robuste Interaction-Faelle (z. B. Arc/Ellipse/Polygon-Lineage).
- Konsistente Drag- und Cursor-Contracts.
- Keine neuen skip/xfail in Kerninteraktion.

PAKET B (8 Punkte) - UX-003 Error UX v2 Vollabdeckung
- Konsistenz Tooltip/Notification/Statusbar fuer WARNING/BLOCKED/CRITICAL/ERROR.
- End-to-End-Flows aus User-Trigger heraus, nicht nur isolierte Mapper.
- Regression gegen Prioritaetsregeln (status_class > severity > legacy level).

PAKET C (8 Punkte) - AR-004 MainWindow Entlastung Phase-2
- Weitere trennbare Sketch/UI-Orchestrierung aus `gui/main_window.py` in Controller/Helper.
- Saubere Delegation, dokumentierter Fallback.
- Regressionstests fuer die extrahierten Flows.

PAKET D (8 Punkte) - SU-009 Discoverability v2 Hardening
- Bestehende schwache Assertions in kritischen Discoverability-Tests auf Behavior-Proof umstellen.
- Hint-Kontext, anti-spam, tutorial/normal mode sauber abdecken.
- Kein API-Existenz-Test als "Proof" in W17-Bereichen.

PAKET E (8 Punkte) - Gate/Evidence Stabilitaet + Laufzeitsteuerung
- `scripts/gate_ui.ps1` und `scripts/generate_gate_evidence.ps1` auf W17 aktualisieren.
- Laufzeit-/Retry-Hinweise im Evidence-Output ergaenzen.
- Klare Marker fuer durchgefuehrte Gateway-Runs.

-------------------------------------------------------------------------------
DELIVERY-REGELN
-------------------------------------------------------------------------------
1) Arbeite in grossen Chunks:
- Mindestens 2 Pakete DONE oder 1 DONE + 2 PARTIAL mit belegtem Fortschritt.

2) Unter 40% nicht abgeben:
- Erst weiterarbeiten bis 16/40 erreicht sind.

3) Bei 20+ Punkten:
- Stop-and-ship (sofort Handoff liefern).

-------------------------------------------------------------------------------
GATEWAY: EMPFOHLENE AUFRUFSTRATEGIE (ANTI-TIMEOUT)
-------------------------------------------------------------------------------
Fuehre in dieser Reihenfolge aus:

1) Preflight Shards (schnelles Fruehsignal)
```powershell
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py -v
conda run -n cad_env python -m pytest -q test/test_sketch_controller.py test/test_ui_abort_logic.py test/test_crash_containment_contract.py -v
```

2) Pflicht-Gateway (nicht skippen)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

3) Wenn Gateway-Lauf timeoutet:
- Sofort Retry mit Log-Datei und Zeitstempel.
- Danach final erneut `gate_ui.ps1` ausfuehren, bis ein verwertbares Ergebnis vorliegt.
```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1 *>&1 | Tee-Object -FilePath "roadmap_ctp/_w17_gate_retry_$ts.log"
```

4) Evidence nur mit vorhandenem Gateway-Result:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W17_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT (STRICT)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w17_titanpack.md`

Pflichtstruktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard (Pflicht)
7. Claim-vs-Proof Matrix (Pflicht)
8. Open Items + naechste 8 Aufgaben

-------------------------------------------------------------------------------
DELIVERY SCORECARD (MUSS EXAKT ENTHALTEN SEIN)
-------------------------------------------------------------------------------
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| A | 8 | ... | ... |
| B | 8 | ... | ... |
| C | 8 | ... | ... |
| D | 8 | ... | ... |
| E | 8 | ... | ... |
| Total | 40 | ... | ... |
| Completion Ratio | X/40 = YY% | MUST BE >= 40% | |

No-Go:
- Completion Ratio < 40%
- Gateway wegen Timeout geskippt
- Fehlende Command-Outputs
- "DONE" ohne Diff + Testproof
