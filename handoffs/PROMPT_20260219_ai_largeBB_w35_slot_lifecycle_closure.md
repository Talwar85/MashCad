You are AI-LargeBB on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `handoffs/HO_20260219_0042_Slot_Direct_Edit_Constraints.md`
- `handoffs/HO_20260219_0047_Slot_Save_Load_Extrude.md`
- `handoffs/HANDOFF_20260218_ai_draw_shapes_full_repair.md`

Objective:
- Make slot behavior production-stable across full lifecycle:
  - create, select, direct-edit, solve, save/load/reopen, profile detect, extrude, undo/redo.

Hard rules:
1. CAD-kernel-only logic. Slot remains native structured geometry (center line + side lines + arcs + constraints).
2. No hidden auto-repair that mutates unrelated entities.
3. No test manipulation (no skip/xfail weakening).
4. Do not merge. Wait for user acceptance.

Scope (allowed):
- `sketcher/sketch.py`
- `gui/sketch_editor.py`
- `modeling/__init__.py` (only slot profile/extrude path)
- `test/test_shape_matrix_w34.py`
- `test/test_project_roundtrip_persistence.py`
- `test/test_ellipse_extrude_w34.py` (if slot matrix extension added here)

No-go:
- `gui/main_window.py`
- `gui/viewport_pyvista.py`
- CI files

Work packages:
1. Slot identity and structure:
   - Ensure robust slot component linkage after serialization and rebuild.
   - Verify marker persistence and reconstruction correctness.
2. Direct-edit consistency:
   - Center drag, length-start, length-end, radius drag all deterministic.
   - Radius constraints update only for the active slot.
3. Persistence closure:
   - Save/load/reopen preserves slot behavior, not only geometry.
4. Profile and extrude closure:
   - Slot recognized as closed profile reliably.
   - Extrude path stable and repeatable.
5. Undo/redo closure:
   - No broken references after repeated slot edits and transactions.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py sketcher/sketch.py modeling/__init__.py
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py -k slot
conda run -n cad_env python -m pytest -q test/test_project_roundtrip_persistence.py
conda run -n cad_env python -m pytest -q test/test_ocp_primitives.py test/test_tnp_stability.py
```

Manual acceptance checklist for user (must be in handoff):
1. Create slot -> edit length/radius -> no spring-back.
2. Reopen sketch -> edit slot again -> same behavior.
3. Extrude slot -> expected body without corruption.
4. Undo/redo through edits and extrude -> no broken slot.

Required handoff file:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBB_w35_slot_lifecycle_closure.md`

Required handoff structure:
1. Root causes
2. Exact changes with file/function list
3. Validation results
4. User acceptance script
5. Remaining risks

Stop condition:
- Print "READY FOR USER ACCEPTANCE - DO NOT MERGE".

