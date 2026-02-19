You are AI-LargeBC on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`
- `handoffs/HANDOFF_20260218_ai_2d_gap_closure_kernel_hardline.md`

Objective:
- Make spline behavior fully usable and non-destructive:
  - finish/cancel behavior, selection behavior, direct-edit behavior, persistence, and profile compatibility.

Hard rules:
1. CAD-kernel-only: keep spline as native spline entity, no segment-based fake substitute.
2. Body drag from spline path must move full spline; point drag edits control points only.
3. No test skipping / no weakening assertions.
4. Do not merge before user acceptance.

Scope (allowed):
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `sketcher/sketch.py`
- `sketcher/geometry.py` (if spline primitives need extension)
- `test/harness/**`
- `test/test_shape_matrix_w34.py`

No-go:
- `modeling/**` (except tiny compatibility fixes with justification)
- `gui/main_window.py`
- `gui/viewport_pyvista.py`

Work packages:
1. Spline completion semantics:
   - Right-click/ESC in spline mode must finalize or cancel predictably.
   - No accidental full discard when user intended finalize.
2. Selection semantics:
   - Prevent illegal "segment drag" that breaks spline.
   - Distinguish path-drag (translate full spline) vs point-drag (edit control point).
3. Constraint and solve stability:
   - No cross-entity distortion after spline edits.
4. Persistence:
   - Save/load/reopen keeps spline editable with same semantics.
5. Regression tests:
   - Add explicit tests for each behavior above.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py sketcher/sketch.py sketcher/geometry.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py
```

Manual acceptance checklist for user:
1. Create spline with multiple points, finish by right-click and by ESC path.
2. Drag spline path -> full spline translates.
3. Drag one control point -> local shape change only.
4. Save/reopen -> repeat 2 and 3.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBC_w35_spline_integrity_megapack.md`

Required sections:
1. Problem
2. Kernel-level fixes
3. Validation evidence
4. User acceptance steps
5. Risks/open items

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

