You are AI-LargeBF on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HANDOFF_20260218_ai_modify_interaction_blocker_fix.md`
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`

Objective:
- Restore and harden Modify toolchain parity (move/copy/rotate/mirror/scale) to old stable behavior.

Hard rules:
1. CAD-kernel-only transformation logic.
2. Preserve constraints and references deterministically where defined.
3. No "input-only fallback" after one drag attempt.
4. No weakening tests. No merge before user acceptance.

Scope (allowed):
- `gui/sketch_handlers.py`
- `gui/sketch_editor.py`
- `sketcher/sketch.py`
- `test/**` for modify workflows

No-go:
- `modeling/**`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`

Required bug closure:
1. Resolve handler signature mismatch in copy flow.
2. Resolve missing `Constraint` import/reference errors.
3. Keep transformation behavior stable across repeated operations.

Work packages:
1. Modify command contract:
   - selection acquisition, operation preview, confirm/cancel.
2. Transformation correctness:
   - move, copy, rotate, mirror, scale with constraints policy.
3. Undo/redo:
   - operation boundaries are deterministic.
4. Regression tests:
   - robust flows for each modify operation.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_handlers.py gui/sketch_editor.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/test_feature_edit_robustness.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py
```

Manual acceptance checklist for user:
1. Select rectangle+lines -> move by drag repeatedly.
2. Copy selected geometry -> no handler exception.
3. Rotate/mirror/scale with undo/redo cycles.
4. Verify constraints are not randomly dropped.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBF_w35_modify_toolchain_parity.md`

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

