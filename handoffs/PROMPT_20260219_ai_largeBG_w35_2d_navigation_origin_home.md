You are AI-LargeBG on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`
- `handoffs/HANDOFF_20260217_ai_small4_w32_zoom_badge_live.md`

Objective:
- Fix 2D sketch navigation usability:
  - fast return to origin (0,0),
  - visible and working Home action in 2D,
  - consistent zoom semantics between viewport and status badge,
  - avoid navigation drift chaos.

Hard rules:
1. CAD-kernel-only for geometry/state; UI hints must reflect real camera/sketch transform.
2. No fake badge value disconnected from real scale.
3. No regression in 3D navigation.
4. No test weakening. No merge before user acceptance.

Scope (allowed):
- `gui/sketch_editor.py`
- `gui/main_window.py` (2D discoverability only)
- `gui/widgets/**` (if badges/hints live there)
- `test/test_discoverability_hints.py`
- `test/test_sketch_editor_w26_signals.py`

No-go:
- `modeling/**`
- `gui/viewport_pyvista.py` camera core unless absolutely required with note

Work packages:
1. Home/Origin in 2D:
   - explicit action and shortcut behavior in sketch mode.
   - deterministic camera reset to full visible geometry and origin aid.
2. Zoom semantics:
   - badge value tied to actual transform used by sketch rendering.
3. Discoverability:
   - in-UI hint for rotate/peek key behavior in 2D.
4. Regression tests:
   - zoom value updates live and correctly.
   - home action available and functional in 2D.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py test/test_sketch_editor_w26_signals.py
```

Manual acceptance checklist for user:
1. Enter sketch mode and trigger Home (button + shortcut).
2. Confirm camera resets and origin is recoverable quickly.
3. Zoom in/out and verify badge tracks real zoom.
4. Confirm hint text for rotate/peek is visible and correct.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBG_w35_2d_navigation_origin_home.md`

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

