You are AI-LargeBE on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`
- `handoffs/HO_20260219_0042_Slot_Direct_Edit_Constraints.md`

Objective:
- Make 3-point arc creation and edit mathematically correct and user-predictable.
- Ensure arc fixes do not regress slot behavior.

Hard rules:
1. CAD-kernel-only math; no visual-only correction.
2. 3-point arc must pass through all 3 points by construction.
3. Do not break slot arc logic.
4. No test skip/xfail weakening.
5. Do not merge before user acceptance.

Scope (allowed):
- `gui/sketch_handlers.py`
- `gui/sketch_editor.py`
- `sketcher/geometry.py`
- `sketcher/sketch.py`
- `test/test_shape_matrix_w34.py`
- `test/harness/**`

No-go:
- `modeling/**`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`

Work packages:
1. 3-point arc solver:
   - Robust orientation/side selection.
   - Degenerate and near-collinear handling.
2. Edit consistency:
   - center/radius/start/end angle drags preserve geometric validity.
3. Slot compatibility:
   - verify slot creation/edit remains stable with updated arc internals.
4. Tests:
   - explicit geometric assertions for pass-through points.
   - slot non-regression tests.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_handlers.py gui/sketch_editor.py sketcher/geometry.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py -k arc
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py -k slot
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py -k arc
```

Manual acceptance checklist for user:
1. Create multiple 3-point arcs in different quadrants.
2. Verify arc visually passes exactly through all three clicked points.
3. Edit arc handles and confirm no inversion glitch.
4. Create and edit slot afterward to confirm no regressions.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBE_w35_arc_three_point_correctness.md`

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

