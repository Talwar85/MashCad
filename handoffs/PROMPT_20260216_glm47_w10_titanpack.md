Du bist GLM 4.7 (UX/WORKFLOW Cell) auf Branch `feature/v1-ux-aiB`.

Pflichtlektüre (vollständig):
- `handoffs/HANDOFF_20260216_glm47_w9.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w11.md`
- `roadmap_ctp/DIRECT_MANIPULATION_CONTRACTS_W6_20260216.md`
- `roadmap_ctp/DISCOVERABILITY_WORKFLOW_W5_20260216.md`
- `roadmap_ctp/SELECTION_STATE_ANALYSIS_W5_20260216.md`
- `roadmap_ctp/STABILITY_DASHBOARD_SEED_W7_20260216.md`

Branch-Truth:
- `feature/v1-ux-aiB` ist die operative Wahrheit.

---

## Harte Regeln

1. Keine Core-Kernel-Edits:
- `modeling/**`
- `config/**`

2. Fokus:
- `gui/**`
- `test/**` (UI/Harness/UX/Gate-bezogen)
- `scripts/gate_ui.ps1`, `scripts/gate_all.ps1`, `scripts/generate_gate_evidence.ps1`
- `handoffs/**`, `roadmap_ctp/**` (Evidenz/Verträge)

3. Keine Placebo-Arbeit:
- Keine reine Doku ohne Code+Tests.

4. Error UX v2 ist verpflichtend:
- `status_class` + `severity` priorisiert, `code` nur fallback.

5. Skip-Disziplin:
- Kein neuer Skip ohne technische Signatur + Exit-Strategie.

---

## W10 Titanpack Ziele

W10 soll ein langer, substanzieller UX-Baustein sein mit drei Schwerpunkten:
1. Direct manipulation testability deutlich erhöhen (entskippen, nicht nur kommentieren).
2. Error UX v2 vollständig in der Oberfläche verdrahten (nicht nur Tooltip/Statusbar isoliert).
3. UI-Gate und Evidence auf Release-Niveau stabilisieren.

---

## Arbeitspakete (groß, in Reihenfolge)

### Paket A (P0): Direct Manipulation Entskip Program v2

Ziel:
- Von den 3 geskippten Drag-Tests mindestens 2 stabil entskippen (wenn technisch möglich).

Aufgaben:
1. Refaktorisiere `test/harness/test_interaction_consistency.py` weiter:
   - zentralisierte coordinate mapping adapter,
   - deterministic drag paths,
   - explicit viewport/editor readiness sync.
2. Prüfe, ob viewport/state hooks ergänzt werden müssen (ohne Core-Änderungen), um Testdeterminismus zu erhöhen.
3. Ent-skippe mindestens 2 Tests oder dokumentiere sauber, warum exakt nur 1/0 möglich war.
4. Liefere eine kleine Matrix in der Doku:
   - Testname, alter Skip-Status, neuer Status, technische Ursache bei Rest-Skip.

Akzeptanz:
- Kein neuer FAIL im UI-Bundle.
- Entskip-Fortschritt klar messbar.

---

### Paket B (P0): Error UX v2 End-to-End Wiring

Ziel:
- `status_class`/`severity` überall dort nutzen, wo UI-Status dargestellt wird.

Aufgaben:
1. Audit in `gui/**`: alle Statusdarstellungen erfassen (Status-Bar, Browser, Panels, Notifications, ggf. Tooltips).
2. Wo noch legacy (`is_error`/Text-only) dominiert:
   - v2-Felder priorisieren,
   - legacy fallback beibehalten.
3. Ergänze Tests:
   - bestehende Tooltip-/Status-Tests erweitern,
   - mindestens 1 Integrationstest, der mehrere UI-Flächen im selben Fehlerfall prüft.

Akzeptanz:
- Keine widersprüchliche Statusdarstellung mehr zwischen UI-Komponenten.

---

### Paket C (P1): Discoverability v4 Anti-Spam + Context Sequencing

Ziel:
- Hinweise helfen, aber nerven nicht.

Aufgaben:
1. Hint-Sequencing-Logik verbessern:
   - dedup pro Kontext,
   - cooldown,
   - priorisierte Hinweisreihenfolge (Navigation/Peek/Tool).
2. “Rapid hint churn” robust machen (kein Flackern/Spam).
3. Tests in `test/test_discoverability_hints.py` erweitern:
   - cooldown contract,
   - priority override,
   - no-repeat within window.

Akzeptanz:
- Hints bleiben informativ, reproduzierbar und ruhig.

---

### Paket D (P1): Selection-State Hard Finalization

Ziel:
- Legacy-Leaks in Selection-Handling endgültig schließen.

Aufgaben:
1. Audit `gui/viewport_pyvista.py` + verwandte Komponenten auf direkte Legacy-Containerzugriffe.
2. Nur Unified API verwenden (sofern möglich):
   - `toggle_face_selection`
   - `clear_face_selection`
   - `clear_all_selection`
3. Regressionen in `test/test_selection_state_unified.py` erweitern:
   - kombiniertes lifecycle scenario (tool switch + abort + reselect),
   - multi-select edge cases.

Akzeptanz:
- Selection-State konsistent und regressionssicher.

---

### Paket E (P1): UI Gate + Evidence v4

Ziel:
- Gate-Evidenz belastbar und release-tauglich.

Aufgaben:
1. `gate_ui.ps1`/`gate_all.ps1` Output auf klare, maschinenlesbare Felder trimmen (ohne bestehende Contracts zu brechen).
2. `generate_gate_evidence.ps1` auf W10-UI-Suite aktualisieren.
3. W10 Evidence-Artefakt liefern:
   - test counts,
   - skips,
   - blocker signatures,
   - Vergleich zu W9.

Akzeptanz:
- Keine widersprüchlichen Gate-Aussagen zwischen Script-Output und Handoff.

---

## Pflicht-Validierung

```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_discoverability_hints.py test/test_feature_commands_atomic.py
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/gate_all.ps1 -EnforceCoreBudget
```

Wenn ein Lauf fehlschlägt:
- Signatur, Root-Cause, betroffene Tests, konkreter Fixpfad dokumentieren.

---

## Rückgabeformat (Pflicht)

Datei:
- `handoffs/HANDOFF_20260216_glm47_w10.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Nächste 5 priorisierte Folgeaufgaben
7. Entskip-Matrix (vorher/nachher)

---

## W10 Review Template (auszufüllen)

```markdown
# W10 Review Template (GLM47)

## Scope-Check
- [ ] Nur erlaubte Pfade editiert
- [ ] Kein Core-Kernel geändert

## Contract-Check
- [ ] status_class/severity priorisiert
- [ ] Legacy fallback vorhanden
- [ ] Selection Unified API konsistent
- [ ] Discoverability anti-spam contracts aktiv

## Test-Check
- [ ] UI bundle gelaufen
- [ ] Gate-runner-contract gelaufen
- [ ] gate_ui gelaufen
- [ ] gate_all -EnforceCoreBudget gelaufen

## Entskip-Matrix
- Test:
  - Vorher:
  - Nachher:
  - Begründung:

## Merge-Risiken
1. ...
2. ...
3. ...

## Empfehlung
- [ ] Ready for merge train
- [ ] Needs follow-up
Begründung: ...
```
