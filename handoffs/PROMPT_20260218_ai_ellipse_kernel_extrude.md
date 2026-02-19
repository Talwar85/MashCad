Du arbeitest in `C:\LiteCad` auf Branch:
`task/ai-ellipse-kernel-extrude-w34`

## Mission
Ellipse muss in der 3D-Extrude-Pipeline dieselbe Stabilität wie Circle haben.
Fokus ist Kernel-/Profil-/Persistenzkette, nicht UI-Polish.

## Harte Regeln
1. CAD-Kernel-First: native Ellipse-Geometrie bleibt erhalten.
2. Keine Linien-Ersatzlösung als finale Pipeline.
3. Keine Quickhacks, keine stillen Fallbacks.
4. Keine neuen skip/xfail Marker.
5. Circle-Pipeline ist Referenz und darf nicht regressieren.

## Scope
- `modeling/__init__.py`
- `sketcher/sketch.py`
- `sketcher/geometry.py`
- ggf. `modeling/features/*` nur wenn zwingend nötig
- Tests in `test/**` passend zum Scope

## Pflichtziele
### 1) Profilbildung
- Ellipse-Profile werden robust als geschlossene Profile erkannt.
- Ellipse + Hole (innere Ellipse) wird korrekt als Shell-Profil erkannt.
- Geometrie-Mapping für Profile bleibt stabil/deterministisch.

### 2) Extrude-Parität zu Circle
- Einfache Ellipse -> Extrude solid funktioniert.
- Ellipse-Ring -> Extrude mit Loch funktioniert.
- Verhalten konsistent mit Circle-Profilen.

### 3) Determinismus
- Mehrfaches Rebuild liefert konsistente Resultate.
- Keine instabilen Referenzen durch Ellipse-Pfad.

### 4) Lifecycle
- Save/Load/Reopen erhält Ellipse-Extrude korrekt.
- Undo/Redo auf Ellipse-Extrude stabil.

## Test+Fix Loop (MUSS)
1. Pipeline-Matrix erstellen:
   - profile detect
   - extrude simple
   - extrude with hole
   - rebuild stability
   - undo/redo
   - save/load/reopen
2. Root Cause je Fail bestimmen.
3. Minimalen Kernel-nahen Fix implementieren.
4. Test ergänzen.
5. Wiederholen bis Matrix grün.

## Pflichtvalidierung
```powershell
conda run -n cad_env python -m py_compile modeling/__init__.py sketcher/sketch.py sketcher/geometry.py
```

Zusätzlich gezielte pytest-Läufe für:
- Profilerkennung
- Ellipse-Extrude
- Circle-Regression
- Roundtrip/Persistenz

## Verboten
- UI-only Workarounds für Kernel-Probleme
- Testmanipulation ohne echte Produktkorrektur
- finale Implementierung über approximierte Linienpfade

## Abgabe
Datei:
`handoffs/HANDOFF_20260218_ai_ellipse_kernel_extrude.md`

Pflichtstruktur:
1. Root Cause Pipeline-Gaps
2. Geänderte Funktionen/Dateien
3. Parität Ellipse vs Circle
4. Testresultate (exakte Commands)
5. Rest-Risiken + Folgeaufgaben
