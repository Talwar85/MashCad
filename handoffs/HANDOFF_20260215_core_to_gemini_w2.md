# HANDOFF_20260215_core_to_gemini_w2

**Date:** 2026-02-15  
**From:** Codex (Core/KERNEL)  
**To:** Gemini (UX/WORKFLOW)  
**ID:** core_to_gemini_w2

## Problem
`HANDOFF_20260215_ux_abort.md` ist integriert. Der Abort-Pfad ist umgesetzt, aber die naechste Welle braucht saubere UX-Regressionen und Discoverability-Fortschritt, damit die Bedienung fuer Einsteiger/Power-User konsistent bleibt.

## Aufgaben (priorisiert)
1. **P0 - SU-006 erweitern**
- `test/test_ui_abort_logic.py` um Randfaelle erweitern:
  - Rechtsklick ins Leere bei aktivem Tool
  - Escape bei kombiniertem Zustand (Drag + Panel + Selection)
  - Wiederholte Escape-Sequenz bis Idle

2. **P0 - SU-004 Harness verhaerten**
- `test/harness/test_interaction_consistency.py` auf echte Assertions heben:
  - Circle move/resize
  - Rectangle edge-drag
  - Line drag consistency
- Keine Print-Smoke-Tests ohne Verifikation.

3. **P1 - 2D Discoverability**
- Sichtbare, kontextsensitive Hinweise in 2D fuer:
  - Rotation
  - Peek (`Leertaste`)

4. **P1 - QA-003 / QA-004**
- Flaky-/Skip-Inventar mit Ursache, Owner, ETA und Abbau-Prioritaet.

## Validation (Pflicht)
```powershell
conda run -n cad_env python -m py_compile gui/main_window.py gui/viewport_pyvista.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_sketch_* test/test_*ui*
```

## Handoff-Format fuer Rueckgabe
Datei:
- `roadmap_ctp/handoffs/HANDOFF_YYYYMMDD_ux_<id>.md`

Pflichtinhalt:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (Commands + Resultat)
5. Breaking Changes / Rest-Risiken
