Du arbeitest auf Branch `stabilize/2d-sketch-gap-closure-w34` in `C:\LiteCad`.

## Mission
2D-Sketch soll fachlich stabil abgeschlossen werden (kein 3D-Ausbau in diesem Paket).
Du analysierst Gaps und schliesst sie mit einem echten Test+Fix-Loop.

## Verbindliche Regeln (MUSS)
1. CAD-Kernel-First. Keine Alternativloesungen.
2. Ellipse MUSS native `Ellipse2D` bleiben. Keine Linien-/Segment-Approximation.
3. Keine Quickhacks, keine kurzfristigen Umgehungen, keine stillen Fallbacks.
4. Keine neuen `skip`/`xfail` Marker.
5. Visuale Validierung ist Pflicht, nicht nur technische Tests.
6. Scope nur 2D-Sketch/Sketcher. Keine grossen 3D-Features in diesem Paket.
7. Jede Aenderung muss Undo/Redo/Save/Load/Reopen beruecksichtigen.

## Problemkontext
Ab Commit `57d48aadc19d74855f36f553b5154497c94474fe` wurden viele 2D-Fixes gemacht.
Es ist unklar, ob alles in Standardprozesse/Test-Suiten sauber integriert wurde.
Vermutung: Teile sind noch Quickhacks oder lifecycle-unvollstaendig.

## Pflicht-Analyse (Gap-Matrix)
Erstelle zuerst eine Matrix fuer folgende Shapes mit den Spalten:
- Create
- Select
- Body-Drag
- Handle-Drag
- Rotate
- Constraint-Edit
- Undo/Redo
- Save/Load/Reopen
- Profile/Extrude-Readiness (nur 2D-Seite: Profilbildung stabil, keine 3D-Implementierung)

Shapes:
1. Line
2. Circle
3. Rectangle
4. Polygon
5. Arc (3-point arc)
6. Ellipse (native)
7. Spline
8. Slot

## Fachliche Zielvorgaben
- **Circle**: Mittelpunkt-Drag verschiebt, Rand-Drag aendert Radius (Referenz, darf nicht regressieren).
- **Rectangle**: Kanten-Drag vergroessert/verkleinert mit korrekter Constraint-Anpassung (Referenz).
- **Polygon**:
  - Mittelpunkt-Drag verschiebt gesamtes Polygon ohne Formzerstoerung.
  - Radius/Outer-Drag skaliert konsistent.
  - Linien einzeln verzerren ist NICHT erlaubt.
- **Arc (3-point)**:
  - Arc-Seite korrekt (durch die drei Eingabepunkte semantisch richtig).
  - Keine Regression fuer Slot.
- **Ellipse**:
  - Native Ellipse2D, kein Segment-Scheinobjekt.
  - Zentrumsgriff fuer Gesamtverschiebung.
  - Korrektes Resize/Rotate auf Objektebene.
  - Constraint-Edit wirkt korrekt auf echte Ellipse-Geometrie.
  - Lifecycle komplett: save/load/undo/redo/reopen.
- **Spline**:
  - Segmentweise Selektion/Drag darf Spline nicht zerlegen.
  - Drag am Pfad verschiebt gesamte Spline.
  - Punkt-/Handle-Edit nur wenn explizit Punkte/Handles gefasst.
- **Slot**:
  - Erstellung ok, aber Direct Edit und Constraint-Edit muessen stabil werden.
  - Radius/Dimension-Edit darf nach Reopen nicht zerstoeren.
  - Move/Rotate/Resize konsistent auf Objektebene.

## Arbeitsablauf (MUSS)
1. Gap-Matrix erstellen (IST).
2. Pro roter Zelle: Root Cause finden.
3. Minimalen Fix implementieren.
4. Test erweitern/anpassen.
5. Visuell validieren.
6. Naechste rote Zelle.
7. Abschluss erst wenn Matrix komplett gruen oder Restblocker klar als Blocker ausgewiesen.

## Dateien (erwarteter Fokus)
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `gui/sketch_renderer.py`
- `sketcher/geometry.py`
- `sketcher/sketch.py`
- ggf. `sketcher/__init__.py` nur falls notwendig

## Pflichtvalidierung
Fuehre mindestens aus:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/sketch_renderer.py sketcher/geometry.py sketcher/sketch.py
```

Ergaenze gezielte Tests fuer die betroffenen Shape-Gaps (keine Fake-Abdeckung).

## Verboten
- "Fix" nur in Testdatei ohne Produktcode-Anpassung.
- Segment-Ersatz fuer native Geometrie.
- Skips/XFails zur Gruenfaerbung.
- Scope-Drift in unrelated 3D-Themen.

## Rueckgabe
Datei:
`handoffs/HANDOFF_20260218_ai_2d_gap_closure_kernel_hardline.md`

Struktur:
1. Gap-Matrix (vorher/nachher)
2. Root Cause je Shape
3. Geaenderte Dateien/Funktionen
4. Lifecycle-Check (Undo/Redo/Save/Load/Reopen)
5. Visual-Checkliste
6. Rest-Risiken/Blocker
7. Nächste 3 priorisierte Schritte
