You are AI-LargeBD on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`
- `handoffs/HANDOFF_20260218_ai_2d_gap_closure_kernel_hardline.md`

Objective:
- Close polygon behavior gaps to professional CAD usability:
  - translate whole polygon, resize from intended handles, block illegal distortive drags.

Hard rules:
1. CAD-kernel-only geometry behavior.
2. No per-segment distortion path if it violates polygon shape contract.
3. No hidden solver overrides to force pass.
4. No test weakening. No merge without user acceptance.

Scope (allowed):
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `sketcher/sketch.py`
- `test/harness/**`
- `test/test_shape_matrix_w34.py`

No-go:
- `modeling/**`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`

Work packages:
1. Polygon interaction contract:
   - Body/path drag = full polygon translation.
   - Size handle drag = scale/resizing behavior.
   - Vertex drag policy explicit: either disabled for regular polygon mode, or transformed with rule.
2. Constraint contract:
   - Ensure radius/regularity constraints are preserved during direct edit.
3. Prevent topology break:
   - No accidental conversion to broken polyline state.
4. Regression tests:
   - create/select/translate/resize/undo/redo/persist.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py -k polygon
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py -k polygon
```

Manual acceptance checklist for user:
1. Draw polygon, drag on path -> whole polygon moves.
2. Drag size handle -> uniform expected resize.
3. Attempt illegal edge drag -> blocked or mapped to valid behavior.
4. Save/reopen and repeat.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBD_w35_polygon_behavior_closure.md`

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

