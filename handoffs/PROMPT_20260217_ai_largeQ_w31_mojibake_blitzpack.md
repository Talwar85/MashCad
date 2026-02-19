# PROMPT_20260217_ai_largeQ_w31_mojibake_blitzpack

Du bist AI-LargeQ auf Branch `feature/v1-ux-aiB`.

## Mission
Führe einen schnellen, vollständigen Mojibake-Fix-Sweep durch:
Alle kaputten Zeichenfolgen wie `fÃ¼r`, `zurÃ¼ck`, `├╝`, `┬░`, `â†’`, `�` in **user-sichtbaren UI-Texten** müssen korrigiert werden.

Referenzproblem (Screenshot): kaputte Labels wie `Ã¼ 2-Point`, `Ôè× Center`.

## Ziel (DoD)
1. Alle user-sichtbaren UI-Strings sind korrekt lesbar (de/en), ohne Mojibake.
2. Keine funktionalen Regressionen.
3. Ein automatischer Guard-Test verhindert Rückfall.

## Harte Regeln

### Fokusbereiche (Pflicht)
- `gui/**` (insb. Toolbar/Sketch/Browser/Panel/Status/Hints)
- `i18n/**` falls nötig
- `test/**` nur für Guard-Tests/Anpassung

### No-Go
- Kein Umbau der CAD-Kernlogik (`modeling/**`) außer absolut notwendig (sollte nicht nötig sein).
- Keine kosmetische „teilweise“ Korrektur: Ziel ist breiter Sweep für UI-Strings.
- Keine pauschalen Skips in Tests.

## Arbeitspakete

### AP1: Inventur & Klassifikation
- Scanne auf Mojibake-Muster in `gui/**/*.py`:
  - `Ã`, `Â`, `�`, `├`, `┬`, `â`, `Ô`, `Õ`, `×`
- Klassifiziere Funde in:
  1) **user-visible runtime strings** (Pflicht-Fix)
  2) interne Kommentare/Docs (optional, wenn Zeit)

### AP2: Runtime-UI-Fix (Pflicht)
- Korrigiere alle user-visible Strings in:
  - Button-Texte, Menüs, Tooltips, Status/HUD/Hint-Texte, Notifications, Log-Messages mit User-Relevanz.
- Beispiele:
  - `fÃ¼r` -> `für`
  - `zurÃ¼ck` -> `zurück`
  - `LÃ¶schen` -> `Löschen`
  - `Â°` -> `°`
  - `â†’` -> `→`
- Achte darauf, dass Symbole konsistent bleiben und nicht durch kaputte Zeichen ersetzt werden.

### AP3: Toolbar/Sketch Schwerpunkt
- Prüfe gezielt die Sketch-Toolbar/Mode-Segmente (wie im Screenshot):
  - „2-Point“, „Center“, Toolnamen, Mode-Chips.
- Stelle sicher, dass dort keine korrupten Präfixe/Icons als Textmüll erscheinen.

### AP4: Mojibake Guard-Test (Pflicht)
- Erstelle neuen Test:
  - `test/test_text_encoding_mojibake_guard.py`
- Test soll user-visible String-Literals in `gui/**` auf Mojibake-Signaturen prüfen.
- Erlaube kleine Whitelist, falls es legitime Sonderfälle gibt (muss dokumentiert werden).
- Ziel: neuer Commit darf keine neuen kaputten Strings einführen.

### AP5: Regression-Schutz
- Führe relevante UI-Tests aus, um zu zeigen, dass Fixes keine Interaktionen brechen.

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/browser.py gui/main_window.py gui/widgets/feature_detail_panel.py

conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py

# Reporting-Scan (nach Fix)
rg -n "Ã|Â|�|├|┬|â|Ô|Õ|×" gui -g "*.py"
```

## Abnahme-Gate (hart)
Delivery = FAIL wenn:
1. Screenshot-ähnliche Mojibake-Strings in Runtime-UI verbleiben.
2. Kein Guard-Test geliefert wird.
3. Guard-Test fehlt oder triviale Placebo-Checks enthält.
4. Relevante UI-Tests regressieren.

## Rückgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeQ_w31_mojibake_blitzpack.md`

Struktur:
1. Problem
2. Root Cause
3. API/Behavior Contract
4. Impact (Datei + was korrigiert)
5. Validation (Commands + Resultate)
6. Breaking Changes / Rest-Risiken
7. Offene Mojibake-Restliste (falls vorhanden, mit Priorität)
8. Nächste 5 Folgeaufgaben

## Zusatzpflicht
- Liste explizit mindestens 20 konkret korrigierte String-Beispiele auf (vorher -> nachher).
- Markiere, welche davon user-sichtbar sind.
