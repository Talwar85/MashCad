# PROMPT_20260217_ai_largeV_w32_workflow_browser_recovery_release_ultrapack

Du bist AI-LARGE-V (Workflow + Browser + Recovery + Release Ops Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses, user-sichtbares Produktpaket ausserhalb des Sketch-Kerns:
Browser-Workflow, Recovery-UX, Error-Mapping, Encoding-Hygiene, Gate-Operationalisierung.

## Nicht-Ueberschneidung mit AI-LARGE-U
Dieses Paket darf keine Sketch-Kernarbeit machen.

### No-Go
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`
- `gui/sketch_renderer.py`
- `modeling/**`

### Fokus-Dateien
- `gui/browser.py`
- `gui/main_window.py` (nur Workflow/Orchestrierung, nicht Sketch-Kern)
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/status_bar.py` (nur Recovery/Status-UX, kein Sketch-Core)
- `scripts/gate_fast_feedback.ps1`
- `scripts/preflight_ui_bootstrap.ps1`
- `test/**` (browser/workflow/recovery/encoding/gate)
- optional Doku unter `roadmap_ctp/**`

## Harte Regeln (STRICT)
1. Keine neuen Skips/Xfails.
2. Keine Test-Abschwaechung.
3. Keine Backup/Temp-Dateien.
4. Keine "nur Doku"-Lieferung ohne funktionalen Code.
5. Jede neue UX-Funktion braucht mindestens einen echten Behavior-Test.

---

## EPIC V1 - Browser Recovery Product Leap (P0)
Ziel: Recovery-Probleme nicht nur anzeigen, sondern handhabbar machen.

### V1.1 Recovery Action Surface
- Browser-Eintraege mit Fehlerstatus erhalten klare Aktionen (z. B. Retry, Reselect, Details).
- Aktionen muessen wirklich verdrahtet sein (kein Placeholder).

### V1.2 Failure Grouping + Priorisierung
- Mehrere fehlerhafte Features gruppieren, kritische zuerst.
- Navigationshilfe vom Browser zum Detailpanel verbessern.

### V1.3 Empty/Noisy State UX
- Browser darf bei vielen Warnungen nicht unlesbar werden.
- Klare Badges/Counter fuer Error/Warn/Blocked.

---

## EPIC V2 - Workflow Robustness 2D<->3D (P0)
Ziel: Moduswechsel + transient states sind deterministic und nachvollziehbar.

### V2.1 Transition Hygiene
- Bei 2D<->3D Wechsel: transient previews, selection leftovers, stale hints sauber resetten.
- Kein ghost UI nach Abbruchpfaden.

### V2.2 Abort Consistency Surface
- ESC/Rechtsklick-Verhalten in Workflow-States konsistent machen, wo MainWindow involviert ist.
- Status-Bar/Toasts muessen den echten State zeigen.

### V2.3 Focus + Discoverability
- Nach kritischen Transitions korrekter Fokus (Sketch/Viewport/Browser) nachvollziehbar.

---

## EPIC V3 - Error Envelope UX Mapping v2 Closeout (P0)
Ziel: Neue Fehlercodes komplett in UI abgedeckt, inklusive Runtime-Dependency-Infos.

Pflichtcodes:
- `tnp_ref_missing`
- `tnp_ref_mismatch`
- `tnp_ref_drift`
- `rebuild_finalize_failed`
- `ocp_api_unavailable`

### V3.1 Feature Detail Mapping
- Fuer jeden Code klare, differenzierte User-Meldung.
- `tnp_failure` Felder (category/reference_kind/next_action) sichtbar auswerten.

### V3.2 Status Bar + Toast Mapping
- Severity/Statusclass korrekt und konsistent.
- Keine pauschale "operation_failed"-Nebelmeldung mehr.

### V3.3 Regression Guard
- Tests muessen Mapping-Luecken hart erkennen.

---

## EPIC V4 - Mojibake + Encoding Guard Expansion (P1)
Ziel: Textoberflaeche sauber und regressionsfest.

### V4.1 Sweep
- UI-Texte in den betroffenen Workflow/Browser/Widget-Dateien auf fehlerhafte Zeichen pruefen und fixen.
- i18n-nahe Strings beruecksichtigen (auch wenn nicht in JSON ausgelagert).

### V4.2 Guard verbessern
- `test/test_text_encoding_mojibake_guard.py` erweitern:
  - relevante GUI-Ordner + ausgewaehlte Doku/Handoff-ignore-Regeln sauber definieren
  - false positives reduzieren, echte mojibake treffen

### V4.3 Nachweis
- Vorher/Nachher-Liste der gefixten Stellen in Handoff auffuehren.

---

## EPIC V5 - Release Ops Acceleration ohne Skip (P1)
Ziel: Schnellere Iteration, aber hartes Gate-Verhalten.

### V5.1 Gate-Profile operationalisieren
- `ui_quick`, `ui_core`, `browser_recovery` Profile klar trennen.
- Laufzeitziele + Coverage pro Profil dokumentieren.

### V5.2 Timeout-proof Ausfuehrung
- Lange Suiten in sinnvolle Chunks mit reproduzierbarer Command-Reihenfolge.
- Kein "wegen Timeout geskippt" mehr.

### V5.3 Script UX
- Skripte liefern klare Exit-Codes und eindeutige Fehlerhinweise.

---

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/browser.py gui/main_window.py gui/widgets/feature_detail_panel.py gui/widgets/status_bar.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestFastFeedbackTimeoutW29
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
```

Wenn etwas fehlschlaegt:
- fixen und erneut laufen lassen
- keine Skip-Loesung

---

## Akzeptanzkriterien
- Mindestens 3 sichtbare UX-Verhaltensaenderungen (Browser/Workflow/Recovery).
- Mindestens 10 neue oder deutlich verstaerkte Tests.
- Vollstaendige Pflicht-Validierung mit Ergebnissen.

---

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_largeV_w32_workflow_browser_recovery_release_ultrapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Dateien + Kern-Diff)
4. Validation (Commands + Resultat)
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
