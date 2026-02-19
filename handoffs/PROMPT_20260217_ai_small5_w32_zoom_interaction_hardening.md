# PROMPT_20260217_ai_small5_w32_zoom_interaction_hardening

Du bist AI-SMALL-5 (UI Test Hardening) auf Branch `feature/v1-ux-aiB`.

## Ziel
W32 Zoom-Badge ist funktional, aber Testabdeckung für echte UI-Interaktion ist noch zu schwach.
Baue robuste, echte Interaction-Tests für das Context-Menü und liefere eine timeout-feste Validierung.

## Scope (klein, strikt)
- Erlaubte Dateien:
  - `test/test_status_bar_zoom_w32.py`
  - optional kleine Testhilfen in `test/harness/**` (nur falls wirklich nötig)
  - optional minimal-invasive Testbarkeitshooks in `gui/widgets/status_bar.py`
- Nicht ändern:
  - `modeling/**`
  - `gui/sketch_editor.py`
  - `gui/main_window.py`

## Konkrete Aufgaben

### 1) Echte UI-Interaktion testen (P0)
Ergänze `test/test_status_bar_zoom_w32.py` um echte Interaction-Cases:
- Klick auf Zoom-Badge in 2D öffnet Preset-Menü.
- Auswahl `50%`, `100%`, `200%` emittiert korrekt `zoom_preset_requested`.
- Auswahl `Fit` emittiert korrekt `zoom_fit_requested`.
- In 3D-Modus öffnet Klick kein funktionales Preset-Menü bzw. emittiert keine Zoom-Signale.

Hinweis:
- Falls `QMenu.exec()` Tests blockiert, erlaube minimalen Test-Hook in `status_bar.py` (z. B. interne Builder-Methode oder ersetzbarer Menu-Invoker), aber keine UX-Änderung.

### 2) Timeout-feste Testausführung dokumentieren (P0)
Führe Tests so aus, dass kein 5min-Hänger entsteht.
Nutze split runs:
- erst W32-Tests
- dann nur 1-2 representative UI-Smokes aus den langen Suites

### 3) Qualität
- Keine Skips hinzufügen.
- Keine bestehenden Assertions abschwächen.
- Keine Fake-Tests (nur Attribut-Checks reichen nicht).

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/widgets/status_bar.py test/test_status_bar_zoom_w32.py
conda run -n cad_env python -m pytest -q test/test_status_bar_zoom_w32.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

## Rückgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_small5_w32_zoom_interaction_hardening.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation (exakte Commands + Ergebnis)
5. Rest-Risiken
