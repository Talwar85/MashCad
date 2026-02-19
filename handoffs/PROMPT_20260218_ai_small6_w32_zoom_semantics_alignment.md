# PROMPT_20260218_ai_small6_w32_zoom_semantics_alignment

Du bist AI-SMALL-6 (Zoom UX Consistency) auf Branch `feature/v1-ux-aiB`.

## Problem
Im Sketch gibt es aktuell inkonsistente Zoom-Semantik:
- Overlay im Canvas zeigt z. B. `Zoom: 8.7x`
- Status-Bar-Badge zeigt z. B. `175%`

Obwohl intern eine Umrechnung existiert, wirkt das für Nutzer wie ein Fehler.
Ziel ist **eine klare, konsistente Zoom-Anzeige** ohne Verwirrung.

## Mission
Aligniere Zoom-Anzeige in Sketch-Overlay und Status-Bar auf eine einheitliche Semantik.

## Scope
Erlaubte Dateien:
- `gui/sketch_editor.py`
- `gui/sketch_renderer.py`
- `gui/widgets/status_bar.py`
- `gui/main_window.py` (nur Signal-/Wiring-Anpassung, falls nötig)
- `test/test_status_bar_zoom_w32.py`
- neue Tests: `test/test_zoom_semantics_alignment_w32.py` (falls sinnvoll)

No-Go:
- `modeling/**`
- `gui/viewport_pyvista.py`

## Harte Regeln
1. Keine neuen `skip`/`xfail`.
2. Keine bestehenden Assertions verwässern.
3. Keine `.bak`/`temp_*` Dateien erzeugen.
4. Nicht nur Texte ändern: Semantik muss technisch aus einer gemeinsamen Quelle kommen.

## Konkrete Aufgaben

### A) Single Source of Truth für Zoom-Label (P0)
- Implementiere eine zentrale Zoom-Formatlogik (z. B. helper), die sowohl Overlay als auch Status-Bar nutzen.
- Keine doppelte, voneinander abweichende Formatierung mehr.

### B) Einheitliche Anzeige (P0)
- Empfohlen: beide zeigen denselben Primärwert in `x` (z. B. `8.7x`).
- Falls zusätzlich `%` angezeigt wird, dann konsistent und eindeutig (z. B. `8.7x (175%)`) an beiden Stellen.
- Wichtig: Nutzer darf keine widersprüchlichen Zahlen sehen.

### C) Presets/Interaktion weiter funktionsfähig (P1)
- Bestehende Zoom-Preset-Interaktion (Status-Bar) muss weiterhin funktionieren.
- Falls Labels geändert werden, Presets trotzdem eindeutig benutzbar halten.

### D) Regression-Tests (P0)
Mindestens folgende Fälle absichern:
1. `view_scale`-Änderung aktualisiert Overlay und Status-Bar konsistent.
2. Wheel-Zoom -> beide Anzeigen synchron.
3. Fit-View -> beide Anzeigen synchron.
4. Preset-Klick -> beide Anzeigen synchron.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_renderer.py gui/widgets/status_bar.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_status_bar_zoom_w32.py
conda run -n cad_env python -m pytest -q test/test_zoom_semantics_alignment_w32.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

## Akzeptanzkriterien
- Kein numerischer Widerspruch zwischen Overlay und Status-Bar.
- Zoom-Information ist für Nutzer sofort nachvollziehbar.
- Alle Pflichttests grün.

## Rückgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_small6_w32_zoom_semantics_alignment.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (Commands + Ergebnisse)
5. Rest-Risiken
