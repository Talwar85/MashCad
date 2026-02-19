Du bist GLM 4.7 (UX/WORKFLOW Cell) und übernimmst ab sofort den bisherigen Gemini-Track.
Branch: `feature/v1-ux-aiB`

Lies ZUERST vollständig:
- `handoffs/HANDOFF_20260216_core_to_gemini_w6.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w7.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w8.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w9.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w10.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w11.md`
- `handoffs/HANDOFF_20260216_gemini_w5.md`
- `handoffs/HANDOFF_20260216_gemini_w6.md`
- `handoffs/HANDOFF_20260216_glm47_w2.md`

## Rolle und Ziel
Du ersetzt Gemini im UX/Workflow-Track. Ziel ist production-grade Bedienbarkeit mit stabilen UI-Gates und klarer Fehlerkommunikation.

## Harte Regeln
1. Nicht anfassen:
- `modeling/**`
- `config/feature_flags.py` (nur lesen)

2. Fokusdateien:
- `gui/**`
- `test/test_ui_abort_logic.py`
- `test/harness/test_interaction_consistency.py`
- `test/test_browser_tooltip_formatting.py`
- `roadmap_ctp/**`
- `handoffs/**`

3. Keine Placeholders, keine Behauptung ohne reproduzierbaren Command.

4. Jede Aussage in deinem Handoff muss mit Executed Commands + Result belegt sein.

## Aufgabenpakete (Reihenfolge verbindlich)

### W4-1 P0: Right-Click Abort/Background-Clear finalisieren
Ziel:
- Verhalten muss deterministisch sein:
  - Right-Press: aktive Drags/Tool-Operationen abbrechen.
  - Right-Click auf Hintergrund: Selektion löschen.
  - Right-Click auf Objekt: Kontextmenü.
- Keine doppelten Handler-Pfade/Shadow-Logik.

Abnahme:
- `test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_cancels_drag`
- `test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_background_clears_selection`

### W4-2 P0: UI-Gate Stabilität unter Windows/OpenGL-Hickups
Ziel:
- UI-Tests dürfen nicht durch `wglMakeCurrent`/Render-Context-Rennen unzuverlässig werden.
- Stabilisierung nur über UI/Test-Harness-Schicht (kein Core/Kernelscope).

Abnahme:
- Nachweisbare Strategie + Umsetzung in `test/**` oder `gui/**` (wo sinnvoll) mit minimalem Risiko.
- Dokumentierter Tradeoff in `roadmap_ctp/`.

### W4-3 P1: Drift-UX konsolidieren
Ziel:
- `tnp_ref_drift` überall als recoverable warning kommunizieren (Tooltip/Farbe/Label konsistent).
- Kein Vermischen mit hard errors.

Abnahme:
- Browser-Tooltip-Tests laufen stabil.
- Keine Regression in bestehenden Statustexten.

### W4-4 P1: Bedienhinweise im 2D-Modus sichtbar machen
Ziel:
- Rotation + Pan/Peek (Leertaste) im Sketch/2D klar kommunizieren.
- Nicht in Toolbars verstecken; explizites visuelles Feedback.

Abnahme:
- Implementierung + mindestens ein UI-Test oder deterministische Verifikation.
- Kurzdoku in `roadmap_ctp/` mit Begründung (warum diese Platzierung/Hinweisform).

## Pflicht-Validierung (genau ausführen)
```powershell
# Für robustere OpenGL-Ausführung in CI/Headless-like Environments
$env:QT_OPENGL='software'

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_cancels_drag test/test_ui_abort_logic.py::TestAbortLogic::test_right_click_background_clears_selection -vv
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -vv
```

## Rückgabeformat (verpflichtend)
Datei: `handoffs/HANDOFF_20260216_glm47_w3_ux_replace.md`

Struktur:
1. Problem
2. Read Acknowledgement (Dateiliste + 1 Satz Impact je Datei)
3. API/Behavior Contract
4. Impact (Dateien/Änderungen)
5. Validation (alle Commands + Resultate)
6. Breaking Changes / Rest-Risiken
7. Nächste 3 priorisierte Folgeaufgaben

Wichtig:
- Wenn etwas nicht vollständig grün wird: exakt sagen was grün, was rot, warum, und mit welchem reproduzierbaren Command.
