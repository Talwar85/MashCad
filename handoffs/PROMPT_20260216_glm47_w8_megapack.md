Du bist GLM 4.7 (UX/WORKFLOW Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst (Pflicht):
- `handoffs/HANDOFF_20260216_glm47_w7_gigapack.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w9.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w10.md`
- `roadmap_ctp/DIRECT_MANIPULATION_CONTRACTS_W6_20260216.md`
- `roadmap_ctp/DISCOVERABILITY_WORKFLOW_W5_20260216.md`
- `roadmap_ctp/SELECTION_STATE_ANALYSIS_W5_20260216.md`
- `roadmap_ctp/CH010_REDFLAG_GATE_20260216.md`

Branch-Truth:
- `feature/v1-ux-aiB` ist die operative Wahrheit.

---

## Harte Regeln

1. Keine Edits in Core-Kernel:
- `modeling/**`
- `config/feature_flags.py`

2. Fokusbereich UX/Workflow/Tests:
- `gui/**`
- `test/**` (nur UX-/Harness-/Gate-nahe Tests)
- `scripts/gate_ui.ps1`, `scripts/gate_all.ps1`, `scripts/generate_gate_evidence.ps1` (falls UI-Gate-Output betroffen)
- `roadmap_ctp/**` (nur UX/QA Doku-Updates)

3. Keine Placeholders:
- Jede Aussage braucht reproduzierbaren Command oder klaren Codebeleg.

4. Vertragsdisziplin:
- `status_class`/`severity` aus Envelope v2 sind Primärquelle.
- Legacy `code` bleibt nur Fallback.

5. Kein stilles Abschalten von Tests:
- Keine neuen globalen `skip` ohne konkrete Root-Cause-Notiz und Gegenmaßnahme.

---

## Ziel von W8 (Megapack)

W8 soll die W7-Basis in einen merge-reifen Zustand bringen, indem:
- Direct Manipulation robuster testbar wird,
- Selection-State technisch konsistent finalisiert wird,
- Discoverability in 2D klar sichtbar wird,
- Error UX v2 in allen zentralen UX-Flächen konsistent ankommt,
- UI-Gate-Berichte belastbar und merge-tauglich sind.

---

## Arbeitspakete (in Reihenfolge)

### Paket A (P0): Direct Manipulation Test De-Flake / Repro-Hardening

Ziel:
- `test/harness/test_interaction_consistency.py` stabilisieren, ohne die Produktlogik weichzuspülen.

Aufgaben:
1. Analysiere die drei aktuell geskippten Drag-Tests auf reproduzierbare Flake-Ursachen (Koordinaten-Mapping, Event-Timing, Fokus).
2. Ergänze robuste Test-Helfer (z. B. deterministische coordinate transforms, explizite waits auf editor state).
3. Ent-skippe mindestens **einen** der drei Tests, wenn reproduzierbar stabil.
4. Falls Ent-Skip nicht stabil machbar: dokumentiere präzise Blocker-Signatur + Mitigation und halte Skip-Texte auf technischem Niveau.

Akzeptanz:
- Keine neuen FAILs im UI-Bundle.
- Wenn Skip verbleibt, dann mit präziser Signatur + Next Action.

---

### Paket B (P0): Selection-State Vollmigration (Finalisierung)

Ziel:
- Single Source of Truth für Face-Selection endgültig durchziehen.

Aufgaben:
1. Entferne direkte Schreibzugriffe auf Legacy-Selection-Container in `gui/viewport_pyvista.py`, wo Unified API vorhanden ist.
2. Vereinheitliche Clear-/Toggle-Pfade (`clear_all_selection`, `clear_face_selection`, `toggle_face_selection`) ohne Seiteneffekte.
3. Ergänze Regressionen in `test/test_selection_state_unified.py` für:
   - background click clear,
   - multi-select toggle,
   - body-face special marker contracts.

Akzeptanz:
- `test/test_selection_state_unified.py` bleibt grün.
- Kein Regressionseintrag in Interaction-Suite.

---

### Paket C (P1): Discoverability v3 (2D Bedienhinweise sichtbar und konsistent)

Ziel:
- In 2D muss klar erkennbar sein: Rotieren möglich, Peek via Space.

Aufgaben:
1. Sichtbare HUD-/Hint-Mechanik in Sketch-Mode schärfen:
   - kurzer, nicht-intrusiver Hinweis bei Mode-Entry,
   - Hinweis auf Space/Peek,
   - Hinweis auf Rotate-Navigation.
2. Rechtsklick-Abbruch/HUD-Konsistenz gegen bestehende Escape-Logik prüfen und vereinheitlichen.
3. Ergänze/aktualisiere Tests (`test/test_ui_abort_logic.py` + ggf. neue schlanke discoverability tests).

Akzeptanz:
- Hinweise erscheinen kontextsensitiv, nicht spammy.
- UI-Abbruchtests bleiben grün.

---

### Paket D (P1): Error UX v2 Rollout Konsistenz

Ziel:
- `status_class`/`severity` müssen UX-seitig konsistent gerendert werden.

Aufgaben:
1. Prüfe alle relevanten UI-Flächen (Browser/Tooltip/Statusanzeige) auf v2-Priorisierung.
2. Stelle sicher, dass `next_action` bei Fehlern mit angezeigt wird, falls vorhanden.
3. Ergänze Tests in `test/test_browser_tooltip_formatting.py`:
   - `WARNING_RECOVERABLE`
   - `BLOCKED`
   - `CRITICAL`
   - Legacy fallback ohne status_class

Akzeptanz:
- Tooltips/Labels eindeutig, regressionssicher.

---

### Paket E (P1): UI-Gate Reliability Evidence v2

Ziel:
- Merge-Entscheidungen sollen auf reproduzierbarer Evidenz basieren.

Aufgaben:
1. Führe vollständiges UI-Bundle aus und dokumentiere Ist-Status.
2. Aktualisiere W8-Doku mit:
   - PASS/FAIL/BLOCKED_INFRA Klassifikation,
   - verbleibende Skips inkl. Ursache,
   - konkrete de-flake next actions.
3. Prüfe Gate-Runner Output-Schema weiterhin gegen Contract.

Akzeptanz:
- W8-Evidence dokumentiert, nicht nur behauptet.

---

## Pflicht-Validierung

```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
```

Wenn ein Command fehlschlägt:
- Fehlerbild mit Signatur dokumentieren,
- kein "works on my machine" ohne Repro.

---

## Rückgabeformat (Pflicht)

Datei:
- `handoffs/HANDOFF_20260216_glm47_w8.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Nächste 5 priorisierte Folgeaufgaben

---

## W8 Review Template (ausfüllen)

```markdown
# W8 Review Template (GLM47)

## Scope-Check
- [ ] Nur erlaubte Pfade editiert
- [ ] Kein Core-Kernel geändert

## Contract-Check
- [ ] status_class/severity zuerst
- [ ] Legacy code fallback vorhanden
- [ ] Selection Unified API durchgängig genutzt

## Test-Check
- [ ] UI-Bundle gelaufen
- [ ] Gate-Runner-Contract gelaufen
- [ ] Skip-Liste aktualisiert (mit Ursache)

## Merge-Risiken
1. ...
2. ...
3. ...

## Empfehlung
- [ ] Ready for merge train
- [ ] Needs follow-up
Begründung: ...
```
