# PROMPT_20260216_gemini_w5

Du arbeitest auf Branch `feature/v1-ux-aiB`.

## Kontext (zuerst lesen)
- `handoffs/PROMPT_20260215_gemini_w4.md`
- `handoffs/HANDOFF_20260215_core_to_gemini_w4.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w6.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w7.md`

Du hängst aktuell bei W4. Ziel ist ein fokussierter Catch-up auf P0/P1 ohne Scope-Ausweitung.

## Harte Regeln
1. **Nur UI-Ownership**
- erlaubt: `gui/**`, UI-nahe Tests in `test/**`
- nicht erlaubt: `modeling/**`

2. Kein Refactor außerhalb des Problemkontexts.
3. Keine Placeholders; jede Behauptung mit Repro-Command.

## Aufgaben (Reihenfolge bindend)

### 1) P0 UI-Infrastruktur unblocken
Fix in `gui/widgets/status_bar.py`:
- `tr()`-Nutzung robust machen (Import oder Fallback), sodass MainWindow-Setup nicht crasht.
- Ziel: `NameError: tr not defined` darf nicht mehr auftreten.

### 2) P0 Viewport Abort/Selection Logik finalisieren
Fix in `gui/viewport_pyvista.py`:
- genau **eine** aktive `eventFilter`-Logik sicherstellen
- Right-Click-Press cancelt aktive Drags zuverlässig:
  - `is_dragging`
  - `_offset_plane_dragging`
  - `_split_dragging`
- Right-Click auf Leerraum löscht Selection zuverlässig
- Kontextmenü/Orbit/Pan dürfen nicht regressieren

### 3) P1 Drift-UX kompatibel machen
Im UI-Mapping sicherstellen:
- `tnp_ref_drift` wird als recoverable warning/fallback dargestellt, nicht als hard error.
- Falls Panel/Tooltip vorhanden: kurze Nutzerbotschaft + next action anzeigen.

### 4) Tests stabilisieren (nur wenn produktlogisch notwendig)
Primär Produktcode fixen, Tests nur minimal anpassen, wenn Testannahme falsch/alt ist.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
```

## Rückgabeformat
Datei: `handoffs/HANDOFF_20260216_gemini_w5.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (exakte Commands + Resultate)
5. Breaking Changes / Rest-Risiken

Zusatz:
- Liste geänderter Dateien (Datei + 1 Satz Zweck)
- Offene Blocker mit Owner/ETA
