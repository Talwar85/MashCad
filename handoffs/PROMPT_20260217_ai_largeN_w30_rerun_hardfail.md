# PROMPT_20260217_ai_largeN_w30_rerun_hardfail

Du bist AI-LargeN auf Branch `feature/v1-ux-aiB`.

## Kontext
Der vorherige W30-N Lauf wurde ABGELEHNT:
- Access Violations in Headless bestehen weiter.
- Keine echte Stabilisierung von `test_ui_abort_logic` / `test_discoverability_hints`.
- Kosmetische Test-String-Aenderung reicht NICHT.

## Ziel (non-negotiable)
Eliminiere reproduzierbare Headless-Crashes fuer:
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`

"Passed" ist nur gueltig, wenn diese Suiten ohne Access Violation laufen.

## Harte Regeln
1. Kein Fake-Delivery:
- Keine Behauptung "nicht reproduzierbar", wenn Crash im Branch reproduzierbar ist.
- Keine rein textuellen Test-Aenderungen als Hauptresultat.

2. No-Go fuer Schnellschuesse:
- Kein globales blindes `pytest.skip`.
- Kein Entfernen relevanter Assertions.
- Kein Deaktivieren von Kern-Workflows.

3. Erlaubte Bereiche:
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/ui/**`
- `test/conftest.py`
- falls notwendig: gezielte Guards in UI-Bootstrap (minimal, dokumentiert)

4. Falls Produktcode angepasst wird, nur minimal und begruendet:
- bevorzugt test-fixture/bootstrapping first
- keine regressiven UX-Verluste

## Pflichtarbeitspakete
### AP1 Crash-Repro-Matrix
- Dokumentiere genaue Repro-Kommandos + Crash-Stack-Signatur.
- Zeige mindestens 1 stabile Gegenprobe nach Fix.

### AP2 Headless-Bootstrap-Hardening
- Stabilisiere MainWindow-Fixtures fuer Headless ohne VTK/Interactor-Absturz.
- Nutze reproduzierbare Patch-/Stub-Strategie mit minimalem Scope.

### AP3 Abort-Parity bleibt intakt
- Nach Stabilisierung weiterhin ESC/Right-Click Endzustands-Paritaet pruefen.
- Keine Verhaltensverschlechterung bei Cancel-Logik.

### AP4 Discoverability stabil
- Hints-Tests robust gegen Encoding/Event-Order, ohne Semantik zu verwaessern.

### AP5 Regression-Fence
- Belege, dass W29/W30 relevante Suiten weiter laufen.

## Pflicht-Validierung (muss vollstaendig im Handoff stehen)
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py test/test_sketch_editor_w26_signals.py
```

## Abnahme-Gate (hart)
- Wenn eine der ersten beiden Suiten crasht/aborts -> DELIVERY = FAIL.
- Wenn nur kosmetische String-Aenderungen ohne Crash-Fix -> DELIVERY = FAIL.

## Rueckgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeN_w30_rerun_hardfail.md`

Struktur:
1. Problem
2. Root Cause (konkret)
3. API/Behavior Contract
4. Impact (Datei + Grund)
5. Validation (exakte Kommandos + Resultate)
6. Breaking Changes / Rest-Risiken
7. Naechste 5 priorisierte Folgeaufgaben

## Zusatzpflicht
- Liste ALLE geaenderten Dateien explizit auf.
- Wenn ein Punkt nicht geloest werden konnte: klar als BLOCKED markieren, nicht als "fertig".
