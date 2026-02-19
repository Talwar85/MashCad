# PROMPT_20260217_ai_small4_w32_zoom_badge_live

Du bist AI-SMALL-4 (UI Surface Fix) auf Branch `feature/v1-ux-aiB`.

## Kontext
Im unteren Statusbereich ist ein Badge `100%` sichtbar (Zoom), aber:
1. es aktualisiert sich nicht live,
2. es ist nicht interaktiv (keine Auswahl/Presets),
3. es wirkt dadurch wie ein defektes UI-Element.

Root-Cause-Hinweis (bereits geprüft):
- `gui/widgets/status_bar.py` enthält `set_zoom(...)`, aber es gibt aktuell keinen verdrahteten Aufruf aus MainWindow/Sketch-Flow.

## Ziel
Kleines, klar abgegrenztes Paket: Zoom-Badge im Statusbereich in 2D wirklich nutzbar machen, ohne Core/Modeling anzufassen.

## Harte Grenzen
- Nicht anfassen: `modeling/**`
- Nicht anfassen: Feature-/Kernel-Logik
- Fokus nur auf UI-Verkabelung + kleine UX-Interaktion

## Konkrete Aufgaben

### A) Live-Zoom im Status-Bar-Badge (P0)
- Verdrahte den 2D-Zoom aus `SketchEditor` in die `MashCadStatusBar`.
- Erwartetes Verhalten:
  - Beim Mausrad-Zoom in Sketch aktualisiert sich Badge sofort.
  - Bei „Fit/Ansicht anpassen“ aktualisiert sich Badge ebenfalls.
  - Beim Wechsel in 3D-Modus bleibt kein veralteter 2D-Wert stehen.

Technikvorschlag (du darfst äquivalent lösen):
- `SketchEditor`: neues Signal `zoom_changed` (z. B. `Signal(float, int)` oder `Signal(str)`).
- Emission bei allen Stellen, die `view_scale` ändern.
- `MainWindow`: connect auf `mashcad_status_bar`.
- `MashCadStatusBar`: Anzeigeformat klar halten (z. B. `"3.8x"` oder `%` konsistent).

### B) Kleine Interaktion: Zoom-Presets (P1)
- Mache das Zoom-Badge anklickbar (Context-Menu oder Popup mit Presets).
- Presets minimal: `50%`, `100%`, `200%`, `Fit`.
- Wirkung nur im Sketch-Modus; in 3D keine kaputte Aktion.
- Kein großes Redesign, nur funktional und robust.

### C) Regression-Tests (P0)
Füge kleine, schnelle Tests hinzu:
- Status-Bar zeigt Live-Update nach Zoom-Event.
- Preset-Klick triggert Zoomänderung im Sketch.
- 3D-Modus: Badge zeigt neutralen/fallback Zustand oder bleibt korrekt ohne falsche Aktion.

## Validierung (Pflicht)
```powershell
conda run -n cad_env python -m py_compile gui/widgets/status_bar.py gui/sketch_editor.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_status_bar_zoom_w32.py
```

## Qualitätskriterien
- Keine Skips hinzufügen.
- Keine bestehenden Tests deaktivieren/abschwächen.
- Keine Dummy-Implementierung (UI muss real reagieren).
- Änderungen klein halten, aber vollständig verdrahtet.

## Rückgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_small4_w32_zoom_badge_live.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Dateien)
4. Validation (exakte Commands + Ergebnis)
5. Rest-Risiken
