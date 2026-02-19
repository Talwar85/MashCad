# PROMPT_20260217_ai_largeS_w31_full_encoding_audit_hardgate

Du bist AI-LargeS auf Branch `feature/v1-ux-aiB`.

## Mission
Fuehre einen vollstaendigen Encoding- und Mojibake-Audit mit Fixes durch.
Ziel: "alles geprueft" und reproduzierbar abgesichert.

## Scope (alles pruefen)
1. `gui/**` (alle user-visible runtime strings)
2. `i18n/**/*.json` (encoding + inhaltliche Konsistenz)
3. `scripts/**` (nur user-visible outputs, falls relevant)
4. `test/**` (Guardrails + Regression)
5. Optional: `docs/**`, `handoffs/**` (nur reporten, nicht prioritaer fixen)

## Harte Regeln
- Kein Greenwashing durch Skip oder abgeschwaechte Assertions.
- Keine CAD-Core Aenderungen in `modeling/**`.
- Keine nicht-erklaerten globalen Refactors.
- Jede Aenderung muss einem klaren Problem zugeordnet werden.

## Prioritaetsmodell
- P0: Runtime-visible mojibake (Buttons, Menues, Tooltips, Hints, Status, Dialogtexte)
- P1: i18n JSON encoding/integrity issues
- P2: comments/docstrings/internal-only strings

P0 und P1 muessen komplett geschlossen sein.

## EPIC A - Full Inventory & Classification (P0)
- Suche repo-weit nach typischen Mustern: `Ã`, `Â`, `â`, `├`, `┬`, `�`, `Ô`, `Õ`, `×`.
- Klassifiziere jede Fundstelle:
  - runtime-visible
  - internal-only
  - uncertain
- Erstelle eine Vorher-Matrix mit Counts pro Datei.

## EPIC B - Runtime Fix Sweep (P0)
- Korrigiere alle runtime-visible Mojibake-Strings in `gui/**`.
- Stelle korrekte Zeichen sicher (`ue/ae/oe/ss`, Gradzeichen, Pfeile, Multiplikationszeichen etc.).
- Fokus auf Bereiche mit hoher Sichtbarkeit (Sketch toolbar, status hints, context menus, dialogs).

## EPIC C - i18n JSON Integrity (P1)
- Verifiziere alle `i18n/**/*.json` als valides UTF-8.
- Pruefe auf Mojibake-Muster in Values.
- Pruefe key parity zwischen Sprachdateien (mindestens de/en falls vorhanden).
- Fixe gefundene Probleme.

## EPIC D - Guardrails (P0)
- Haerte `test/test_text_encoding_mojibake_guard.py`:
  - muss runtime-visible Contexts in `gui/**` pruefen
  - muss i18n JSON pruefen
  - darf eine kleine dokumentierte allowlist haben
- Der Guard muss bei echtem Mojibake failen.

## EPIC E - Regression Safety
- Fuehre relevante UI/interaction suites aus und sichere, dass nichts bricht.

## Pflicht-Validierung
```powershell
# 1) Compile checks
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/browser.py gui/main_window.py gui/widgets/feature_detail_panel.py

# 2) Encoding guard
conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py

# 3) UI regressions
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py

# 4) Reporting scans (before + after)
rg -n "Ã|Â|â|├|┬|�|Ô|Õ|×" gui i18n -g "*.py" -g "*.json"
```

## Hard Acceptance Gates
Delivery = FAIL wenn:
1. P0 runtime-visible Mojibake in `gui/**` verbleibt.
2. P1 i18n JSON Probleme verbleiben.
3. `test_text_encoding_mojibake_guard.py` nicht gruen ist.
4. Keine nachvollziehbare before/after count matrix geliefert wird.

## Rueckgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeS_w31_full_encoding_audit_hardgate.md`

Pflichtstruktur:
1. Problem
2. Root Cause
3. API/Behavior Contract
4. Impact (dateiweise, warum)
5. Validation (exakte commands + outputs)
6. Before/After Matrix (counts pro file)
7. Breaking Changes / Rest-Risiken
8. Naechste 10 Folgeaufgaben (priorisiert)

## Zusatzpflicht
- Liste mindestens 50 konkrete Korrekturen `vorher -> nachher`.
- Markiere jede als `runtime-visible`, `i18n`, oder `internal`.
- Explizite Restliste, falls irgendwas offen bleibt (mit Grund).
