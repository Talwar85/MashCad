# PROMPT_20260217_ai_largeY_w33_viewport_interaction_stability_ultrapack

Du bist AI-LARGE-Y (Viewport/3D Interaction Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Großes 3D-Produktpaket liefern: Selektion, Interaction-Flows, Preview-Cleanup und messbar bessere Interaktionsstabilitaet.

## Nicht-Ueberschneidung
Dieses Paket ist 3D/Viewport-zentriert und darf den Sketch-Core nicht anfassen.

### No-Go
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `modeling/**`

### Fokus
- `gui/viewport_pyvista.py`
- `gui/viewport/selection_mixin.py`
- `gui/viewport/edge_selection_mixin.py`
- `gui/main_window.py` (nur viewport/workflow hooks)
- viewport/workflow-bezogene Tests

## Harte Regeln
1. Keine neuen Skips/Xfails.
2. Keine stille Ausnahmebehandlung, die Fehler verschluckt.
3. Jede UX-Aenderung muss mindestens 1 Verhaltenstest haben.
4. Kein no-op "cleanup" ohne sichtbaren Effekt.

---

## EPIC Y1 - Selection Robustness Product Leap (P0)
Ziel: Auswahl in 3D ist praezise, vorhersagbar und ohne Ghost-States.

### Aufgaben
1. Hit-Priorisierung verbessern (Face/Edge/Body je Modus klar definiert).
2. Multi-Select / Toggle Verhalten vereinheitlichen.
3. Verhindere stale selection actors bei Moduswechseln und component switch.
4. Selektionsfeedback (highlight + status/hint) konsistent halten.

---

## EPIC Y2 - Abort/Cancel Parity in 3D Workflows (P0)
Ziel: ESC und Rechtsklick-ins-Leere beenden identische Interaktionszustände.

### Aufgaben
1. Fuer viewport-getriebene Flows parity absichern:
- selection operations
- preview-intensive interactions
- temporary transform/measure states

2. Sicherstellen, dass transient previews/actors bei Abort wirklich entfernt sind.
3. Keine hängenden mode-flags nach Abbruch.

---

## EPIC Y3 - Preview & Actor Lifecycle Hardening (P1)
Ziel: kein Actor-Leak, keine doppelten Remove-Pfade, kein Flicker durch stale previews.

### Aufgaben
1. Actor-Tracking vereinheitlichen, remove-paths robust gegen doppelte Calls.
2. Preview-Gruppen sauber trennen (selection, hover, operation-preview, debug).
3. Deterministische Cleanup-Reihenfolge beim mode switch 2D<->3D.

---

## EPIC Y4 - Interaction Performance (P1)
Ziel: Hover/Pick/Selection bei realen Szenen fluessig.

### Aufgaben
1. Hot-path reduzieren (unnötige actor rebuilds vermeiden).
2. Optionales throttling/debouncing dort, wo es UX-neutral ist.
3. Messbare Verbesserung dokumentieren (z. B. select latency, render churn, actor counts).

---

## Testpflicht
Erweitere/erzeuge suites, z. B.:
- `test/test_main_window_w26_integration.py`
- `test/test_browser_product_leap_w26.py` (nur falls relevant)
- neue gezielte suite `test/test_viewport_interaction_w33.py`

Pflichtabdeckung:
1. Selection-Prio pro Modus
2. ESC == Rechtsklick parity fuer viewport states
3. actor cleanup nach mode transitions
4. kein stale highlight nach component/target switch

---

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/viewport_pyvista.py gui/viewport/selection_mixin.py gui/viewport/edge_selection_mixin.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_viewport_interaction_w33.py
```

Wenn neue Tests noch fehlen, muessen sie von dir implementiert und gruen gemacht werden.

## Akzeptanzkriterien
- Mindestens 2 sichtbare 3D-UX-Verbesserungen.
- Mindestens 8 neue oder deutlich verschaerfte Viewport-Tests.
- Keine Regression in MainWindow/Abort-Suiten.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_largeY_w33_viewport_interaction_stability_ultrapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
