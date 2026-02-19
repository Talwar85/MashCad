Du bist `AI-LARGE-E` auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollständig:
- `handoffs/HANDOFF_20260217_ai_largeD_w25_workflow_product_leaps.md`
- `handoffs/HANDOFF_20260217_ai_largeA_w24_sketch_interaction.md`
- `handoffs/HANDOFF_20260217_ai_largeC_w25_sketch_product_leaps.md`
- `handoffs/HANDOFF_20260217_glm47_totalpack_all_tasks.md`

## Mission (W26-E)
Baue den 3D→2D-Workflow von "funktional" auf "produktreif":
1. echte Projection-Preview im tatsächlichen Project-Workflow (nicht nur API/HUD),
2. Trace-Assist End-to-End mit belastbarer Zustandsmaschine,
3. harte Abort-Parität (Esc = Rechtsklick ins Leere),
4. belastbare Regression-Tests ohne Skip-Workarounds.

Die Änderungen müssen für Nutzer sichtbar sein, nicht nur testseitig.

## Harte Regeln
1. Kein `skip`/`xfail` hinzufügen, um rote Tests zu umgehen.
2. Keine Timeouts als Begründung für ausgelassene Gates.
3. Keine Placeholders, keine TODO-Kommentare als "Lösung".
4. Keine Änderungen in:
- `modeling/**`
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
5. Nicht am Branch/History-Setup drehen (kein Rebase/Reset).
6. Wenn ein Test instabil ist: Ursache beheben oder deterministisch machen.

## Scope (nur diese Bereiche)
- `gui/sketch_editor.py`
- `gui/viewport_pyvista.py`
- `gui/main_window.py`
- neue Tests in `test/**` und `test/harness/**`
- optional kurze Doku in `roadmap_ctp/**`

## Große Arbeitspakete

### Paket E1: Projection Preview als echter Workflow
Implementiere Projection-Preview so, dass sie bei realer Nutzung sichtbar und korrekt gecleart wird.

Pflicht:
1. Preview startet beim echten "Project/Include"-Ablauf (nicht nur manueller API-Call).
2. Preview zeigt Kandidaten-Geometrie (Edge-Segmente) konsistent im Viewport.
3. Preview wird garantiert gecleart bei:
- Confirm
- Cancel/Escape
- Mode-Wechsel
- Component-Aktivierung
- Sketch-Verlassen
4. Keine Preview-Leaks (keine "hängenden" Actor/Labels).

### Paket E2: Trace Assist 2.0 (produktreif)
Verbessere den W25-Trace-Assist zu einem robusten Feature:

Pflicht:
1. Hint nur in neutralem, erlaubtem Kontext.
2. `T` Shortcut nur aktiv, wenn Ziel-Face valide und Kontext erlaubt.
3. Kontextmenü, Hover-Hint und Shortcut führen deterministisch in denselben Create-Sketch-Flow.
4. Rechtsklick-ins-Leere und Escape beenden den Assist identisch.
5. Kein Ghost-State nach Moduswechseln.

### Paket E3: Abort/State-Matrix schließen
Schließe alle erkennbaren State-Leaks im betroffenen Flow:

Pflicht:
1. Esc/Rechtsklick-ins-Leere verhalten sich in den betroffenen Flows identisch.
2. `_clear_transient_previews(...)` wird in allen relevanten Übergängen konsistent verwendet.
3. Event-Order robust gegen schnelle Input-Sequenzen (MouseMove, KeyPress, Context-Menu, Mode-Toggle).

### Paket E4: Regression- und Behavior-Proof
Baue schnelle, robuste Tests (ohne schwere Langläufer):

Mindestens:
1. neue Datei `test/test_projection_trace_workflow_w26.py` (oder mehrere Dateien)
2. mindestens 14 neue Assertions, davon:
- 6 Projection-Preview Behavior,
- 5 Trace-Assist/Shortcut Behavior,
- 3 Abort-Parität/State-Cleanup Behavior.
3. Tests müssen echte Methodenpfade prüfen, nicht nur `hasattr`.

## Pflicht-Validierung (ohne Skip)
Führe exakt diese Kommandos aus und dokumentiere Ergebniszahlen:

```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/viewport_pyvista.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py -v
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py::TestArcDirectManipulation -v
```

Wenn ein Kommando scheitert:
1. zuerst fixen,
2. dann erneut laufen lassen,
3. im Handoff transparent dokumentieren.

## Abnahme-Kriterien (DoD)
1. Nutzer sieht Projection-Preview im echten Workflow.
2. Trace-Assist funktioniert konsistent via Hover + Kontextmenü + `T`.
3. Keine persistierenden Preview-/Hint-Artefakte nach Abbruch/Mode-Wechsel.
4. Alle Pflicht-Validierungen grün, ohne neue Skips.
5. Sauberer Commit mit präziser Message.

## Rückgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeE_w26_projection_trace_end2end.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Dateien + warum)
4. Validation (Kommandos + Zahlen)
5. Breaking Changes / Rest-Risiken
6. Nächste 5 priorisierte Folgeaufgaben

Zusätzlich:
- exakte Liste der Commits (Hash + Message)
- kurze "Before/After" UX-Beschreibung in 5-8 Sätzen

