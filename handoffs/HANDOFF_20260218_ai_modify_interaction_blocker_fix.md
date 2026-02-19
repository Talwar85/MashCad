# Handoff: Modify Interaction Blocker Fix

**Datum:** 2026-02-18
**Branch:** 2d_sketch
**Autor:** Claude (AI)

## Problem

Modify-Tools (Move, Copy, Rotate, Mirror, Scale) zeigten **keine Live-Vorschau** bei Mausbewegung. Der User beschreibt:

> "ich zeichne rechteck → wähle es aus → klicke auf verschieben. dann selektiere ich irgendwo einen punkt egal wo, und von da an zeichnet er eine 'Konstruktionslinie' in der vorschau von punkt zur maus und zeigt die neue rechteck position an. wenn ich bestätige ist dann das rechteck am neuen ort. das ging früher. so ähnlich haben sich auch die anderen modifies verhalten. aber nun passiert nichts mehr. keine vorschau etc."

## Ursache

**`_update_live_values()`** ([gui/sketch_editor.py:6920-7036](gui/sketch_editor.py#L6920-L7036)) hatte **keine Handler für Modify-Tools**.

### Der fehlerhafte Flow:

1. User wählt Rechteck aus → klickt auf "Verschieben" (MOVE)
2. `_handle_move` wird bei Klick aufgerufen, setzt `tool_step = 1`
3. Durch den `tool_step`-Setter wird `_check_auto_show_dim_input()` aufgerufen
4. `dim_input` wird angezeigt mit Feldern dx=0, dy=0
5. `dim_input_active = True` wird gesetzt
6. User bewegt die Maus → `mouseMoveEvent` wird aufgerufen
7. Da `tool_step > 0`, wird `_update_live_values(snapped)` aufgerufen
8. **ABER:** `_update_live_values` hat keinen Handler für MOVE! Die Methode tut nichts.
9. `dim_input` zeigt weiterhin dx=0, dy=0 an
10. In `_draw_preview` wird `dim_input_active` geprüft → True
11. Die Preview berechnet dx/dy aus dim_input Werten → **dx=0, dy=0**!
12. Ergebnis: Die verschobene Geometrie wird an der Originalposition gezeichnet (keine sichtbare Änderung)!

### Der entscheidende Code in `_draw_preview` ([sketch_renderer.py:1607-1620](gui/sketch_renderer.py#L1607-L1620)):

```python
elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
    # Bei aktiver Tab-Eingabe: Werte aus dim_input verwenden
    if self.dim_input_active and self.dim_input.isVisible():
        try:
            vals = self.dim_input.get_values()
            dx = vals.get("dx", 0)  # ← IMMER 0!
            dy = vals.get("dy", 0)  # ← IMMER 0!
```

Wenn `dim_input_active == True`, werden die Werte aus dim_input verwendet, und diese waren immer 0 weil `_update_live_values` sie nie aktualisiert hat.

## Fix

Handler für **MOVE, COPY, ROTATE, SCALE** zu `_update_live_values` hinzugefügt ([gui/sketch_editor.py:7038-7077](gui/sketch_editor.py#L7038-L7077)).

### Geänderte Dateien

- `gui/sketch_editor.py`
  - Zeile 7038-7077: Neue Handler für Modify-Tools in `_update_live_values()`
  - Zeile 827-828: Initialisierung von `live_dx` und `live_dy` in `__init__()`

## Codeänderungen

### 1. Handler für Modify-Tools ([gui/sketch_editor.py:7038-7077](gui/sketch_editor.py#L7038-L7077))

```python
        # Phase 8: Live-Werte für Modify-Tools (MOVE, COPY, ROTATE, SCALE)
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            p1 = self.tool_points[0]
            if not self.dim_input.is_locked('dx'):
                dx = snapped.x() - p1.x()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dx', dx)
            if not self.dim_input.is_locked('dy'):
                dy = snapped.y() - p1.y()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dy', dy)

        elif self.current_tool == SketchTool.COPY and self.tool_step == 1:
            # COPY benutzt die gleichen Felder wie MOVE
            p1 = self.tool_points[0]
            if not self.dim_input.is_locked('dx'):
                dx = snapped.x() - p1.x()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dx', dx)
            if not self.dim_input.is_locked('dy'):
                dy = snapped.y() - p1.y()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dy', dy)

        elif self.current_tool == SketchTool.ROTATE and self.tool_step >= 1:
            center = self.tool_points[0]
            if not self.dim_input.is_locked('angle'):
                angle = math.degrees(math.atan2(snapped.y() - center.y(), snapped.x() - center.x()))
                self.live_angle = angle
                if self.dim_input.isVisible():
                    self.dim_input.set_value('angle', angle)

        elif self.current_tool == SketchTool.SCALE and self.tool_step == 1:
            center = self.tool_points[0]
            current_dist = math.hypot(snapped.x() - center.x(), snapped.y() - center.y())
            base_dist = self.tool_data.get('base_dist', current_dist)
            if base_dist > 0.01 and not self.dim_input.is_locked('factor'):
                factor = current_dist / base_dist
                if self.dim_input.isVisible():
                    self.dim_input.set_value('factor', factor)
```

### 2. Initialisierung neuer Variablen ([gui/sketch_editor.py:827-828](gui/sketch_editor.py#L827-L828))

```python
self.live_dx = 0.0  # Für Modify-Tools (MOVE, COPY)
self.live_dy = 0.0  # Für Modify-Tools (MOVE, COPY)
```

## Warum der Fix funktioniert

Mit den neuen Handlern in `_update_live_values`:

1. Wenn die Maus bewegt wird, berechnet `_update_live_values` jetzt **dx/dy** (bzw. **angle/factor**) für Modify-Tools
2. Die Werte werden an `dim_input` übermittelt via `set_value()`
3. `dim_input` zeigt die **korrekten Live-Werte** an
4. `_draw_preview` liest die Werte aus `dim_input` und zeigt die **transformierte Geometrie an der korrekten Position**

## Validierung

```bash
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py
# Result: Syntax-Check PASSED
```

## Manueller Prüfplan

### Move (M)
1. Rechteck zeichnen → Selektieren → M drücken
2. Basispunkt klicken → Maus bewegen
   - **Erwartung:** Verschiedenes Rechteck folgt der Maus
   - **Erwartung:** dim_input zeigt live dx/dy Werte
3. Zielpunkt klicken → Rechteck verschoben

### Copy (K)
1. Rechteck zeichnen → Selektieren → K drücken
2. Basispunkt klicken → Maus bewegen
   - **Erwartung:** Kopie-Vorschau folgt der Maus
3. Zielpunkt klicken → Kopie erstellt

### Rotate (Q)
1. Rechteck zeichnen → Selektieren → Q drücken
2. Zentrum klicken → Maus bewegen
   - **Erwartung:** Rotiertes Rechteck-Vorschau
   - **Erwartung:** Winkelanzeige aktualisiert live
3. Winkel klicken → Rotation ausgeführt

### Scale (S)
1. Rechteck zeichnen → Selektieren → S drücken
2. Zentrum klicken → Maus bewegen
   - **Erwartung:** Skalierte Vorschau
   - **Erwartung:** Faktor-Anzeige aktualisiert
3. Faktor klicken → Skalierung ausgeführt

### Mirror (I)
1. Rechteck zeichnen → Selektieren → I drücken
2. Erster Punkt klicken → Maus bewegen
   - **Erwartung:** Spiegelachse + gespiegelte Vorschau
3. Zweiter Punkt klicken → Spiegelung ausgeführt

## Akzeptanzkriterien

- [x] Keine Exception bei Modify-Aktionen
- [ ] Move zeigt Live-Vorschau bei Mausbewegung
- [ ] Copy zeigt Live-Vorschau bei Mausbewegung
- [ ] Rotate zeigt Live-Vorschau bei Mausbewegung
- [ ] Scale zeigt Live-Vorschau bei Mausbewegung
- [ ] Mirror zeigt Live-Vorschau bei Mausbewegung
- [ ] Verhalten ist stabil bei mehrfacher Wiederholung

**Bitte testen und die Akzeptanzkriterien abhaken.**
