# PROMPT_20260217_ai_largeQ_w31_mojibake_rerun_hardfail

Du bist AI-LargeQ-Rerun auf Branch `feature/v1-ux-aiB`.

## Kontext
Der vorige Mojibake-Blitzlauf wurde abgelehnt:
- Nur minimale Fixes geliefert.
- Guard-Test schlug weiterhin fehl.
- Viele kaputte UI-Strings bestehen fort.

## Mission
Schneller, großer Mojibake-Fix mit Fokus auf **user-sichtbare Runtime-Texte**.
Ziel: Screenshot-Problemklasse komplett entfernen (kaputte Labels/Tooltips/Hints/Statusmeldungen).

## Non-Negotiable DoD
1. Keine Mojibake in user-sichtbaren UI-Strings in `gui/**`.
2. Guard-Test besteht.
3. Relevante UI-Regressionstests bleiben grün.
4. Klare Before/After-Evidence mit Zählung.

---

## Harte Regeln

### Erlaubte Bereiche
- `gui/**`
- `test/test_text_encoding_mojibake_guard.py`
- optional `test/**` für gezielte Zusatztests

### No-Go
- Keine inhaltliche UX/Feature-Änderung, nur Text-Encoding-Korrekturen.
- Keine CAD-Logikänderungen in `modeling/**`.
- Kein "Skip" als Ersatz für Fix.
- Kein Greenwashing durch Abschwächung zentraler Assertions.

---

## Priorität (wichtig)

### P0 (Pflicht, runtime sichtbar)
Fixe Mojibake in String-Literalen, die zur Laufzeit angezeigt werden, z. B. in:
- `status_message.emit(...)`
- `show_message(...)`
- `tr("...")` bei sichtbaren Labels/Hints
- `QPushButton("...")`, `QAction("...")`, `menu.addAction("...")`
- `setToolTip("...")`, `setText("...")`, Dock-/Panel-Titel

### P1 (nach P0)
- Weitere sichtbare Texte in Dialogen/Property-Panels.

### P2 (optional, wenn Zeit)
- Kommentare/Docstrings bereinigen.

Hinweis: P2 darf P0 nicht blockieren.

---

## Arbeitspakete

### AP1: Inventur mit Runtime-Fokus
- Erstelle eine Liste aller P0-Treffer (Datei + Zeile + vorher/nachher).
- Nutze Muster wie `Ã`, `Â`, `â`, `├`, `┬`, `�`, `Ô`, `Õ`, `×` als Trigger.

### AP2: Bulk-Fix der Runtime-Strings
- Korrigiere alle P0-Texte in einem konsistenten Sweep.
- Achte auf korrekte Sonderzeichen: `ü ä ö ß ° × →`.
- Icons/Emojis nicht zerstören.

### AP3: Guard-Test auf Runtime-Texte schärfen
- `test/test_text_encoding_mojibake_guard.py` so anpassen, dass er primär runtime-relevante String-Kontexte prüft (P0), nicht nur beliebige Kommentare.
- Optional separate non-blocking Info-Ausgabe für Kommentar-Mojibake.

### AP4: Regression-Safety
- Sicherstellen, dass gängige UI-Tests weiter laufen.

### AP5: Evidence
- Vorher/Nachher-Zählung liefern:
  - `rg` Treffer P0 vor Fix
  - `rg` Treffer P0 nach Fix

---

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py gui/browser.py gui/main_window.py gui/widgets/feature_detail_panel.py

conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py

$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py
```

Zusätzliche Reporting-Scans:
```powershell
rg -n "Ã|Â|â|├|┬|�|Ô|Õ|×" gui -g "*.py"
rg -n "status_message\.emit\(|show_message\(|setToolTip\(|addAction\(|QPushButton\(|tr\(" gui -g "*.py"
```

---

## Harte Abnahmebedingungen
Delivery = FAIL wenn:
1. Guard-Test weiterhin fehlschlägt.
2. Sichtbare Mojibake-Texte (P0) bleiben.
3. Keine klare Before/After-Evidence geliefert wird.
4. Regressionstests brechen ohne gute Begründung.

---

## Rückgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeQ_w31_mojibake_rerun_hardfail.md`

Struktur:
1. Problem
2. Root Cause
3. API/Behavior Contract
4. Impact (Datei + konkrete Textfixes)
5. Validation (Commands + Resultate)
6. Breaking Changes / Rest-Risiken
7. Offene Restliste (P1/P2)
8. Nächste 5 Folgeaufgaben

## Zusatzpflicht
- Liste mindestens 30 konkrete Korrekturen als `vorher -> nachher`.
- Markiere jede Korrektur als `runtime-visible` oder `internal`.
- Kein "fertig" ohne diese Liste.
