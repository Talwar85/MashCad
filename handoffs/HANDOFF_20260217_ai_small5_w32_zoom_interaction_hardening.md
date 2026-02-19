# HANDOFF_20260217_ai_small5_w32_zoom_interaction_hardening

## 1. Problem
W32 zoom badge had only attribute-level tests. No real interaction coverage for context menu actions, signal wiring, or 3D-mode guard behavior.

## 2. API/Behavior Contract

### Testability hook
- `MashCadStatusBar._build_zoom_menu()` → returns a `QMenu` with wired actions, separated from `_on_zoom_badge_clicked()` which calls `.exec()`. Tests call `_build_zoom_menu()` directly, trigger actions without blocking.

### New test classes (10 new tests, 24 total)
| Class | Tests | What it validates |
|-------|-------|-------------------|
| `TestZoomMenuBuilt` | 3 | Menu has 4 actions (50%, 100%, 200%, Fit), correct labels, 1 separator |
| `TestPresetActionEmitsSignal` | 4 | Each action.trigger() emits the correct signal with correct value |
| `TestThreeDModeBlocksMenu` | 1 | Simulated mouse click in 3D mode emits nothing |
| `TestPresetEndToEnd` | 2 | Full signal chain: preset → set_zoom_to → view_scale + badge text |

## 3. Impact
| Datei | Änderung |
|-------|----------|
| `gui/widgets/status_bar.py` | Extracted `_build_zoom_menu()` from `_on_zoom_badge_clicked()` (no UX change) |
| `test/test_status_bar_zoom_w32.py` | Added 10 interaction tests (14 → 24 total), fixtures, deprecation-free QMouseEvent |

## 4. Validation

```powershell
conda run -n cad_env python -m py_compile gui/widgets/status_bar.py test/test_status_bar_zoom_w32.py
# Exit 0 ✅

conda run -n cad_env python -m pytest -q test/test_status_bar_zoom_w32.py
# 24 passed in 4.28s ✅

conda run -n cad_env python -m pytest -q "test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate" "test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode"
# 2 passed in 13.33s ✅
```

## 5. Rest-Risiken
- Full-suite runs of `test_discoverability_hints.py` and `test_ui_abort_logic.py` may hang in headless environments (pre-existing, not related to this change). Individual test targeting with `::` works reliably.
- `pytest-timeout` is not installed; if added later, full-suite runs become safer.
