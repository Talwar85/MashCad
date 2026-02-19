You are AI-LargeBH on branch `stabilize/2d-sketch-gap-closure-w34`.

Read first:
- `sketcher/solver.py`
- `sketcher/constraints.py`
- `docs/process/stabilization_protocol.md`
- latest relevant handoffs in `handoffs/` about sketch instability

Objective:
- Reassess whether SciPy least-squares is the right long-term solver approach for 2D sketch constraints.
- Deliver a production-grade recommendation plus concrete implementation steps.

Hard rules:
1. CAD-kernel-first: solver decisions must be based on geometric correctness and deterministic behavior, not "looks okay".
2. No blind replacement of solver. Must keep compatibility and controlled rollout.
3. No disabling constraints to fake stability.
4. No test weakening. No merge before user acceptance.

Scope (allowed):
- `sketcher/solver.py`
- `sketcher/constraints.py`
- `sketcher/sketch.py` (adapter integration only)
- `test/test_sketch_solver_status.py`
- New docs under `docs/solver/`

No-go:
- `gui/**` except minimal hooks for diagnostics display
- `modeling/**`

Work packages:
1. Baseline analysis:
   - classify failure modes (spring-back, infeasible systems, drift, slow convergence).
   - measure current SciPy path on representative scenarios.
2. Solver abstraction:
   - define stable solver interface and result object contract.
   - keep SciPy backend as one implementation.
3. Alternative candidate evaluation:
   - at least one alternative strategy (e.g. damped Gauss-Newton, staged solve, symbolic pre-pass).
   - provide deterministic comparison table.
4. Controlled rollout:
   - feature-flagged backend selection.
   - no behavior break for existing projects.
5. Deliverable doc:
   - `docs/solver/SCIPY_REASSESSMENT_W35.md` with recommendation:
     - keep SciPy, or hybrid, or replacement roadmap.

Mandatory validation commands:
```powershell
conda run -n cad_env python -m py_compile sketcher/solver.py sketcher/constraints.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/test_sketch_solver_status.py
```

Mandatory benchmark evidence (in handoff):
- command lines used
- sample cases
- convergence/failure metrics
- decision rationale

Required handoff:
- `handoffs/HANDOFF_YYYYMMDD_ai_largeBH_w35_solver_scipy_reassessment.md`

Required handoff sections:
1. Current-state diagnosis
2. Interface and implementation changes
3. Benchmark evidence
4. Recommendation and migration plan
5. Risks and rollback strategy

Stop condition:
- "READY FOR USER ACCEPTANCE - DO NOT MERGE".

