# PROMPT_20260217_ai_largeU_w32_sketch_product_leaps_ultrapack

Du bist AI-LARGE-U (Sketch UX + Interaction Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses, sichtbares Produkt-Upgrade im 2D-Sketch-Bereich.
Nicht nur Tests stabilisieren, sondern echte Bedienqualitaet auf Profi-Niveau heben.

## Kontext
- Bisherige Basis ist vorhanden (Circle/Rectangle Direct Edit, W24-W31 Regression-Pakete).
- Offene Erwartung: mehr Fusion-/Onshape-Paritaet bei direkter Manipulation, klareres visuelles Feedback, robustere Constraint-Reaktionen.

## Harte Regeln (STRICT)
1. No-Go:
- `modeling/**`
- `gui/main_window.py`
- `gui/browser.py`
- `gui/viewport_pyvista.py`

2. Fokus-Dateien:
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `gui/sketch_renderer.py`
- `gui/sketch_snapper.py`
- `test/**` (nur sketch-bezogene Tests)

3. Verboten:
- keine `skip`/`xfail` neu einfuehren
- keine bestehenden Tests deaktivieren
- keine `.bak`/`temp_*` Dateien erzeugen
- keine Placebo-Tests (nur Attributchecks ohne Verhalten)

4. Lieferpflicht:
- mind. 3 echte UX-Leaps mit sichtbarem Verhalten
- mind. 1 Performance-Verbesserung im Interaktionspfad
- mind. 1 Robustheitsverbesserung fuer ESC/Rechtsklick/Undo

---

## EPIC S1 - Direct Manipulation Parity (P0)
Ziel: Arc/Ellipse/Polygon/Line Verhalten deutlich naeher an Profi-CAD.

### S1.1 Arc Radius + Center Drag
- Arc: Radius-Handle eindeutig pickbar machen.
- Arc: Center-Drag und Radius-Drag muessen stabil getrennt sein.
- Solver-Fehler bei Drag: sauberer rollback + klare HUD-Meldung.

### S1.2 Ellipse Handles vereinfachen
- Standardmodus: nur relevante Handles sichtbar (kein Punkt-Overload).
- Aktivmodus waehrend Drag: erweiterte Handles einblenden (z. B. Nebenachse/Rotation).
- Handle-Hitbox fuer hohen/niedrigen Zoom robust machen.

### S1.3 Polygon Direct Edit
- Polygon als Objekt verschiebbar (Center-Drag).
- Vertex-Drag robust + visuelle Priorisierung des aktiven Vertex.
- Optional: Seitenzahl-Anpassung ueber klaren, expliziten Interaktionsweg (kein Hidden Behavior).

---

## EPIC S2 - Constraint-faehiges Editieren (P0)
Ziel: bei Linie/Rechteck nicht nur Geometrie ziehen, sondern kontrolliert Constraint-freundlich.

### S2.1 Line Drag Behavior
- Linie als Ganzes verschieben (ohne unbeabsichtigte Längenänderung), wenn passende Freiheitsgrade da sind.
- Endpunkt-Drag darf erwartbar Constraint-Konflikte melden, ohne Zustand zu zerstoeren.

### S2.2 Rectangle Edge Drag
- Kanten-Drag passt genau eine Hauptdimension an, Gegenkante bleibt konsistent.
- Konfliktfall: klare Fehlermeldung + kein inkonsistenter Halbzustand.

### S2.3 Undo/Redo Granularitaet
- Ein abgeschlossener Drag = genau ein Undo-Step.
- Keine Undo-Flut pro Mouse-Move.

---

## EPIC S3 - Discoverability + Visual Feedback (P1)
Ziel: User sieht sofort, was gerade moeglich ist.

### S3.1 Kontext-Hinweise
- Beim Hover auf editierbare Geometrie: kurzer Hint fuer Drag-Verhalten.
- Bei aktiver Manipulation: Hint fuer ESC/Rechtsklick-Abbruch sichtbar.

### S3.2 Cursor/Handle-Konsistenz
- Cursor-Semantik muss zur Richtung/Art des Drags passen.
- Keine invertierten Resize-Cursor bei horizontal/vertikal.

### S3.3 HUD-Fehlertexte
- Constraint-Konflikttexte kurz, konkret, handlungsorientiert.

---

## EPIC S4 - Interaktions-Performance (P1)
Ziel: fluesiges Dragging auch in groesseren Sketchen.

### S4.1 Hot-Path entschlacken
- Keine unnötigen Voll-Redraws im Drag-Hotpath.
- Dirty-Rect/Update-Culling nachziehen, falls noch Luecken.

### S4.2 Solver-Throttling
- Bei kontinuierlichem Drag nur so oft loesen wie noetig.
- Final solve bei mouse release erzwingen.

### S4.3 Instrumentation
- Minimal-Metriken fuer Drag-Perf (z. B. solve count / sec, dropped frame indicators in logs).

---

## Testpflicht (P0)
Erweitere/erstelle robuste Verhaltens-Tests, z. B.:
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/test_line_direct_manipulation_w30.py`
- neue Suite: `test/test_sketch_product_leaps_w32.py`

Pflichtabdeckung:
1. Arc radius handle pick + drag
2. Ellipse simplified/active handle behavior
3. Polygon center/vertex drag
4. Rectangle edge drag constraint behavior
5. Undo granularity for drag sessions
6. ESC == RightClick abort parity waehrend drag

---

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/sketch_renderer.py gui/sketch_snapper.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py test/test_line_direct_manipulation_w30.py
conda run -n cad_env python -m pytest -q test/test_sketch_product_leaps_w32.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

Wenn etwas fehlschlaegt:
- nicht skippen
- Root-Cause dokumentieren
- Fix + Re-Run liefern

---

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_largeU_w32_sketch_product_leaps_ultrapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Dateien + Kern-Diff)
4. Validation (exakte Commands + Ergebnis)
5. Breaking Changes / Rest-Risiken
6. Nächste 3 priorisierte Folgeaufgaben
