# HANDOFF_20260216_core_to_glm47_w4

**Date:** 2026-02-16 00:06
**From:** Codex (Core/KERNEL)
**To:** GLM 4.7 (UX/WORKFLOW)
**ID:** core_to_glm47_w4

## 1. Problem
Right-click abort/background-clear war funktional inkonsistent und UI-Tests waren zuvor nicht stabil reproduzierbar.
Zusätzlich nutzte der Abort-Pfad direkte/unklare Render-Aufrufe (`self.request_render()`), die im Fehlerfall nicht robust waren.

## 2. API/Behavior Contract
- `gui/viewport_pyvista.py`
  - `cancel_drag()` nutzt jetzt einen sicheren Render-Request-Pfad statt direkter Aufrufe.
  - `clear_selection()` nutzt denselben sicheren Render-Request-Pfad.
  - Neuer Helper: `_safe_request_render(immediate=False)` mit Guards auf verfügbarem Plotter.
- Right-click Verhalten (aus W6-Stand) bleibt erhalten:
  - active drag cancel
  - background clear
  - object context menu

## 3. Impact
Geändert:
- `gui/viewport_pyvista.py`
- `test/test_ui_abort_logic.py` (Test-Env-Härtung: `QT_OPENGL=software`)
- `test/harness/test_interaction_consistency.py` (Test-Env-Härtung: `QT_OPENGL=software`)

## 4. Validation
Ausgeführt:
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_cancels_drag test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_background_clears_selection -vv
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -vv
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
```

Resultate:
- `test_right_click_cancels_drag`: passed
- `test_right_click_background_clears_selection`: passed
- `test/test_ui_abort_logic.py`: `10 passed`
- `test/harness/test_interaction_consistency.py`: `1 passed, 3 skipped`
- `test/test_browser_tooltip_formatting.py` + `test/test_feature_commands_atomic.py`: `11 passed`

Hinweis:
- VTK meldet weiterhin `wglMakeCurrent`-Warnings auf Windows beim Cleanup, aber ohne Test-Fail in den o.g. Läufen.

## 5. Breaking Changes / Rest-Risiken
- Kein API-Break im Core/Kernelscope.
- Rest-Risiko: Windows OpenGL-Cleanup-Warnings (Noise), funktional aber reproduzierbar grüne Tests in den genannten Suiten.

## Nächste 3 priorisierte Folgeaufgaben
1. UI-Harness von Hard-OpenGL entkoppeln (z. B. dedizierter Test-Render-Mode mit reduziertem VTK-Lifecycle).
2. Interaction-Consistency-Skips abbauen (circle/rectangle/line drag) mit deterministischem Event-Setup.
3. Right-click Contract als explizite Regression im UI-Gate dokumentieren (P0-Blocker bei Fail).
