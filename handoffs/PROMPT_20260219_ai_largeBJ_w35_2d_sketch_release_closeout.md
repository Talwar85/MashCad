You are AI-LargeBJ on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- All W35 prompt/handoff files for BA..BI in `handoffs/`
- `docs/process/stabilization_protocol.md`

Objective:
- Perform final 2D sketch release closeout after BA..BI work is integrated.
- Deliver a release candidate readiness package for user sign-off.

Hard rules:
1. CAD-kernel-only behavior; no temporary hacks.
2. Do not close issues without evidence.
3. No test manipulation (skip/xfail or timeout dodge).
4. Do not merge before explicit user acceptance.

Scope:
- Integration-level stabilization only.
- Bug burn-down across 2D sketch create/edit/modify/persist/extrude flow.
- Release checklist and evidence package.

No-go:
- New unrelated features.
- Large architecture changes outside 2D sketch stabilization.

Work packages:
1. Cross-epic integration verification:
   - direct edit, modify tools, slot, spline, polygon, arc, navigation, persistence.
2. Release risk matrix:
   - severity, reproducibility, workaround, owner.
3. Must-fix final sweep:
   - close remaining P0/P1 blockers only.
4. Evidence bundle:
   - test evidence + manual acceptance script + known limitations.
5. RC recommendation:
   - GO / NO-GO with rationale.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_project_roundtrip_persistence.py test/test_sketch_solver_status.py
```

Manual acceptance checklist for user:
1. Execute final manual script (all shapes + modify + persistence + extrude).
2. Confirm no blocking behavior regressions remain.
3. Confirm GO/NO-GO decision.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBJ_w35_2d_sketch_release_closeout.md`

Required handoff sections:
1. Readiness summary
2. Remaining blockers
3. Validation evidence
4. User acceptance script
5. GO/NO-GO recommendation

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

