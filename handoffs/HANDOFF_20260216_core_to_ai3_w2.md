# HANDOFF_20260216_core_to_ai3_w2

**Date:** 2026-02-15
**From:** Codex (Core/KERNEL)
**To:** AI-3 (QA/Release Cell)
**ID:** core_to_ai3_w2
**Branch:** `feature/v1-ux-aiB`

## 1. Problem
AI-3 W1 report is now partially outdated. Core rollback-metrics blockers (fillet/hole) are fixed in Core, but W1 docs still mark them as open.
Current release risk shifted to:
- UI gate remains blocked by `NameError: tr not defined` in `gui/widgets/status_bar.py:126`
- QA docs and gate definitions need a rebaseline to current facts
- Workspace hygiene is still weak (debug/temp files still present)

## 2. API/Behavior Contract
No new API change request for AI-3 in this wave.
AI-3 scope remains QA/release infrastructure and documentation only:
- allowed: `test/**`, `roadmap_ctp/**`, `scripts/**` (gate tooling)
- blocked: `modeling/**`, `gui/main_window.py`, `gui/viewport_pyvista.py`

## 3. Impact
Core baseline already validated by Codex:
- Core-gate pack: `217 passed, 2 skipped`
- Regression pack (4 suites): `98 passed, 1 skipped`
UI baseline currently:
- `11 errors, 3 skipped` (blocked at MainWindow setup because `tr` is not defined)

AI-3 task in W2 is to update release QA artifacts to this new baseline and harden gate execution hygiene.

## 4. Validation (executed by Codex)
```powershell
conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py
# Result: 98 passed, 1 skipped

conda run -n cad_env python -m pytest -q test/test_feature_error_status.py test/test_tnp_v4_feature_refs.py test/test_trust_gate_core_workflow.py test/test_cad_workflow_trust.py test/test_brepopengun_offset_api.py test/test_feature_flags.py test/test_tnp_stability.py test/test_feature_edit_robustness.py test/test_project_roundtrip_persistence.py
# Result: 217 passed, 2 skipped

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py
# Result: 11 errors, 3 skipped
# Root blocker: NameError: name 'tr' is not defined in gui/widgets/status_bar.py:126
```

## 5. Breaking Changes / Residual Risks
- No breaking change in Core API.
- Primary release blocker is still UI gate setup failure.
- Existing W1 QA docs contain stale blocker statements and can mislead prioritization if not corrected.

## W2 Tasks for AI-3
1. Rebaseline QA docs to current truth (P0)
- Update:
  - `roadmap_ctp/FLAKY_BURN_DOWN_20260215.md`
  - `roadmap_ctp/REGRESSION_PACK_STATUS_20260215.md`
  - `roadmap_ctp/GATE_DEFINITIONS_20260215.md`
- Remove stale Core rollback blocker entries.
- Keep UI blocker entries with exact repro and stack location.

2. Gate tooling implementation (P0)
- Create runnable scripts:
  - `scripts/gate_core.ps1`
  - `scripts/gate_ui.ps1`
  - optional aggregator `scripts/gate_all.ps1`
- Output format must include: duration, pass/fail/skip counts, exit code, failing tests.

3. Workspace hygiene gate (P1)
- Implement `scripts/hygiene_check.ps1`:
  - fail on untracked files matching debug/temp patterns:
    - `test/debug_*.py`
    - `test_output*.txt`
    - `*.tmp`
- Document usage in `roadmap_ctp/WORKSPACE_HYGIENE_GATE_20260215.md`.

4. Error-code mapping QA refresh (P1)
- Re-run mapping report and keep only evidence-backed gaps.
- Confirm that core code mappings include:
  - `tnp_ref_missing`, `tnp_ref_mismatch`, `tnp_ref_drift`, `rebuild_finalize_failed`, `ocp_api_unavailable`

## Required return format
Create: `handoffs/HANDOFF_20260216_ai3_w2.md`
Sections:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (exact commands + result)
5. Breaking Changes / Residual Risks
Plus: next 3 prioritized follow-up tasks.
