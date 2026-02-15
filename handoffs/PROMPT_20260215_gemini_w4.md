# PROMPT_20260215_gemini_w4

Du arbeitest in `feature/v1-ux-aiB`.

Kontext:
- Lies zuerst `handoffs/HANDOFF_20260215_core_to_gemini_w4.md`.
- Ziel: Right-Click Abort/Selection Verhalten im 3D-Viewport stabil machen.

Aufgaben:
1. Behebe `gui/viewport_pyvista.py` so, dass es nur eine aktive `eventFilter`-Implementierung gibt.
2. In dieser aktiven `eventFilter`:
   - Right-Click-Press cancelt aktiven Drag (`is_dragging/_offset_plane_dragging/_split_dragging`).
   - Right-Click-Klick in leeren Raum löscht Selection.
3. Initialisiere `_right_click_start_pos` und `_right_click_start_time` in `__init__`.
4. Stelle sicher, dass Kontextmenü/Orbit/Pan Verhalten nicht regressiert.
5. Passe Tests nur an, wenn es wirklich ein Test-Bug ist. Primär Produktcode fixen.

Pflicht-Validierung:
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py
```

Rückgabeformat:
- Kurze Änderungsliste (Datei + Zweck)
- Exakte Testresultate (passed/failed/skipped)
- Offene Risiken
