You are AI-LargeBA on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HANDOFF_20260218_ai_2d_gap_closure_kernel_hardline.md`
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`
- `handoffs/HO_20260219_0039_Ellipse_Constraint_Springback_Fix.md`
- `handoffs/HO_20260219_0042_Slot_Direct_Edit_Constraints.md`

Objective:
- Define and enforce one consistent Direct-Edit contract in 2D sketch for:
  - `line`, `circle`, `rectangle`, `arc`, `ellipse`, `polygon`, `spline`
- Result must be production behavior, not test-only behavior.

Hard rules:
1. CAD-kernel-only logic. No UI-only fake geometry, no "draw-only" workaround, no polyline replacement of native entities for logic.
2. Do not skip, xfail, mute, or weaken tests to get green.
3. Do not add fallback hacks that bypass solver failure silently.
4. Do not merge. Stop after handoff and wait for user acceptance.
5. Every claim requires a repro command and observed result.

Scope (allowed):
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `sketcher/geometry.py`
- `sketcher/sketch.py`
- `test/harness/**`
- `test/test_sketch_product_leaps_w32.py`
- `test/test_shape_matrix_w34.py`

No-go:
- `modeling/**` (except imports/constants if absolutely required, document why)
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- Any CI workflow files

Work packages:
1. Direct-edit state machine normalization:
   - Formalize body-drag vs handle-drag behavior per shape.
   - Guarantee "path drag moves whole entity" for ellipse/polygon/spline.
2. Handle semantics parity:
   - Circle remains reference behavior.
   - Rectangle edge drag updates dimensions without destroying topology.
   - Arc handle logic consistent with center/radius/angle.
3. Constraint-safe post-drag reconciliation:
   - Update only edited-entity constraints.
   - No cross-entity drift from local edits.
4. Guard rails:
   - Headless/harness-safe attributes (`getattr` safety where needed).
   - No exceptions on finish/cancel paths.
5. Regression tests:
   - Add/extend tests per shape for create/select/body-drag/handle-drag.
   - Add failure tests for previous regressions.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py sketcher/geometry.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py test/test_sketch_product_leaps_w32.py
```

Manual acceptance checklist (must be included in handoff for user):
1. Draw each shape and drag on body path -> whole shape moves.
2. Drag each official handle -> expected parameter update only.
3. Undo/Redo after each drag -> stable and identical state.
4. Save/reopen sketch -> same direct-edit behavior.
5. No spontaneous geometry deformation from adding next entity.

Required handoff file:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBA_w35_2d_direct_edit_contract.md`

Required handoff structure:
1. Problem and root causes
2. Exact code changes (file + function + why)
3. Validation commands with output summary
4. Manual acceptance script for user (step-by-step)
5. Risks, open gaps, and next actions

Stop condition:
- After writing handoff, explicitly state:
  - "READY FOR USER ACCEPTANCE - DO NOT MERGE"

