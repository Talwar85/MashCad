Du bist `AI-LARGE-F` auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollständig:
- `handoffs/HANDOFF_20260217_altki_smokepack_browser.md`
- `handoffs/HANDOFF_20260217_altki_smokepack_feature_detail.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w11.md`
- `roadmap_ctp/ERROR_CODE_MAPPING_QA_20260215.md`

## Mission (W26-F)
Liefere einen großen sichtbaren Produkt-Sprung im Browser-/Diagnostik-/Recovery-Bereich:
1. problemorientierter Browser-Flow,
2. Feature-Detail-Panel mit schnellen Recovery-Aktionen,
3. konsistenter Error-Code-UX mit Taxonomie (`tnp_ref_*`, `rebuild_finalize_failed`, `ocp_api_unavailable`),
4. robuste Gate-/QA-Abdeckung ohne Skip-Tricks.

## Harte Regeln
1. Kein Skip/XFail hinzufügen, um Rot zu kaschieren.
2. Keine "nur Doku"-Antwort ohne konkrete Umsetzung.
3. Keine Änderungen in:
- `modeling/**`
- `gui/sketch_editor.py`
- `gui/viewport_pyvista.py`
4. Keine Breaking-Refactors außerhalb des Scopes.
5. Bei Flakes: deterministisch machen, nicht verdecken.

## Scope (nur diese Bereiche)
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
- `gui/main_window.py` (nur Integration glue, minimal)
- `test/test_browser*.py`
- `test/test_feature_detail_panel*.py`
- `test/test_operation_summary*.py`
- `test/test_notification_manager*.py`
- optionale Ergänzungen in `roadmap_ctp/**`

## Große Arbeitspakete

### Paket F1: Browser Problem Workflow v2
Pflicht:
1. "Problem First"-Navigation:
- schnelles Springen zum nächsten Problem-Feature (keyboard-first),
- klare visuelle Priorisierung (Critical > Blocked > Error > Warning).
2. Multi-Select für Problem-Features inkl. Batch-Aktionen:
- "retry rebuild" / "open diagnostics" / "isolate body" (je nach bestehender API).
3. Anti-Flicker/Refresh-Stabilität:
- kein sichtbares Flackern bei häufiger Aktualisierung,
- keine UI-Hänger bei >200 Features im Tree (Smoke-Metrik).

### Paket F2: Feature Detail Recovery Actions
Pflicht:
1. Detailpanel zeigt Error-Taxonomie klar und aktionsfähig:
- `tnp_ref_missing`
- `tnp_ref_mismatch`
- `tnp_ref_drift`
- `rebuild_finalize_failed`
- `ocp_api_unavailable`
2. Für jede Kategorie mindestens eine sinnvolle Recovery-Aktion (UI-seitig):
- z. B. "Referenz neu wählen", "Feature editieren", "Konflikt isolieren", "Dependency prüfen".
3. Copy-Diagnostics verbessert:
- enthält strukturierte Felder + klare Kurzfassung für schnelle Weitergabe.

### Paket F3: Operation Summary + Notification Alignment
Pflicht:
1. Operation Summary und Notification Layer sprechen dieselbe Schwere-Sprache:
- Statusklasse/Severity konsistent dargestellt.
2. Keine widersprüchlichen Meldungen zwischen Panel, Toast, Browser-Badge.
3. Für Recoverable-Warnings klare "Weiterarbeiten möglich"-Kommunikation.

### Paket F4: QA/Gate-Härtung für diesen Scope
Pflicht:
1. Neue/erweiterte Tests mit Behavior-Proof (nicht nur Existenzprüfungen).
2. Mindestens 18 neue Assertions:
- 7 Browser-Workflow,
- 6 Feature-Detail-Recovery,
- 5 Summary/Notification-Konsistenz.
3. Keine Regression in bestehenden W21-Smoke-Packs.

## Pflicht-Validierung (ohne Skip)
Führe exakt diese Kommandos aus:

```powershell
conda run -n cad_env python -m py_compile gui/browser.py gui/widgets/feature_detail_panel.py gui/widgets/operation_summary.py gui/managers/notification_manager.py gui/main_window.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py -v
conda run -n cad_env python -m pytest -q test/test_feature_detail_panel_w21.py -v
conda run -n cad_env python -m pytest -q test/test_operation_summary_w21.py test/test_notification_manager_w21.py -v
```

Zusatz (falls neue Testdateien):
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py -v
```

## Abnahme-Kriterien (DoD)
1. Browser-Problem-Workflow ist sichtbar schneller und handlungsorientiert.
2. Feature-Detail-Panel bietet konkrete Recovery-Optionen statt nur Fehltext.
3. Error-Code-Mapping ist UX-seitig konsistent und vollständig für die genannten Codes.
4. Pflicht-Validierung grün, ohne neue Skip/xfail.
5. Mindestens ein nachvollziehbarer Product-Leap im UI, den Nutzer direkt merkt.

## Rückgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeF_w26_browser_diagnostics_recovery_surface.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact (Dateien + Änderungstyp)
4. Validation (Kommandos + Resultatzahlen)
5. Breaking Changes / Rest-Risiken
6. Nächste 5 priorisierte Folgeaufgaben

Zusätzlich:
- Commit-Liste (Hash + Message)
- kurze UX-Delta-Liste: "vorher" vs "nachher" in 6-10 konkreten Punkten

