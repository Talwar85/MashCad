# PROMPT_20260217_ai_largeN_w30_headless_abort_hardening

Du bist AI-LargeN auf Branch `feature/v1-ux-aiB`.

## Mission
Eliminiere reproduzierbare Headless-/OpenGL-Crashes in UI-Abort/Discoverability-Tests und liefere einen stabilen, timeout-sicheren Testpfad ohne Produktfunktion zu kastrieren.

## Pflicht-Read (zuerst)
- `handoffs/HANDOFF_20260217_ai_largeI_w29_sketch_stabilization_hardgate.md`
- `handoffs/HANDOFF_20260217_ai_largeM_w29_workflow_e2e_closeout.md`
- `handoffs/HANDOFF_20260217_ai_largeK_w29_release_ops_timeoutproof.md`

## Harte Grenzen (No-Go)
1. Keine Edits in:
- `modeling/**`
- `gui/sketch_editor.py`
- `gui/browser.py`

2. Fokus nur auf:
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/ui/**`
- `test/conftest.py` (nur falls absolut nötig)
- `scripts/preflight_ui_bootstrap.ps1` (nur für reproduzierbare Klassifikation)

3. Verboten:
- Blindes Skippen wegen Timeout
- Globales `pytest.skip` ohne präzise Runtime-Guard
- "mock everything" ohne E2E-Wert

## Zielkriterien (Definition of Done)
- `test/test_ui_abort_logic.py` läuft reproduzierbar in Headless ohne Access Violation.
- `test/test_discoverability_hints.py` läuft reproduzierbar in Headless.
- Kein Regression-Leak auf bereits grüne W29-Suiten.
- Dokumentierte Runtime-Grenzen (Soll/Ist) + klare Ursache-Fix-Kette.

## Arbeitspakete
### AP1: Crash-Isolation
- Isoliere die exakte Crash-Stelle (Fixture, MainWindow-Boot, Plotter-Init, Qt Event Loop).
- Liefere 2 minimale Repro-Kommandos und 1 Gegenbeispiel (läuft stabil).

### AP2: Deterministischer Test-Bootstrap
- Implementiere robusten Headless-Bootstrap für die betroffenen Suiten (gezielt, nicht global brachial).
- Nutze existierende W29-Prinzipien: früh gesetzte Env-Variablen, klare Fallback-Pfade, keine Seiteneffekte auf andere Tests.

### AP3: Abort-Parity Regression-Hardening
- Ergänze Tests, die sicherstellen, dass ESC und Right-Click im gleichen Endzustand landen, selbst wenn Viewport/Plotter nicht vollständig initialisiert werden kann.
- Fokus auf Verhalten, nicht auf Renderdetails.

### AP4: Discoverability-Hints Stabilität
- Stabilisiere Hint-Tests bei Toolwechsel, Space-Peek, Rotate-Hint-Cooldown.
- Entferne Flakiness (Timing-/Event-order), ohne User-Verhalten zu verfälschen.

### AP5: Gate-kompatible Laufstrategie
- Optional kleine Ergänzung in `scripts/preflight_ui_bootstrap.ps1`, um diese Crash-Klasse sauber als Infrastruktur-/Environment-Risiko zu klassifizieren, nicht als Produktlogik-Defekt.

## Pflicht-Validierung (ohne Skip wegen Timeout)
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py test/test_projection_trace_workflow_w26.py test/test_sketch_editor_w26_signals.py
```

## Rückgabeformat
Erzeuge:
- `handoffs/HANDOFF_20260217_ai_largeN_w30_headless_abort_hardening.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Datei/Änderung/Grund)
4. Validation (exakte Commands + Resultate)
5. Breaking Changes / Rest-Risiken
6. Nächste 5 priorisierte Folgeaufgaben

## Qualitätslatte
- Wenn etwas skipped wird: nur mit präzisem, technisch begründetem Guard + Nachweis, dass Produktverhalten trotzdem getestet wird.
- Jeder neue Test muss einen echten Failure-Mode absichern.
- Keine Placeholders, kein "sollte passen".
