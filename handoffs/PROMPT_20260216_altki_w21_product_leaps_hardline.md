Du bist AI-2 (Product Surface Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst:
- `handoffs/HANDOFF_20260216_glm47_w18_recovery_closeout.md`
- `handoffs/PROMPT_20260216_glm47_w19_w20_unified_sprint.md`

Mission:
Liefer einen separaten Product-Leap in einem klar getrennten Bereich, damit
parallel echter Fortschritt entsteht.

-------------------------------------------------------------------------------
SEPARATION CONTRACT (STRICT)
-------------------------------------------------------------------------------
Du arbeitest NUR in diesem Bereich:
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/widgets/operation_summary.py`
- `gui/widgets/notification.py`
- `gui/managers/notification_manager.py`
- `gui/widgets/status_bar.py`
- neue Tests in `test/` fuer genau diese Bereiche
- optionale Doku in `handoffs/` und `roadmap_ctp/`

VERBOTEN (harte No-Go):
- `gui/sketch_editor.py`
- `gui/main_window.py`
- `gui/sketch_controller.py`
- `gui/feature_controller.py`
- `gui/export_controller.py`
- `gui/viewport/**`
- `modeling/**`
- `config/feature_flags.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`

Wenn eine verbotene Datei geaendert wird -> Lieferung automatisch FAIL.

-------------------------------------------------------------------------------
W21 HARDLINE PRODUCT LEAPS
-------------------------------------------------------------------------------
Gesamt: 40 Punkte
Akzeptanz:
- Minimum 20/40 (50%)
- Ziel 28+/40 (70%+)

Paket A (10 Punkte) Browser Power UX
1. Schnellfilter fuer Tree-Inhalte (z. B. all/warnings/errors/blocked).
2. Keyboard-first Browser Navigation (next/prev item + activate).
3. Sichtbare Status-Badges im Browser fuer Problemfeatures.
4. Kein visuelles Flackern bei Refresh/Filterwechsel.

Paket B (10 Punkte) Feature Detail Panel v2
1. Strukturierte Fehlerdiagnose (code/category/hint) klar lesbar.
2. "Copy diagnostics" Aktion fuer Support/Debug.
3. Kantenreferenzen mit robustem Invalid-Handling.
4. TNP-Sektion visuell priorisieren bei kritischen Fehlern.

Paket C (10 Punkte) Operation Summary History
1. Nicht nur Toast: letzte Operationen als History-Liste.
2. Pin/Unpin einer wichtigen Meldung.
3. Konsistente Farb-/Statuslogik zu Error UX v2.
4. Keine ueberlappenden Animationen im Burst-Fall.

Paket D (10 Punkte) Notification Robustness
1. Deduplication fuer identische Notifications in kurzem Zeitfenster.
2. Prioritaetsregeln (critical > error > blocked > warning > info) strikt.
3. Queue-Verhalten unter Last testbar und stabil.
4. Sichtbare Produktverbesserung, nicht nur interne Refactors.

-------------------------------------------------------------------------------
HARDLINE QUALITY RULES
-------------------------------------------------------------------------------
1. Kein test-only Delivery:
- Mindestens 70% der geaenderten Zeilen muessen in `gui/**` liegen.

2. Keine Entschuldigungs-Skips:
- In neu hinzugefuegten Tests sind `skip/xfail` verboten.

3. Keine "manuell verifiziert"-Luecken:
- Jeder zentrale Claim braucht automatisierten Proof.

4. Kein "DONE" bei roten Kernsuiten.

-------------------------------------------------------------------------------
VALIDIERUNG (PFLICHT)
-------------------------------------------------------------------------------
1) Bestehende relevante Suite:
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_error_ux_v2_integration.py -v
```

2) Neue W21 Suiten (von dir zu erstellen):
```powershell
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w21.py test/test_feature_detail_panel_w21.py test/test_operation_summary_w21.py test/test_notification_manager_w21.py -v
```

3) UI Gate (mandatory):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

4) Evidence:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate_gate_evidence.ps1 -OutPrefix roadmap_ctp/QA_EVIDENCE_W21_ALT_20260216
```

-------------------------------------------------------------------------------
RUECKGABEFORMAT (STRICT)
-------------------------------------------------------------------------------
Datei:
- `handoffs/HANDOFF_20260216_altki_w21_product_leaps_hardline.md`

Pflichtstruktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Delivery Scorecard
7. Claim-vs-Proof Matrix
8. Product Change Log (user-facing, Pflicht)
9. Offene Punkte + naechste 6 Aufgaben

-------------------------------------------------------------------------------
DELIVERY SCORECARD (PFLICHT)
-------------------------------------------------------------------------------
| Paket | Punkte | Status (DONE/PARTIAL/BLOCKED) | Proof |
|------|--------|---------------------------------|-------|
| A | 10 | ... | ... |
| B | 10 | ... | ... |
| C | 10 | ... | ... |
| D | 10 | ... | ... |
| Total | 40 | ... | ... |
| Completion Ratio | X/40 = YY% | MUST BE >= 50% | |

No-Go:
- Verbotene Datei geaendert
- Neue Tests mit skip/xfail
- Product-code Anteil < 70%
- UI Gate skipped
