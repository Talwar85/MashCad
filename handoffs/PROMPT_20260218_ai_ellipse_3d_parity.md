Du arbeitest in `C:\LiteCad` auf Branch:
`task/ai-ellipse-3d-parity-w34`

## Ziel
Ellipse im 3D-Modus muss dieselbe Produktqualität wie Circle haben:
- korrekt sichtbar
- korrekt auswählbar/bearbeitbar
- korrekt als Profil nutzbar
- korrekt extrudierbar
- korrekt über Save/Load/Undo/Redo

## Harte Regeln (verbindlich)
1. CAD-Kernel-First: native Geometrie (`Ellipse2D`) bleibt erhalten.
2. Keine Quickhacks, keine stillen Fallbacks, keine temporären Umgehungen.
3. Keine neuen `skip`/`xfail`.
4. Nicht nur Tests grün: visuelle und funktionale Validierung ist Pflicht.
5. Circle-Verhalten ist Referenz für Parität.

## Scope (primär)
- `sketcher/geometry.py`
- `sketcher/sketch.py`
- `gui/sketch_editor.py`
- `gui/sketch_renderer.py`
- `gui/viewport_pyvista.py`
- `modeling/__init__.py` (nur falls für Extrude-Pipeline nötig)

## Pflichtanforderungen
### A) 3D-Mode Darstellung
- Ellipse wird im 3D-Sketch-Kontext korrekt dargestellt (keine Segmentartefakte).
- Selektion/Highlighting behandelt Ellipse als Ganzes.

### B) Profile + Extrude
- Geschlossene Ellipsenprofile werden zuverlässig erkannt.
- Extrude einer Ellipse funktioniert wie Circle-Extrude.
- Ellipse mit innerer Ellipse (Ring) funktioniert wie bei Kreisprofilen.
- Keine Regression bei Circle-Profilen.

### C) Lifecycle
- Undo/Redo erhält Ellipse als native Ellipse.
- Save/Load/Reopen erhält Ellipse vollständig (Typ + Parameter + Constraints).
- Kein Downgrade zu Linien.

### D) Edit-Parität
- Verhalten im 3D-Modus ist konsistent mit Circle-Qualität.
- Bearbeitungszustände dürfen keine Geometrie zerstören.

## Test+Fix Loop (MUSS)
1. Repro-Matrix für Ellipse erstellen (Render, Select, Profile, Extrude, Undo/Redo, Save/Load).
2. Pro roter Zelle Root Cause bestimmen.
3. Minimalen, fachlich sauberen Fix implementieren.
4. Test ergänzen/aktualisieren.
5. Visuell validieren (vorher/nachher).
6. Wiederholen bis Matrix grün.

## Pflichtvalidierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_renderer.py gui/viewport_pyvista.py sketcher/geometry.py sketcher/sketch.py modeling/__init__.py
```

Zusätzlich:
- neue/angepasste pytest-Fälle für Ellipse-3D-Parität
- Regression-Check für Circle/Slot/Arc

## Verboten
- Ellipse als persistente Linien-Approximation
- nur Teständerungen ohne Produktcodefix
- "works on my machine" ohne reproduzierbare Schritte

## Abgabe
Datei:
`handoffs/HANDOFF_20260218_ai_ellipse_3d_parity.md`

Pflichtstruktur:
1. Root Cause(s)
2. Exakte Änderungen (Datei/Funktion)
3. Paritätsnachweis Circle vs Ellipse
4. Testnachweis
5. Visuelle Validierung
6. Rest-Risiken / offene Blocker
