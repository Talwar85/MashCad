# PROMPT_20260217_ai_largeR_w31_multi_epic_portfolio

Du bist AI-LargeR auf Branch `feature/v1-ux-aiB`.

## Mission
Liefere ein großes, mehrstufiges Portfolio mit mehreren EPICs, die den V1-Reifegrad sichtbar erhöhen.

## Harte Rahmenbedingungen
- Keine Änderungen in `modeling/**`.
- Keine unspezifischen "Refactors" ohne Nutzerwirkung.
- Jede EPIC-Lieferung braucht messbare Evidence (Tests + Vorher/Nachher).

## EPIC A - Mojibake Runtime Eradication (P0)
Ziel: Alle user-sichtbaren kaputten Texte (Labels/Tooltips/Hints/Status) beseitigen.

### Scope
- `gui/**`
- `test/test_text_encoding_mojibake_guard.py`

### Deliverables
1. Runtime-UI-Texte korrigiert (`ü ä ö ß ° × →`).
2. Guard-Test schlägt bei neuem Mojibake zuverlässig an.
3. Liste mit mindestens 40 konkreten `vorher -> nachher` Fixes.

### Pflicht-Checks
```powershell
conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py
```

## EPIC B - Headless Bootstrap Reliability (P0)
Ziel: UI-Tests in headless stabil und reproduzierbar ohne Access Violation.

### Scope
- `gui/viewport_pyvista.py`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `scripts/preflight_ui_bootstrap.ps1`

### Deliverables
1. Kein Access-Violation-Crash in Pflichtsuiten.
2. Bootstrap-Fallback sauber dokumentiert (Mock/Echt-Pfad).
3. Preflight klassifiziert Native-Bootstrap-Probleme eindeutig.

### Pflicht-Checks
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
```

## EPIC C - Sketch Interaction Leaps (P1)
Ziel: Deutlich bessere direkte Interaktion im Sketch (line/rect/arc/ellipse/polygon).

### Scope
- `gui/sketch_editor.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/test_line_direct_manipulation_w30.py`

### Deliverables
1. Line/Rect/Arc Interaktionen mit klarer Cursor-Parität und stabilen Drag-Endstates.
2. Ellipse/Polygon Handles visuell reduziert und verständlich.
3. Regressionsnetz für alle neuen Interaktionspfade.

### Pflicht-Checks
```powershell
conda run -n cad_env python -m pytest -q test/test_line_direct_manipulation_w30.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
```

## EPIC D - Browser/Recovery Product Flow (P1)
Ziel: Problemfeatures schneller finden, recovern und fokussieren.

### Scope
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `test/test_browser_product_leap_w26.py`
- `test/test_feature_detail_recovery_w26.py`

### Deliverables
1. Recovery-Entscheidungen klar priorisiert.
2. Batch-Recovery robust (inkl. mixed/hidden selection guards).
3. E2E-verifizierte "Recover & Focus" Flows.

### Pflicht-Checks
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py
```

## EPIC E - Gate Realism & Speed (P1)
Ziel: Quick-Gates wirklich quick, Full-Gates klar abgegrenzt.

### Scope
- `scripts/gate_fast_feedback.ps1`
- `test/test_gate_runner_contract.py` (nur falls nötig)

### Deliverables
1. `ui_quick` Laufzeitziel realistisch + nachweisbar.
2. Zielzeiten in Script, JSON, Dokumentation konsistent.
3. Kein Widerspruch zwischen "quick" und tatsächlicher Dauer.

## Abnahme (Portfolio)
- EPIC A + B müssen vollständig grün sein.
- Mindestens 2 der EPICs C/D/E zusätzlich vollständig grün.
- Handoff muss pro EPIC "Done/Partial/Blocked" klar ausweisen.

## Rückgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeR_w31_multi_epic_portfolio.md`

Struktur:
1. Problem
2. EPIC-Plan und Ergebnisstatus
3. Impact (Dateien + Gründe)
4. Validation (komplette Kommandos + Resultate)
5. Breaking Changes / Rest-Risiken
6. Nächste 10 Folgeaufgaben (priorisiert)
