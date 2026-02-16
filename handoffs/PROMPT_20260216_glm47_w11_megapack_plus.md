Du bist GLM 4.7 (UX/WORKFLOW + QA Integration Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst (vollstaendig):
- `handoffs/HANDOFF_20260216_glm47_w10.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w11.md`
- `roadmap_ctp/ROADMAP_STATUS_20260216_codex.md`
- `roadmap_ctp/CODEX_SELF_MEGAPACK_W8_20260216.md`
- `roadmap_ctp/EVIDENCE_SCHEMA_CONTRACT_W8_20260216.md`

-------------------------------------------------------------------------------
Harte Regeln
-------------------------------------------------------------------------------
1. Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`
- `gui/viewport_pyvista.py` (nur wenn unbedingt noetig, dann im Handoff begruenden)

2. Fokus auf:
- `gui/**` (UX/Workflow Layer)
- `test/**` (UI + Integration + Harness)
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `handoffs/**`

3. Keine Placeholders:
- Keine "TODO spaeter" ohne konkreten Repro-Command.
- Keine Handoff-Claims ohne validierten Command.

4. Jede Aussage im Handoff muss auf reproduzierbarer Validation beruhen.

5. Wenn ein Paket blockiert ist:
- technisch praezise Root Cause,
- reproduzierbarer Nachweis,
- klare Exit-Strategie mit Owner und ETA.

-------------------------------------------------------------------------------
Mission W11 (MEGAPACK+)
-------------------------------------------------------------------------------
Liefer ein grosses, zusammenhaengendes Paket mit Fokus auf Produktionsreife.
Ziel: nicht nur weitere Features, sondern deutliche Reduktion von UX- und Gate-Risiken.

-------------------------------------------------------------------------------
Paket A (P0): Direct Manipulation De-Flake / Entskip Program v3
-------------------------------------------------------------------------------
Ziel:
- Die 3 geskippten Drag-Tests sollen entweder entskippt werden oder mit technisch wasserdichter
  Blocking-Dokumentation + Zwischenloesung geliefert werden.

Aufgaben:
1. In `test/harness/test_interaction_consistency.py` deterministische Hilfen ausbauen:
- viewport transform snapshot helper
- deterministic coordinate conversion helper
- event flush stabilization helper

2. Entskip-Versuch fuer:
- `test_circle_move_resize`
- `test_rectangle_edge_drag`
- `test_line_drag_consistency`

3. Wenn Entskip nicht moeglich:
- `xfail(strict=True)` statt skip pruefen, falls reproduzierbarer known-failure contract vorliegt
- blocker signature in Testdocstring + Handoff standardisieren

4. Liefere Entskip-Matrix:
- vorher/nachher Status, technische Ursache, verbleibende Luecke.

Abnahme:
- mindestens 1 Test aus den 3 entskippt ODER
- saubere blocker-contract matrix ohne diffuse Begruendung.

-------------------------------------------------------------------------------
Paket B (P0): Error UX v2 Complete Wiring in Product Flows
-------------------------------------------------------------------------------
Ziel:
- `status_class`/`severity` nicht nur in Tooltips/Statusbar/Notification, sondern durchgaengig
  in zentralen User-Flows.

Aufgaben:
1. Audit + Wiring aller relevanten `show_notification()` und Status-Set-Pfade in `gui/**`.
2. Sicherstellen:
- `status_class` priorisiert
- `severity` fallback
- legacy level fallback bleibt stabil
3. Integrationstests erweitern:
- mindestens 10 neue Assertions fuer reale Workflow-Einstiegspunkte
  (z. B. Feature-Edit-Fehler, blocked-upstream, recoverable warning).

Abnahme:
- `test/test_error_ux_v2_integration.py` signifikant erweitert und gruen.

-------------------------------------------------------------------------------
Paket C (P1): Selection-State Legacy Debt Burn-Down
-------------------------------------------------------------------------------
Ziel:
- Legacy-Ausweichpfade weiter reduzieren, ohne UX-Regressions.

Aufgaben:
1. Suche direkte Legacy-Zugriffe auf `selected_faces` / `selected_edges` im UI-Layer.
2. Migriere auf Unified API, wo noch direkte Zugriffe bestehen.
3. Wenn Legacy-Wrapper noetig bleiben:
- explizit dokumentieren (warum, bis wann, wer Owner).
4. Neue Regressionen:
- multi-select lifecycle unter Mode-Wechsel
- abort/escape Konsistenz bei aktivem Tool + bestehender Auswahl.

Abnahme:
- erweiterte Suite `test/test_selection_state_unified.py` gruen.

-------------------------------------------------------------------------------
Paket D (P1): Discoverability v5 Context Sequencing
-------------------------------------------------------------------------------
Ziel:
- Hinweise werden kontextsensitiv, priorisiert und nicht spammy.

Aufgaben:
1. `gui/sketch_editor.py` Hint-Sequencing:
- context key concept (mode, tool, action)
- anti-repeat ueber Kontext
- force/priority contracts beibehalten
2. Tests:
- mindestens 8 neue Tests in `test/test_discoverability_hints.py`
- race/rapid hint cases abdecken
- "kritische Hinweise duerfen Cooldown uebersteuern" absichern.

Abnahme:
- Suite stabil, kein Hint-Spam bei rapid input.

-------------------------------------------------------------------------------
Paket E (P1): UI Gate + Evidence v5 Hardening
-------------------------------------------------------------------------------
Ziel:
- UI-Gate und Evidence-Generator auf aktuellen W11-Scope bringen.

Aufgaben:
1. `scripts/gate_ui.ps1`:
- Testliste auf W11 aktualisieren
- klare Statusausgabe (PASS/BLOCKED_INFRA/FAIL)
2. `scripts/generate_gate_evidence.ps1`:
- W11 Prefix + neue Suites + blocker details
- konsistente status_class Felder fuer UI-Teil
3. Evidence Datei in `roadmap_ctp/` erzeugen (MD + JSON) mit validierten Zahlen.

Abnahme:
- Evidence-Commands reproduzierbar und im Handoff dokumentiert.

-------------------------------------------------------------------------------
Paket F (P2): UX Robustness Long-Run Pack
-------------------------------------------------------------------------------
Ziel:
- Last- und Robustheitsindikatoren fuer UI-Verhalten sammeln.

Aufgaben:
1. Langlaufnahe Regressionen (ohne endlose Laufzeit):
- wiederholte hint/notification burst tests
- selection/abort loop tests
2. Neue Suite oder bestehende Suiten erweitern mit klaren Contracts fuer:
- "kein Crash"
- "kein state leak"
- "keine inkonsistente cursor/state transitions"

Abnahme:
- neue/erweiterte Tests mit reproduzierbarem Nutzen dokumentiert.

-------------------------------------------------------------------------------
Pflicht-Validierung (alles ausfuehren)
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_feature_commands_atomic.py -v

conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_selection_state_unified.py

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W11_20260216
```

-------------------------------------------------------------------------------
Rueckgabeformat (verbindlich)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w11.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Entskip-Matrix (Pflicht)
7. W11 Review Template (ausgefuellt)
8. Naechste 7 priorisierte Folgeaufgaben (Owner + ETA)

Zusatzpflichten:
- Alle Zahlen konsistent (keine widerspruechlichen Pass-Counts).
- Wenn Blocker: klare technische Signatur + reproduzierbarer Nachweis.
- Keine "fertig" Aussage ohne Command+Resultat.
