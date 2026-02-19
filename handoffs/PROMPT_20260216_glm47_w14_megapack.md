Du bist GLM 4.7 (UX/WORKFLOW Reliability Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollstaendig:
- `handoffs/HANDOFF_20260216_glm47_w13_unskip_retest.md`
- `test/harness/test_interaction_consistency.py`
- `test/harness/test_interaction_drag_isolated.py`
- `test/test_crash_containment_contract.py`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `roadmap_ctp/04_workpackage_backlog.md`
- `roadmap_ctp/03_workstreams_masterplan.md`

Aktueller baseline (durch Codex validiert):
- Drag-Stack ist hard-runnable (`no skip`, `no xfail`) via subprocess containment + hard fail checks.
- UI-Gate: `120 passed, 0 failed, 0 skipped, 0 errors`.

-------------------------------------------------------------------------------
HARTE REGELN
-------------------------------------------------------------------------------
1) Keine Edits in:
- `modeling/**`
- `config/feature_flags.py`

2) Fokus-Pfade:
- `gui/**`
- `test/**`
- `scripts/gate_ui.ps1`
- `scripts/generate_gate_evidence.ps1`
- `handoffs/**`

3) Keine Placeholders:
- Keine TODO-Aussagen ohne reproduzierbaren Command.
- Kein "fertig" ohne Command + Result.

4) Keine kosmetischen-only Aenderungen:
- Jede Aenderung muss einen klaren UX- oder Stability-Effekt plus Regressionstest haben.

5) W14 muss als grosses zusammenhaengendes Paket geliefert werden (nicht nur Mini-Fixes).

-------------------------------------------------------------------------------
MISSION W14: SU-006 + SU-009 + UX-003 Produktionshaertung (MEGAPACK)
-------------------------------------------------------------------------------
Ziel:
Sketch- und UI-Bedienung auf V1-Produktionsniveau bringen: konsistente Abbruchlogik,
Discoverability ohne Spam, Error-UX durchgaengig in Produktflows, Gate/Evidence synchron.

-------------------------------------------------------------------------------
PAKET A (P0): SU-006 Abort-State-Machine Vollendung
-------------------------------------------------------------------------------
Aufgaben:
1) Einheitliche Cancel-Regel erzwingen:
- Rechtsklick ins Leere bricht aktuelle Aktion IMMER ab.
- Escape und Rechtsklick duerfen keine divergierenden Endstates haben.
- Gilt fuer Sketch-Tools inkl. Select-Substates, Path-Modes, direct-edit drag states.

2) Regressionstest-Ausbau:
- `test/test_ui_abort_logic.py` deutlich erweitern.
- Mindestens 12 neue Assertions fuer: right-click empty, escape, mixed sequences,
  active tool + partial input + selected entities.

3) Abnahmekriterium:
- Kein beobachtbarer "stuck tool state" nach abort.

-------------------------------------------------------------------------------
PAKET B (P0): SU-009 Discoverability ohne Spam (Sketch + 2D Navigation)
-------------------------------------------------------------------------------
Aufgaben:
1) Sichtbarkeit der Kern-Interaktionen verbessern:
- Im 2D Sketch klar kommunizieren: Rotation moeglich, Peek mit Space.
- Hinweise muessen kontextsensitiv sein (Tool/Mode/State).

2) Anti-Spam Policy:
- Hint-Cooldown + Kontext-Keying robust machen.
- Kritische Hinweise duerfen Cooldown uebersteuern.

3) Tests:
- `test/test_discoverability_hints.py` um mindestens 12 Assertions erweitern.
- Cases: rapid mode switches, repeated hover, force hints, priority override.

-------------------------------------------------------------------------------
PAKET C (P0): UX-003 / CH-008 Error UX v2 End-to-End Wiring
-------------------------------------------------------------------------------
Aufgaben:
1) Audit in `gui/**` auf Fehler-/Warnpfade mit Nutzerfeedback:
- `status_class` priorisiert
- `severity` fallback
- legacy level fallback stabil

2) Produktflow-Wiring:
- Mindestens 3 echte User-Flows erweitern (nicht nur Utility-Funktionen),
  z. B. feature edit failure, blocked upstream, recoverable warning.

3) Tests:
- `test/test_error_ux_v2_integration.py` signifikant erweitern
  (mindestens 15 neue assertions).

-------------------------------------------------------------------------------
PAKET D (P1): Direct Manipulation UX Parity-Finish
-------------------------------------------------------------------------------
Aufgaben:
1) Circle/Rectangle/Line parity nachziehen (Cursor + drag semantics + selection preconditions).
2) Wenn noch offene Inkonsistenzen bei Handle-/Cursor-Richtung existieren: fixen + testen.
3) Tests in `test/harness/test_interaction_consistency.py` und/oder neuen harness tests erweitern.

Wichtig:
- Keine Re-Introduktion von skip/xfail fuer die 3 Kern-Drag-Tests.

-------------------------------------------------------------------------------
PAKET E (P1): UI Gate + Evidence v6 Synchronisierung
-------------------------------------------------------------------------------
Aufgaben:
1) `scripts/gate_ui.ps1` auf W14 Scope synchronisieren (neue/erweiterte Suites enthalten).
2) `scripts/generate_gate_evidence.ps1` analog synchronisieren.
3) Evidence fuer W14 erzeugen:
- `roadmap_ctp/QA_EVIDENCE_W14_20260216.json`
- `roadmap_ctp/QA_EVIDENCE_W14_20260216.md`

-------------------------------------------------------------------------------
PAKET F (P1): Regression Contract Upgrade
-------------------------------------------------------------------------------
Aufgaben:
1) `test/test_crash_containment_contract.py` und ggf. weitere Contract-Tests auf W14-Realitaet
   anheben (hard-runnable drag stack, no skip/xfail policy).
2) Neue Contract-Checks fuer Abort-/Discoverability-Regeln (mindestens 1 neue Contract-Datei
   oder Erweiterung bestehender Contract-Suites).

-------------------------------------------------------------------------------
PFLICHT-VALIDIERUNG (alles ausfuehren)
-------------------------------------------------------------------------------
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_error_ux_v2_integration.py test/test_feature_commands_atomic.py -v

conda run -n cad_env python -m pytest -q test/harness/test_interaction_drag_isolated.py test/test_crash_containment_contract.py -v

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W14_20260216
```

Mindestakzeptanz W14:
- Keine skip/xfail bei den 3 Drag-Kerntests.
- UI-Gate bleibt PASS.
- Abort + Discoverability + Error-UX Erweiterungen sind testbar belegt.

-------------------------------------------------------------------------------
RUECKGABEFORMAT (verbindlich)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_glm47_w14_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. W14 Delta-Matrix (Pflicht)
7. Review Template (ausgefuellt)
8. Naechste 7 priorisierte Folgeaufgaben (Owner + ETA)

Pflicht in Delta-Matrix:
- Bereich (Abort / Discoverability / Error UX / Direct Manipulation / Gate)
- Vorher-Zustand
- Nachher-Zustand
- Testnachweis (Datei + Command)
- Offene Restluecke

No-Go:
- Unbelegte Claims
- Nur Header-/Text-Aenderungen ohne funktionalen Effekt
- Wiedereinbau von skip/xfail fuer die 3 Drag-Kerntests
