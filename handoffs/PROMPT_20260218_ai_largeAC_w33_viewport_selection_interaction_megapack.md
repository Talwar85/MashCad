# PROMPT_20260218_ai_largeAC_w33_viewport_selection_interaction_megapack

Du bist AI-LARGE-AC (Viewport Selection + Interaction Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere ein grosses 3D-Interaction-Paket mit Fokus auf:
1. praezise Selektion,
2. konsistente Abort-Paritaet,
3. robustes Preview/Actor-Lifecycle,
4. bessere wahrgenommene Interaktionsperformance.

## Scope
Erlaubte Dateien:
- `gui/viewport_pyvista.py`
- `gui/viewport/selection_mixin.py`
- `gui/viewport/edge_selection_mixin.py`
- `gui/main_window.py` (nur viewport workflow hooks)
- `test/test_viewport_interaction_w33.py`
- `test/test_main_window_w26_integration.py`
- `test/test_ui_abort_logic.py`

No-Go:
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `modeling/**`

## Harte Regeln
1. Keine neuen `skip` oder `xfail`.
2. Keine stillen except-blanks fuer native Fehler.
3. Keine `.bak` oder `temp_*` Dateien erzeugen.
4. Jede UI-Aenderung braucht mindestens einen Verhaltenstest.

## EPIC AC1 - Selection Precision (P0)
Ziel: Face/Edge/Body-Picking ist stabil und kontextgerecht.

Aufgaben:
1. Hit-Priorisierung pro Modus explizit machen.
2. Hover vs selected states sauber trennen.
3. Multi-select toggle Verhalten gegen false positives haerten.

## EPIC AC2 - Abort Parity in 3D (P0)
Ziel: ESC und Rechtsklick-ins-Leere fuehren zu identischem Endzustand.

Aufgaben:
1. Abbruchpfade fuer viewport interaction states vereinheitlichen.
2. Nach Abbruch keine verbleibenden transient actors.
3. Status-/Hint-Ausgabe konsistent zum echten State.

## EPIC AC3 - Actor Lifecycle Hardening (P1)
Ziel: Keine stale actors, keine remove_actor Konflikte, kein ghost highlight.

Aufgaben:
1. Actor-Tracking cleanup robust machen.
2. Double-remove safe, aber sichtbar geloggt.
3. Mode transitions 2D<->3D ohne residue.

## EPIC AC4 - Interaction Performance (P1)
Ziel: weniger churn bei hover/pick/selection.

Aufgaben:
1. Unnoetige actor rebuilds reduzieren.
2. Lightweight update-Strategie fuer hover feedback.
3. Nachweis ueber tests/log assertions.

## Testpflicht
Mindestens abdecken:
1. Pick-Prioritaet in zentralen Modis.
2. ESC/RightClick parity im viewport flow.
3. actor cleanup nach mode switch.
4. kein stale selection state nach batch focus/recover und component switch.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/viewport_pyvista.py gui/viewport/selection_mixin.py gui/viewport/edge_selection_mixin.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_viewport_interaction_w33.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
```

## Akzeptanzkriterien
1. Mindestens 2 sichtbare 3D-UX-Verbesserungen.
2. Keine neuen skips/xfails.
3. Preflight bleibt pass.
4. Pflichtvalidierung komplett gruen.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260218_ai_largeAC_w33_viewport_selection_interaction_megapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
