# PROMPT_20260218_ai_largeU_w32_sketch_product_leaps_rerun_hardfail

Du bist AI-LARGE-U-RERUN auf Branch `feature/v1-ux-aiB`.

## Kontext (wichtig)
Der vorige Lauf zu W32 wurde abgelehnt.
Gruende:
1. Prompt-Verstoß: neue `pytest.skip(...)` eingeführt (No-Skip-Regel gebrochen).
2. Testqualität zu schwach (zu viele Mock-only-Checks ohne reale Interaktion).
3. Handoff-Reporting war widersprüchlich ("17/17 passed" trotz skips).

## Mission
Liefere W32 Sketch Product Leaps diesmal belastbar und prompt-konform.

## Harte Regeln (NON-NEGOTIABLE)
1. Keine neuen `skip`/`xfail`/"fallback asserts".
2. Keine bestehenden strikten Assertions verwässern.
3. Keine `.bak`/`temp_*` Dateien erzeugen.
4. Handoff muss exakte Testzahlen korrekt berichten (inkl. skipped=0 Pflicht in neuen W32-Tests).

## Scope
Erlaubt:
- `gui/sketch_editor.py`
- `gui/sketch_renderer.py`
- `gui/sketch_handlers.py`
- `test/test_sketch_product_leaps_w32.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/test_line_direct_manipulation_w30.py`

Verboten:
- `modeling/**`
- `gui/main_window.py`
- `gui/viewport_pyvista.py`

## Pflichtaufgaben

### A) Skip-Bereinigung + echte Tests (P0)
- Entferne alle in W32 neu eingeführten `pytest.skip(...)` in `test/test_sketch_product_leaps_w32.py`.
- Ersetze Mock-only-Fälle durch echte, reproduzierbare Interaction-Tests (QtBot/QTest/real editor state), mindestens:
  1. Arc center drag
  2. Arc radius drag
  3. Ellipse standard-vs-active handles
  4. Polygon vertex drag (ohne skip)
  5. Undo-granularity für einen Drag-Loop

### B) Produktverhalten absichern (P0)
- Falls nötig in `sketch_editor.py` nachziehen, damit die obigen Tests ohne Skip bestehen.
- ESC/Rechtsklick-Parität in direktem Editiermodus nicht regressiv.

### C) Performance-/Render-Nebenwirkungen (P1)
- Sicherstellen, dass Direct-Edit keine offensichtliche Update-Flut erzeugt.
- Mindestens 1 Test für update/debounce-Verhalten im Drag-Kontext.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_renderer.py gui/sketch_handlers.py
conda run -n cad_env python -m pytest -q test/test_sketch_product_leaps_w32.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py test/test_line_direct_manipulation_w30.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

## Akzeptanzkriterien
- `test/test_sketch_product_leaps_w32.py` mit **0 skipped**.
- Keine neuen Skip/Xfail in den geänderten Testdateien.
- Sichtbarer Code-Impact im Sketch-Verhalten, nicht nur Testtext.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeU_w32_sketch_product_leaps_rerun_hardfail.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Dateien)
4. Validation (Commands + exakte Zahlen)
5. Rest-Risiken

Wichtig: Wenn etwas nicht erreicht ist, Status = PARTIAL (nicht COMPLETE).
