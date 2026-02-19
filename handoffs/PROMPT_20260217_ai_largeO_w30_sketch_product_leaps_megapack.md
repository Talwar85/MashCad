# PROMPT_20260217_ai_largeO_w30_sketch_product_leaps_megapack

Du bist AI-LargeO auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere sichtbare Sketch-Product-Leaps (Fusion-/Onshape-Niveau), nicht nur Testpflege: direkteres Bearbeiten, klareres visuelles Feedback, robuste Constraints-Interaktion.

## Pflicht-Read
- `handoffs/HANDOFF_20260217_ai_largeI_w29_sketch_stabilization_hardgate.md`
- `handoffs/HANDOFF_20260217_ai_largeA_w24_sketch_interaction.md`
- `handoffs/HANDOFF_20260217_ai_largeC_w25_sketch_product_leaps.md`

## Harte Grenzen
1. No-Go Files:
- `modeling/__init__.py`
- `scripts/**`
- `gui/main_window.py`

2. Fokus auf:
- `gui/sketch_editor.py`
- `gui/sketch_tools.py` (falls nötig)
- neue/angepasste Tests in `test/harness/` + `test/test_sketch_editor_w26_signals.py` + `test/test_projection_trace_workflow_w26.py`

3. Verboten:
- Feature nur andeuten und dann skippen
- Dummy-UI ohne echte Interaktion

## Zielbild (DoD)
- Linie verhält sich beim direkten Drag wie Kreis (verschieben/achsenlogik/sichtbares Feedback).
- Rechteck-Linien-Drag passt Dimensionen kontrolliert an statt inkonsistentem Shape-Sprung.
- Arc-Handles (Radius + Start/End) sind konsistent pickbar und bearbeiten die Geometrie verlässlich.
- Ellipse/Polygon-Interaktion wirkt nicht "Punkte-Chaos": klare Primär-Handles + reduzierte visuelle Unruhe.

## Arbeitspakete
### AP1: Line Direct Manipulation 2.0
- Hover-Handles für Linie klar trennen: Mitte (Move), Endpunkte (Extend), optional Normalversatz.
- Drag-Verhalten mit Modifiern:
  - `Shift`: axis-lock
  - `Ctrl` (oder bestehender Modifier): Snapping
- Dirty-Rect/Render nur lokal aktualisieren.

### AP2: Rectangle Edge Resize Parity
- Wenn eine Rechteckkante gezogen wird, wird die passende Constraint-Dimension aktualisiert (Breite/Höhe), nicht das ganze Rechteck instabil verschoben.
- Cursor-Mapping korrekt (nicht verdreht).
- Löschen eines Rechtecks entfernt konsistent zugehörige Hilfspunkte/Handles.

### AP3: Arc Handle Completion
- `_pick_direct_edit_handle()` und Drag-Pfad für Arc Radius + Start/End-Angle schließen.
- SHIFT-Lock/Snap für Arc-Editing korrekt anwenden.
- Kein Ghost-State nach Cancel/ESC/Toolwechsel.

### AP4: Ellipse/Polygon UX Simplification
- Reduziere sichtbare Edit-Punkte auf sinnvolle Primärpunkte im Normalzustand.
- Zeige erweiterte Punkte erst bei aktivem Edit-Modus.
- Visuelles Feedback: aktive Handle-Hervorhebung + klare Cursorsemantik.

### AP5: Regression-Netz
- Ergänze/aktualisiere Harness-Tests für alle neuen Interaction-Pfade.
- Keine reine Snapshot-Assertions; teste Verhalten (State before/after + constraints).

## Pflicht-Validierung
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m py_compile gui/sketch_editor.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py test/test_projection_trace_workflow_w26.py
```

## Rückgabeformat
Erzeuge:
- `handoffs/HANDOFF_20260217_ai_largeO_w30_sketch_product_leaps_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. UX-Deltas (vorher/nachher kurz, konkret)
7. Nächste 5 Folgeaufgaben

## Qualitätslatte
- Mindestens 30 neue/angepasste Assertions über echte Interaktionen.
- Spürbare Produktverbesserung in Bedienbarkeit, nicht nur "refactor internals".
- Jede neue UX-Regel muss testbar und getestet sein.
