Du bist GLM 4.7 (UX/WORKFLOW Reliability Cell) auf Branch `feature/v1-ux-aiB`.

STARTBEDINGUNG:
- Dieses Paket erst starten, wenn Codex W14 (`HANDOFF_20260216_glm47_w14_megapack.md`) validiert und freigegeben hat.

Lies vor Start:
- `handoffs/HANDOFF_20260216_glm47_w14_megapack.md`
- `roadmap_ctp/04_workpackage_backlog.md`
- `roadmap_ctp/03_workstreams_masterplan.md`

-------------------------------------------------------------------------------
MISSION W15: ULTRAPACK - GUI/UX Produktionsreife Phase 2
-------------------------------------------------------------------------------
Ziel:
Groesserer, laengerer Lieferblock zur V1-Reife mit Schwerpunkt auf
Sketch/UX-Konsistenz, MainWindow-Entlastung im UI-Layer, und robusten
Langlauf-Regressionen.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`

2) Ownership:
- `gui/**`, `test/**`, `scripts/gate_ui.ps1`, `scripts/generate_gate_evidence.ps1`, `handoffs/**`

3) Jeder Teilblock muss mit Tests/Gates belegbar sein.

-------------------------------------------------------------------------------
PAKET A (P0): SU-004/SU-010 Interaction Consistency Expansion
-------------------------------------------------------------------------------
Aufgaben:
1) Interaction-Harness auf weitere Grundformen ausdehnen (mindestens 2 neue Shape-Klassen,
   z. B. Arc/Ellipse/Slot je nach Realitaet im Code).
2) Einheitliche drag/select/cursor contracts definieren und durchsetzen.
3) Neue Regressionen fuer mode transitions waehrend active manipulation.

Abnahme:
- Neue Interaction-Tests mit klaren PASS/FAIL assertions (kein skip/xfail als default).

-------------------------------------------------------------------------------
PAKET B (P0): AR-004 GUI-Layer Entlastung (MainWindow Phase-1 im UX-Scope)
-------------------------------------------------------------------------------
Aufgaben:
1) Nicht-kritische, klar trennbare UI-Orchestrierung aus `gui/main_window.py` in dedizierte
   Controller/Helper im GUI-Layer extrahieren.
2) Keine Verhaltensaenderung ausser beabsichtigter UX-Fixes.
3) Tests fuer extrahierte Flows bereitstellen.

Abnahme:
- Reduzierte Komplexitaet in `gui/main_window.py` plus gruene Regressionen.

-------------------------------------------------------------------------------
PAKET C (P1): UX-004 Context Help Overlay v1
-------------------------------------------------------------------------------
Aufgaben:
1) Kontextsensitives Hilfe-Overlay fuer Kern-Sketch-Flows (on-demand + state aware).
2) Hinweise muessen mit bestehender Discoverability-Policy kompatibel bleiben (anti-spam).
3) Tests fuer visibility, context switch, dismissal, re-open behavior.

-------------------------------------------------------------------------------
PAKET D (P1): UX-005 Accessibility Baseline im Kernworkflow
-------------------------------------------------------------------------------
Aufgaben:
1) Keyboard-Navigation und Focus-Zustaende in zentralen GUI-Flows pruefen/fixen.
2) Mindestens baseline checks fuer kritische Interaktionspfade hinterlegen.
3) Tests dokumentieren, was aktuell abgesichert ist und was bewusst ausser Scope bleibt.

-------------------------------------------------------------------------------
PAKET E (P1): QA-006 UI Performance/Robustness Regression Pack
-------------------------------------------------------------------------------
Aufgaben:
1) Kurz-Langlauf-Tests fuer state leaks / event storms / hint bursts.
2) Mindestens eine reproduzierbare Budget-Metrik im UI-Layer dokumentieren (z. B. max update latency).
3) Gate-nahe Ausfuehrung sicherstellen, ohne unendliche Laufzeiten.

-------------------------------------------------------------------------------
PAKET F (P1): Evidence/Gate W15 Synchronisierung
-------------------------------------------------------------------------------
Aufgaben:
1) UI-Gate-Scope auf W15 anpassen.
2) Evidence-Generator auf neue Suites/Contracts anpassen.
3) W15 Evidence erzeugen (`QA_EVIDENCE_W15_20260216.*`).

-------------------------------------------------------------------------------
PFLICHT-VALIDIERUNG
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py -v

conda run -n cad_env python -m pytest -q test/harness/test_interaction_drag_isolated.py test/test_crash_containment_contract.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W15_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w15_ultrapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. W15 Delivery Matrix (Pflicht)
7. Review Template (ausgefuellt)
8. Naechste 10 priorisierte Folgeaufgaben (Owner + ETA)

No-Go:
- Core-Edits
- Unbelegte Claims
- Rueckfall auf skip/xfail fuer Kern-Drag-Tests ohne harte technische Begruendung
