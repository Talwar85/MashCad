# PROMPT_20260217_ai_largeW_w32_encoding_rework_hardfail

Du bist AI-LARGE-W (Encoding Rework Cell) auf Branch `feature/v1-ux-aiB`.

## Kontext
Vorherige Deliverys (`HANDOFF_20260217_ai_largeS_w31_full_encoding_audit_hardgate.md`, `HANDOFF_20260217_ai_largeT_w31_v1_acceleration_gigapack.md`) sind inhaltlich nicht ausreichend belastbar.

### Nachgewiesene Defizite
1. Mojibake-/Encoding-Guard ist technisch zu schwach:
- In `test/test_text_encoding_mojibake_guard.py` wird aktuell mit `if pattern in line` gearbeitet statt mit echten Regex-Matches (`re.search`).
- Dadurch werden viele definierte Pattern nicht wirklich geprueft.

2. Runtime-visible Textfehler sind noch vorhanden (Beispiele):
- `auswÄhlen`
- `BestÄtigen`
- `Lüschen`

3. "Alles gruen" Claims ohne harte, reproduzierbare Nachweise sind nicht akzeptiert.

---

## Mission (Hard Rework)
Schliesse Encoding-/Mojibake-Thema belastbar ab: technisch korrekt, testbar, reproduzierbar.

## Harte Regeln (STRICT)
1. Keine neuen Skips/Xfails.
2. Keine Tests abschwaechen oder umgehen.
3. Keine Placebo-Aenderungen.
4. Keine Backup-/Temp-Dateien erzeugen (`*.bak`, `temp_*`).
5. Jede Behauptung im Handoff muss durch echte Kommandos belegbar sein.

---

## Arbeitspaket A - Runtime-String Fix (P0)
Bereinige user-visible Texte in GUI-Dateien (mindestens):
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- optional weitere `gui/**`, falls betroffen

### Anforderungen
- Ersetze korrupte/inkonsistente Strings durch korrekte Formulierungen.
- Fokus auf sichtbare UI-Texte: Menues, Tooltips, HUD, Dialoglabels, Statusmeldungen.
- Keine rein kosmetischen Kommentar-Rewrites als Hauptergebnis verkaufen.

---

## Arbeitspaket B - Guard-Test technisch korrekt machen (P0)
Datei: `test/test_text_encoding_mojibake_guard.py`

### Pflichtfixes
1. Pattern-Pruefung auf echte Regex-Matches umstellen (`re.search`).
2. Scanner darf nicht stillschweigend zu viel ausblenden.
3. Whitelist restriktiver machen (nur dokumentierte, begruendete Ausnahmen).
4. Fehlerausgabe konkret: Datei + Zeile + gefundener Ausschnitt.

### Zusatz
- Füge eine kleine gezielte Regression-Pruefung hinzu (neue oder erweiterte Tests), die bekannte Fehlwoerter sicher erkennt.

---

## Arbeitspaket C - Evidence-Hardening (P0)
Erzeuge belastbare Nachweise:
1. Vorher/Nachher-Scan mit exakt denselben Kommandos.
2. Liste der wirklich geaenderten runtime-visible Strings (Datei + Zeile + before/after).
3. Keine pauschalen Aussagen wie "alles behoben" ohne Messbasis.

---

## Pflicht-Validierung (ohne Ausnahme)
```powershell
conda run -n cad_env python -m py_compile gui/sketch_editor.py gui/sketch_handlers.py test/test_text_encoding_mojibake_guard.py
conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py::TestAbortLogic::test_escape_and_right_click_same_endstate test/test_discoverability_hints.py::TestDiscoverabilityW16::test_context_navigation_hint_in_peek_3d_mode
```

Zusatz-Scan (im Handoff mit Outputauszug dokumentieren):
```powershell
rg -n "auswÄhlen|BestÄtigen|Lüschen|Ã|â|Ãƒ|Ã‚|Ã¢" gui -g "*.py" --glob "!*.bak*"
```

Hinweis: Wenn legitime Treffer verbleiben, muessen sie einzeln begruendet werden (mit Datei/Zeile und warum nicht Mojibake).

---

## Akzeptanzkriterien
- Guard technisch korrekt (Regex-basiert), nicht nur formal gruen.
- Kritische runtime-visible Fehlstrings behoben.
- Pflichtvalidierung vollstaendig erfolgreich.
- Handoff liefert harte Evidence statt Marketing-Text.

---

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_largeW_w32_encoding_rework_hardfail.md`

Struktur:
1. Problem
2. Root Cause
3. API/Behavior Contract
4. Impact (Dateien + konkrete before/after Beispiele)
5. Validation (exakte Commands + Ergebnis)
6. Rest-Risiken
7. Offene Punkte (falls etwas nicht abgeschlossen wurde, transparent markieren)

Wichtig: Wenn etwas nicht geloest ist, explizit `PARTIAL` statt `COMPLETE` deklarieren.
