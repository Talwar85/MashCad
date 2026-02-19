# PROMPT_20260217_ai_largeO_w30_rerun_hardfail

Du bist AI-LargeO auf Branch `feature/v1-ux-aiB`.

## Kontext
Der vorherige W30-O Lauf wurde ABGELEHNT:
- Keine nachweisbaren Sketch-Produkt-Aenderungen im Branch.
- Claims standen im Handoff, aber Diffs in Sketch-Dateien fehlten.

## Ziel (non-negotiable)
Liefere reale, sichtbare Sketch Product Leaps mit echten Code-Diffs in Sketch-Bereich.

## Harte Regeln
1. Delivery gilt nur, wenn geaendert wurde in mindestens einem Kernfile:
- `gui/sketch_editor.py` (Pflicht)
- optional: `gui/sketch_tools.py`
- plus passende Tests

2. Verboten:
- "Done" ohne Code-Diff in Sketch-Files.
- Nur Tests aendern ohne Produkt-Verhalten.
- Nur Refactor ohne wahrnehmbaren UX-Effekt.

3. No-Go Files:
- `modeling/**`
- `gui/main_window.py`
- `scripts/**`

## Pflichtarbeitspakete
### AP1 Line Direct Manipulation Parity
- Linie muss sich verhalten wie Kreis:
  - Move via Center/Line-Hit
  - Endpoint Drag fuer Geometrieanpassung
  - klare Cursor-Paritaet

### AP2 Rectangle Edge Resize Constraint-First
- Kante ziehen aktualisiert kontrolliert Breite/Hoehe (keine instabilen Spruenge).
- Cursor-Ausrichtung korrekt.

### AP3 Arc Handle Completion
- Radius + Start/End-Angle Handles robust pickbar und dragbar.
- SHIFT-Lock/Snap konsistent.

### AP4 Ellipse/Polygon Visual Simplification
- Reduzierte Primar-Handles im Normalmodus.
- Erweiterte Handles nur im aktiven Edit-Kontext.
- klares visuelles Feedback fuer aktives Handle.

### AP5 Regression-Netz
- Neue/erweiterte Interaction-Tests mit echten Zustandspruefungen.
- Keine Pseudo-Assertions ohne Verhaltenswert.

## Pflicht-Validierung
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m py_compile gui/sketch_editor.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py test/test_projection_trace_workflow_w26.py
```

## Abnahme-Gate (hart)
- Kein Diff in `gui/sketch_editor.py` -> DELIVERY = FAIL.
- Keine verhaltensbezogenen Tests fuer neue Interaktion -> DELIVERY = FAIL.
- Claims ohne reproduzierbare Tests -> DELIVERY = FAIL.

## Rueckgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeO_w30_rerun_hardfail.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Datei, Methoden, Vorher/Nachher)
4. Validation (Commands + Resultate)
5. Breaking Changes / Rest-Risiken
6. UX-Deltas (messbar)
7. Naechste 5 Folgeaufgaben

## Zusatzpflicht
- Fuehre "Changed Methods Map" auf (Methodenname + Zweck + Testreferenz).
- Nenne mindestens 3 konkrete Nutzer-Deltas (was jetzt direkt besser bedienbar ist).
