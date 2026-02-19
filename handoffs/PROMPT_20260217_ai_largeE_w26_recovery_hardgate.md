Du bist `AI-LARGE-E-RECOVERY` auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollständig:
- `handoffs/PROMPT_20260217_ai_largeE_w26_projection_trace_end2end.md`
- `handoffs/HANDOFF_20260217_ai_largeD_w25_workflow_product_leaps.md`
- `handoffs/HANDOFF_20260217_ai_largeA_w24_sketch_interaction.md`

## Wichtiger Kontext aus letzter Runde (Fehlschlag)
Die letzte Lieferung war **nicht abnahmefähig**. Gründe:
1. `show_projection_preview(...)` existiert, wird aber im echten Workflow nicht aufgerufen.
2. `test/test_projection_trace_workflow_w26.py` wurde nicht erstellt.
3. `SketchTool.PROJECT` ist inkonsistent angebunden.
4. Pflicht-Validierungen aus dem Prompt wurden nicht erfüllt.

Du lieferst jetzt ein **Recovery-Pack**, das diese Lücken schließt.

## Mission (W26-E Recovery)
Setze den 3D→2D Projection/Trace-Workflow produktreif um, nicht nur API-seitig.

Pflichtziele:
1. Projection-Preview läuft im echten Project-Workflow.
2. Preview wird zuverlässig gecleart (Confirm/Cancel/Modewechsel/Sketch verlassen/Component-Wechsel).
3. Trace-Assist bleibt konsistent (Hover + Context Menu + `T`).
4. Abort-Parität bleibt stabil (Esc = Rechtsklick ins Leere).
5. Neue W26-Tests vorhanden und grün.

## Harte Regeln
1. Keine Analyse-only Abgabe.
2. Kein `skip`/`xfail` zum Umgehen roter Tests.
3. Keine Placeholder/TODO als "Fix".
4. Keine Änderungen in:
- `modeling/**`
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
5. Keine Git-History-Operationen (kein Reset/Rebase/Force-Push).
6. Wenn ein Gate rot ist: fixen und neu laufen lassen.

## Scope (erlaubte Dateien)
- `gui/sketch_editor.py`
- `gui/viewport_pyvista.py`
- `gui/main_window.py`
- `test/**` (nur relevante neue/angepasste Tests)
- optional kurzer Report in `roadmap_ctp/**`

## Konkrete Aufgaben

### Task 1: Echter Projection-Preview-Hook
Implementiere die Anbindung der Preview an den realen PROJECT-Ablauf im Sketch-Workflow.

Pflicht:
1. Beim Hover/Kandidatenfindung im PROJECT-Tool wird Preview sichtbar aktualisiert.
2. Bei Confirm der Projektion wird Preview entfernt.
3. Bei Cancel/Escape wird Preview entfernt.
4. Bei Toolwechsel weg von PROJECT wird Preview entfernt.
5. Bei Sketch-Ende/Modewechsel/Component-Aktivierung keine Actor-Leaks.

### Task 2: PROJECT-Tool-Integrität
Sorge dafür, dass der PROJECT-Flow tatsächlich einen Handlerpfad hat.

Pflicht:
1. Kein "toter" Tool-Eintrag ohne Handler.
2. Shortcut-Mapping konsistent (keine widersprüchliche Doppelbelegung ohne Absicht).
3. Context-Hinweise passen zum tatsächlichen Verhalten.

### Task 3: Trace-Assist End-to-End Härten
Pflicht:
1. `T` arbeitet nur in erlaubtem Kontext und nur mit gültigem Ziel.
2. Context-Menu Action + Hover-Hint + Shortcut landen in demselben robusten Create-Sketch-Flow.
3. Kein Ghost-State nach schneller Eingabeabfolge.

### Task 4: W26-Tests liefern
Erstelle mindestens:
- `test/test_projection_trace_workflow_w26.py`

Mindestabdeckung:
1. Mind. 6 Assertions für Projection-Preview Behavior.
2. Mind. 5 Assertions für Trace-Assist/Shortcut Behavior.
3. Mind. 3 Assertions für Abort/State-Cleanup Behavior.
4. Keine reinen `hasattr`-Tests als Hauptnachweis.

## Pflicht-Validierung (exakt ausführen)
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/viewport_pyvista.py gui/main_window.py test/test_projection_trace_workflow_w26.py
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py -v
conda run -n cad_env python -m pytest -q test/test_workflow_product_leaps_w25.py -v
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_discoverability_hints.py test/test_discoverability_hints_w17.py -v
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py::TestArcDirectManipulation -v
```

## Nachweispflicht im Handoff
Du musst im Ergebnis liefern:
1. Liste der geänderten Dateien mit Begründung.
2. Commit-Hash + Commit-Message.
3. Exakte Testkommandos + Pass/Fail-Zahlen.
4. Grep-Nachweis:
   - Aufrufstellen von `show_projection_preview(` (nicht nur Definition),
   - Existenz von `test/test_projection_trace_workflow_w26.py`.
5. Rest-Risiken (falls vorhanden) klar benennen.

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeE_w26_recovery_hardgate.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Nächste 5 Folgeaufgaben

Wenn du einen Punkt nicht liefern kannst, sag explizit warum und welche konkrete Blockade vorliegt (Datei/Zeile/Exception).

