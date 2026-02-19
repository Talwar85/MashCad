You are AI-LargeBI on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `docs/process/stabilization_protocol.md`
- `test/harness/**`
- latest 2D sketch handoffs in `handoffs/`

Objective:
- Build a fast visual acceptance harness for 2D sketch so user acceptance can happen before long full gates.

Hard rules:
1. Harness must verify real behavior, not mocks only.
2. No replacing product code with test doubles in critical paths.
3. No test skip/xfail manipulations.
4. No merge before user acceptance.

Scope (allowed):
- `test/harness/**`
- `test/test_*` related to sketch interactions
- `scripts/**` (new quick-run acceptance scripts allowed)
- `docs/process/**` acceptance documentation

No-go:
- Core geometry/solver/modeling logic changes unless strictly necessary
- CI workflow edits (unless requested explicitly)

Work packages:
1. Quick acceptance runner:
   - one command executes critical 2D interaction smoke scenarios.
   - clear pass/fail report per shape.
2. Visual checkpoints:
   - standardized list of user-visible checkpoints with expected outcome.
3. Artifact output:
   - produce concise result file under `roadmap_ctp/` or `test_output/`.
4. Failure triage tags:
   - classify failures into interaction, solver, persistence, rendering.
5. Documentation:
   - user-facing "what to test in 10 minutes" script.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile test/harness
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py test/harness/test_interaction_direct_manipulation_w17.py
```

Manual acceptance checklist for user:
1. Run quick harness command.
2. Execute listed in-app manual checks (<=10 min).
3. Confirm report and visual behavior align.

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBI_w35_visual_acceptance_harness.md`

Required in handoff:
- exact run command for user
- expected output format
- known blind spots

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

