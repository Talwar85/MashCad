# Refactor Regression Audit - Cleaned Current-State Version

Date: 2026-03-01
Baseline: `b014fc8`
Verified against: current `feature/tnp5` working tree after recent regression fixes

## Scope

This document replaces the earlier broad audit that mixed historical findings, stale claims, and current state.

This version keeps only claims that were checked against the current code.

## Summary

The earlier audit was not reliable as an authoritative status report.

Reasons:
- it marked some hypotheses as `confirmed regressions`
- it missed multiple fixes already present on the branch
- several key claims were directly false against current code

## Already Fixed On Current Branch

These refactor regressions were real, but are no longer open on the current branch:

1. Feature edit dispatch for PushPull / Loft / Sweep
2. TNP body-pick wiring in the feature dialogs
3. TNP stats panel API drift (`set_body_stats` vs `update_stats` / `refresh`)
4. Feature-edit face/edge highlighting after fillet/chamfer
5. Hole face picking reliability and full-face hover/highlight
6. Hole continuous on-face preview after face selection
7. Texture live-preview cancel cleanup
8. PickingMixin initialization / `_selection_contexts`
9. Locale corruption in numeric feature edit dialogs (`2.0` -> `20` / scientific notation)
10. Push/Pull rebuild direction / no-op success handling

## False Or Stale Claims In The Old Audit

These claims were checked and should not be treated as open issues:

1. `_update_detector()` is a TODO/pass stub
   - False
   - Current implementation exists in `gui/feature_operations.py`

2. `keyReleaseEvent` / Peek-3D release handling was removed
   - False as stated
   - Current Space-release handling exists in `gui/event_handlers.py`

3. `PickingMixin` init is missing
   - False for current branch
   - `PickingMixin.__init__(self)` is explicitly called in `gui/viewport_pyvista.py`

4. `_extract_face_as_polygon()` removal is a confirmed current Push/Pull regression
   - Not proven
   - Current Push/Pull flow uses `face_shape_id`, `face_selector`, and TNP selection context

5. large parts of the report still describe pre-fix branch state rather than current HEAD
   - stale

## Confirmed Issues Fixed During This Cleanup

These were validated as real and fixed now:

1. Missing viewport single-body removal API
   - Problem: `gui/commands/feature_commands.py` called `viewport.remove_body(body_id)`
   - Current fix:
     - `gui/viewport/body_mixin.py` now provides `remove_body()` as compatibility alias
     - `gui/commands/feature_commands.py` now falls back to `clear_bodies(only_body_id=...)` and no longer silently swallows the failure

2. Missing CAD feature highlight implementation
   - Problem: `gui/feature_operations.py` called `viewport.highlight_feature(body, feature)` but the real CAD viewport had no implementation, only STL feature analysis had one
   - Current fix:
     - `gui/viewport_pyvista.py` now implements `clear_feature_highlight()` and `highlight_feature(body, feature)`
     - supports body highlight fallback
     - prefers edge ShapeIDs / edge indices for edge-based features
     - falls back to face ShapeID / selector / index for face-based features

## Remaining Plausible Issues Worth Auditing Next

These were not proven by the old audit, but remain plausible engineering targets:

1. silent exception handling in `gui/commands/feature_commands.py`
   - still present in multiple helpers
   - should be reduced further over time

2. SelectionContext observability in Push/Pull creation
   - currently logs only on debug level when context capture fails
   - likely acceptable for now, but weak for diagnostics

3. duplicated plane-axis logic across modules
   - not a confirmed bug by itself
   - still a maintenance risk

## Tests Added / Revalidated In This Cleanup

1. `test_viewport_remove_body_alias_routes_to_clear_bodies`
2. `test_remove_body_from_viewport_falls_back_to_clear_bodies`
3. `test_viewport_highlight_feature_prefers_tnp_edges_and_marks_body`
4. `test_viewport_highlight_feature_falls_back_to_face_reference_lists`

Related targeted verification also remains green for the already-fixed UI/feature regression suites.

## Bottom Line

Use this file as the current baseline, not the older audit narrative.

The old audit was useful as a lead generator, but not as a trusted truth source.
The two strongest still-open engineering claims from that audit were:
- missing viewport single-body removal
- missing CAD feature highlight

Both are now fixed in the current working tree.
