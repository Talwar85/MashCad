# PROMPT_20260216_gemini_w6

Du bist Gemini (UX/WORKFLOW) auf Branch `feature/v1-ux-aiB`.

## Pflicht: Erst lesen, dann arbeiten
Lies diese Dateien vollständig, **bevor** du irgendeinen Edit machst:
1. `handoffs/HANDOFF_20260216_core_to_gemini_w6.md`
2. `handoffs/HANDOFF_20260216_core_to_gemini_w7.md`
3. `handoffs/HANDOFF_20260216_core_to_gemini_w8.md`
4. `handoffs/HANDOFF_20260216_core_to_gemini_w9.md`
5. `handoffs/HANDOFF_20260216_core_to_gemini_w10.md`
6. `handoffs/HANDOFF_20260216_core_to_gemini_w11.md`
7. `handoffs/HANDOFF_20260216_ai3_w5.md`
8. `handoffs/HANDOFF_20260216_glm47_w2.md`

## Pflicht: Lesebestaetigung im Handoff
Dein Rueckgabe-Handoff muss am Anfang eine Sektion enthalten:
`## Read Acknowledgement`
Mit 8 Bulletpoints (je Datei 1 Satz):
- Was ist der Kern-Contract?
- Welche konkrete UX/QA-Auswirkung folgt daraus?

Ohne diese Sektion ist das Ergebnis unvollstaendig.

---

## Harte Regeln
1. **Keine Edits in `modeling/**`**.
2. Fokus auf:
- `gui/viewport_pyvista.py`
- `gui/widgets/status_bar.py`
- `gui/widgets/tnp_stats_panel.py`
- `gui/browser.py`
- `test/test_ui_abort_logic.py`
- `test/harness/test_interaction_consistency.py`
- optional `test/test_browser_tooltip_formatting.py`
3. Keine Placeholders, keine "wahrscheinlich"-Aussagen ohne Repro.

---

## Aktuelle Fakten (bereits reproduziert)
- `gui/viewport_pyvista.py` hat weiterhin **zwei** `eventFilter`-Definitionen:
  - erste bei ~Zeile 528
  - zweite bei ~Zeile 2312
- Damit ist die fruehe Right-Click-Logik effektiv tote/ueberschriebene Logik.
- `test/test_ui_abort_logic.py` + `test/harness/test_interaction_consistency.py` laufen aktuell nicht stabil durch (UI-Gate bleibt nicht gruen).

---

## Aufgaben (bindend)

### P0-1: `eventFilter` wirklich konsolidieren
Ziel:
- Genau **eine** aktive `def eventFilter(...)` in `gui/viewport_pyvista.py`.

Pflichten:
1. Die Right-Click-Abort-Logik muss in der **tatsaechlich aktiven** `eventFilter`-Implementierung liegen.
2. Kein doppelter Methodenname `eventFilter` mehr in der Klasse.
3. Kein regressives Verhalten fuer Context-Menu / Zoom / Picking.

Check:
```powershell
rg -n "^\s*def eventFilter\(" gui/viewport_pyvista.py
# Erwartet: genau 1 Treffer
```

### P0-2: Right-Click Abort/Background-Clear stabil machen
Ziel:
- Press auf Right-Click bricht aktive Drag/Operation korrekt ab.
- Release auf Background (Click, nicht Drag) leert Selection.

Pflichten:
1. Press: Drag-/Mode-Abbruch wie spezifiziert.
2. Release-Background: `clear_selection()` + `background_clicked.emit()`.
3. Release auf Objekt: kein Background-Clear.
4. Keine schweren Render-/Pick-Aufrufe bei jedem Event (nur wenn noetig).

### P0-3: UI-Gate entblocken
Ziel:
- Kein Infrastructure-BLOCKED mehr im UI-Gate.

Pflichten:
1. `status_bar.py` bleibt `tr`-sicher.
2. Keine Access-Violation durch neue Abort-Logik im Testpfad.

### P1-1: Drift UX konsistent halten
Ziel:
- `tnp_ref_drift` bleibt klar als recoverable warning sichtbar (nicht hard error).

Pflichten:
1. Browser-Farbe/Tooltip konsistent mit Panel-Mapping.
2. Keine Regression der bestehenden Drift-Tooltip-Tests.

---

## Pflicht-Validierung (alle ausfuehren)
```powershell
conda run -n cad_env python -m py_compile gui/viewport_pyvista.py gui/widgets/status_bar.py gui/widgets/tnp_stats_panel.py gui/browser.py test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py

rg -n "^\s*def eventFilter\(" gui/viewport_pyvista.py

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py

powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

Erwartung:
- Keine Infrastructure-BLOCKED-Klassifikation wegen `tr`/eventFilter.
- UI-Suiten laufen ohne Access-Violation.

---

## Rueckgabeformat
Datei:
- `handoffs/HANDOFF_20260216_gemini_w6.md`

Struktur:
1. Problem
2. Read Acknowledgement  (**Pflicht, 8 Punkte**)
3. API/Behavior Contract
4. Impact
5. Validation
6. Breaking Changes / Rest-Risiken

Zusatzpflicht:
- Liste der geaenderten Dateien + je 1 Satz "warum".
- Wenn etwas nicht gruen ist: exakter blocker + minimaler next fix.
