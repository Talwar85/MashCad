# HANDOFF_20260217_ai_small4_w32_zoom_badge_live

## 1. Problem
The zoom badge (`100%`) in the status bar was static – it never updated when zooming in the sketch editor, and had no interactivity. It appeared broken.

## 2. API/Behavior Contract

### A) Live Zoom (P0)
- `SketchEditor.zoom_changed` signal (Signal(int)) emitted on every zoom change
- Emitted in `wheelEvent` (mouse wheel zoom) and `_fit_view` (fit to content)
- Conversion: `zoom_pct = int(round(view_scale * 20))` (default view_scale=5.0 → 100%)
- `SketchEditor.set_zoom_to(percent: int)` – sets view_scale from percentage
- On 3D mode switch: badge resets to `100%`

### B) Zoom Presets (P1)
- `MashCadStatusBar.zoom_preset_requested` signal (Signal(int)) – emits preset percentage
- `MashCadStatusBar.zoom_fit_requested` signal (Signal()) – emits fit request
- Context menu on zoom badge click (only in 2D/sketch mode): 50%, 100%, 200%, Fit
- In 3D mode: click does nothing (no broken action)

### C) Wiring (MainWindow)
- `sketch_editor.zoom_changed` → `mashcad_status_bar.set_zoom`
- `mashcad_status_bar.zoom_preset_requested` → `sketch_editor.set_zoom_to`
- `mashcad_status_bar.zoom_fit_requested` → `sketch_editor._fit_view`

## 3. Impact (Dateien)
| Datei | Änderung |
|-------|----------|
| `gui/sketch_editor.py` | +Signal `zoom_changed`, +`_emit_zoom_changed()`, +`set_zoom_to()`, emit in `wheelEvent` & `_fit_view` |
| `gui/widgets/status_bar.py` | +Signals `zoom_preset_requested`/`zoom_fit_requested`, +`_on_zoom_badge_clicked()`, mode tracking, cursor |
| `gui/main_window.py` | +3 signal connections, +zoom reset on 3D switch |
| `test/test_status_bar_zoom_w32.py` | 14 new tests |

## 4. Validation

```powershell
conda run -n cad_env python -m py_compile gui/widgets/status_bar.py gui/sketch_editor.py gui/main_window.py
# Exit 0 ✅

conda run -n cad_env python -m pytest -q test/test_status_bar_zoom_w32.py
# 14 passed ✅
```

## 5. Rest-Risiken
- Zoom percentage formula `view_scale * 20` is approximate; if the default view_scale changes from 5.0, the 100% baseline shifts. Low risk since 5.0 is a well-established default.
- `test_discoverability_hints.py` and `test_ui_abort_logic.py` require a display server to run (MainWindow instantiation) – not a regression from this change, pre-existing limitation.
