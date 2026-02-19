Du bist AI-LARGE-Y-STAB (Viewport Interaction Crash Stabilization) auf Branch `feature/v1-ux-aiB`.

## Kontext
W33 hat neue Viewport-Interaction-Tests geliefert, aber die Suite ist nicht release-faehig:
- Reproduzierbarer Crash: `Windows fatal exception: access violation`
- Trigger-Test: `test/test_viewport_interaction_w33.py::TestY2AbortParity::test_escape_clears_point_to_point_mode`
- Kritische Zeile: `QTest.keyClick(viewport, Qt.Key_Escape)`

Ziel: **Crash-freie, belastbare W33-Viewport-Suite** bei unveraenderter Produktsemantik.

## Pflicht-Inputs (vor Start lesen)
- `handoffs/HANDOFF_20260217_ai_largeY_w33_viewport_interaction_stability_ultrapack.md`
- `test/test_viewport_interaction_w33.py`
- `gui/viewport/selection_mixin.py`
- `gui/main_window.py`
- ggf. relevante Dateien unter `gui/viewport/**`

## Scope
Erlaubte Dateien:
- `test/test_viewport_interaction_w33.py`
- `test/test_main_window_w26_integration.py` (nur falls absolut noetig)
- `gui/main_window.py`
- `gui/viewport/**`

No-Go:
- `modeling/**`
- `gui/sketch_editor.py`
- `gui/sketch_renderer.py`
- `gui/widgets/status_bar.py`

## Harte Regeln (nicht verhandelbar)
1. Keine neuen `skip`, `xfail`, `flaky`, Retry-Decorator.
2. Kein "works on my machine"-Handoff.
3. Kein Abschwaechen von Assertions ohne gleichwertige semantische Absicherung.
4. Kein Umgehen des Crashes durch Deaktivieren von Tests.
5. Keine `.bak`, `temp_*`, `debug_*` Artefakte.

## Aufgabenpaket

### A) Crash Root Cause sauber isolieren (P0)
- Reproduziere den Crash mit exakt:
  - `conda run -n cad_env python -m pytest -q test/test_viewport_interaction_w33.py::TestY2AbortParity::test_escape_clears_point_to_point_mode`
- Identifiziere den technischen Grund (Event-Target, Focus, Qt/OpenGL-Lifecycle, Widget-State).
- Dokumentiere die Ursache im Handoff mit konkreter Code-Stelle.

### B) Stabiler Event-Pfad ohne Semantikverlust (P0)
- Stabilisiere den Escape-Abbruchpfad fuer Point-to-Point-Mode.
- Wenn `QTest.keyClick(viewport, ...)` auf der Runtime instabil ist, migriere auf einen robusten, semantisch gleichwertigen Event-Pfad (z. B. Event an das tatsaechliche Input-Owner-Widget/Fokusroute), ohne Testabsenkung.
- Produktverhalten muss gleich bleiben: Escape beendet Point-to-Point konsistent.

### C) W33 Abort-Parity absichern (P0)
- Sicherstellen, dass ESC und Right-Click weiterhin konsistenten Endzustand liefern.
- Keine Regression bei:
  - `is_dragging`
  - `point_to_point_mode`
  - `edge_select_mode`
  - Preview-Cleanup

### D) Test-Qualitaet und Suite-Haerte (P1)
- Behalte bzw. erhoehe Aussagekraft von `test/test_viewport_interaction_w33.py`.
- Mocking nur wo technisch zwingend, keine self-fulfilling Tests.

## Pflicht-Validierung
Fuehre aus und liefere exakte Ergebnisse:

```powershell
conda run -n cad_env python -m py_compile gui/main_window.py gui/viewport/selection_mixin.py test/test_viewport_interaction_w33.py
conda run -n cad_env python -m pytest -q test/test_viewport_interaction_w33.py::TestY2AbortParity::test_escape_clears_point_to_point_mode
conda run -n cad_env python -m pytest -q test/test_viewport_interaction_w33.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

## Akzeptanzkriterien
- Kein Access-Violation-Crash im Einzeltest und in der gesamten W33-Suite.
- Keine neuen Skips/Xfails.
- Abort-Parity bleibt fachlich korrekt.
- Regression-Suiten bleiben gruen.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeY_w33_crash_stabilization.md`

Struktur:
1. Problem
2. Root Cause
3. API/Behavior Contract
4. Impact
5. Validation (Commands + exakte Ergebnisse)
6. Rest-Risiken
7. Naechste 3 priorisierte Folgeaufgaben
