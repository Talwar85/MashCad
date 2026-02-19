Du bist `AI-LARGE-F-FOLLOWUP` auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260217_ai_largeF_w26_browser_diagnostics_recovery_surface.md`
- `test/test_browser_product_leap_w26.py`
- `test/test_feature_detail_recovery_w26.py`
- `test/test_operation_summary_notification_alignment_w26.py`

## Ziel
Hebe W26-F von "bestanden" auf "produktionsreif belastbar":
1. fehlende MainWindow-Integration für neue Batch/Recovery-Signale,
2. echte Runtime-Behavior-Tests statt Existenzprüfungen,
3. Qualitätssicherung gegen Namenskollisionen/Signal-Überschreibung.

## Harte Regeln (nicht verhandelbar)
1. Keine Analyse-only Antwort.
2. Kein `skip`/`xfail`, um Rot zu kaschieren.
3. Keine Placeholders/TODO als finale Lösung.
4. Keine Änderungen in:
- `modeling/**`
- `gui/sketch_editor.py`
- `gui/viewport_pyvista.py`
5. Jeder neue öffentliche Hook braucht mindestens 1 positiven und 1 negativen Behavior-Test.
6. Verbotene Testmuster:
- reine `hasattr(...)`-Tests ohne Verhaltensprüfung,
- Tests, die nur "no exception" prüfen ohne fachliche Assertion.
7. Wenn ein Gate fehlschlägt: fixen, erneut ausführen, dokumentieren.

## Scope (erlaubt)
- `gui/main_window.py`
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/managers/notification_manager.py`
- `test/**` im W26-F Kontext

## Arbeitspakete

### Paket F-UX-1: MainWindow Signal Wiring vollständig
Implementiere verbindlich:
1. Handler für Browser Batch-Signale:
- `batch_retry_rebuild`
- `batch_open_diagnostics`
- `batch_isolate_bodies`
2. Handler für FeatureDetail Recovery-Signale:
- `recovery_action_requested`
- `edit_feature_requested`
- `rebuild_feature_requested`
- optional `delete_feature_requested` (falls bereits vorgesehen)
3. Definiere klare UX-Reaktion:
- Statusbar/Toast,
- Auswahlfokus,
- sichere No-Op wenn Daten fehlen.

### Paket F-UX-2: Guardrails gegen API-Kollisionen
Füge Schutz ein:
1. Keine Signal/Methoden-Namenskollisionen (wie zuvor bei `batch_open_diagnostics`).
2. Mindestens ein Test, der diese Kollision als Regression verhindert.
3. Wenn nötig, interne Namenskonvention durchsetzen (`*_requested`, `*_selected_*`).

### Paket F-UX-3: Testhärtung (Behavior-Proof)
Erweitere W26-Tests so, dass echte Wirkung geprüft wird.

Pflicht:
1. Mind. 14 neue oder verschärfte Assertions:
- 6 MainWindow Integration,
- 4 Batch/Recovery Runtime Verhalten,
- 4 Negative/Guardrail Fälle.
2. Jeder Signalpfad:
- Payload-Inhalt prüfen,
- Zielhandler-Aufruf prüfen,
- Fehlerpfad prüfen (z. B. leere Auswahl, None-Feature).

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile gui/main_window.py gui/browser.py gui/widgets/feature_detail_panel.py gui/widgets/operation_summary.py gui/managers/notification_manager.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py -v
conda run -n cad_env python -m pytest -q test/test_feature_detail_recovery_w26.py -v
conda run -n cad_env python -m pytest -q test/test_operation_summary_notification_alignment_w26.py -v
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py test/test_feature_detail_panel_w21.py test/test_operation_summary_w21.py test/test_notification_manager_w21.py -v
```

## Beweispflicht im Handoff
Du musst liefern:
1. Commit-Hash + Commit-Message.
2. Geänderte Dateien mit kurzem "warum".
3. Exakte Testresultate (Pass/Fail Zahlen).
4. Liste aller ersetzten schwachen Tests (z. B. reine `hasattr`) und deren neue Behavior-Variante.
5. Kurze Risikoliste (max 5 Punkte).

## Abgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeF_w26_followup_ultrahard.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Nächste 5 Aufgaben

