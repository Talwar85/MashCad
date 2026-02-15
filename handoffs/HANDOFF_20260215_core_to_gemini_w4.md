# HANDOFF_20260215_core_to_gemini_w4

**Date:** 2026-02-15  
**From:** Codex (Core/KERNEL Validation)  
**To:** Gemini (UX/WORKFLOW)  
**ID:** core_to_gemini_w4

## Problem
UI-Änderungen für Abort/Right-Click-Flow sind im aktuellen Stand nicht konsistent wirksam. Die neuen Tests laufen nicht grün.

## Findings (validiert)
1. **Regression:** `test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_cancels_drag` schlägt fehl.  
   Erwartet: `viewport.is_dragging == False` nach Right-Click-Press.  
   Ist: `viewport.is_dragging == True`.

2. **Regression:** `test/harness/test_interaction_consistency.py::TestInteractionConsistency::test_click_selects_nothing_in_empty_space` schlägt fehl.  
   Erwartet: Selection wird bei Leerraum-Klick gelöscht.  
   Ist: `selected_faces` bleibt `['face_1']`.

3. **Root Cause (Code-Struktur):** `gui/viewport_pyvista.py` enthält **zwei** `eventFilter()`-Definitionen:
   - `gui/viewport_pyvista.py:532`
   - `gui/viewport_pyvista.py:2319`

   Die neu eingefügte Right-Click-Logik liegt im frühen Block (`:532`), wird aber effektiv vom späteren `eventFilter` überschrieben. Dadurch greift die neue Abort-Logik in der Laufzeit nicht zuverlässig.

4. **Zusatzproblem:** Initialisierung von `_right_click_start_pos/_right_click_start_time` ist im diff in `_set_face_highlight()` eingerückt statt zentral in `__init__`, was den State-Lebenszyklus unnötig fragil macht.

## Repro Commands
```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py -x
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -x
```

## Expected Fix Scope (Gemini)
1. `eventFilter` konsolidieren: genau **eine** gültige Implementierung behalten.
2. Right-Click Abort/Background-Clear in der tatsächlich aktiven `eventFilter`-Implementierung integrieren.
3. `_right_click_start_pos` und `_right_click_start_time` in `__init__` initialisieren.
4. Rechtsklick-Press auf Drag muss deterministisch `cancel_drag()` triggern.
5. Rechtsklick-Klick im Leerraum muss deterministisch `clear_selection()` triggern.
6. Keine Regressionen für bestehende 3D-Interaktionen (Kontextmenü, Orbit/Pan, Extrude-Rechtsklick-Abbruch).

## Acceptance Criteria
- `test/test_ui_abort_logic.py` komplett grün.
- `test/harness/test_interaction_consistency.py` komplett grün (abzgl. explizit `@pytest.mark.skip` markierter CI-unstable Fälle).
- Kein zweites `def eventFilter(...)` mehr in `gui/viewport_pyvista.py`.

## Validation Status (Core)
- Core-Suite ist grün:
  - `198 passed, 2 skipped` auf:
    - `test/test_feature_error_status.py`
    - `test/test_tnp_v4_feature_refs.py`
    - `test/test_trust_gate_core_workflow.py`
    - `test/test_cad_workflow_trust.py`
    - `test/test_brepopengun_offset_api.py`
    - `test/test_feature_flags.py`
    - `test/test_tnp_stability.py`
