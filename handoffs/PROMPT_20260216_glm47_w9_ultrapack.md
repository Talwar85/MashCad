Du bist GLM 4.7 (UX/WORKFLOW Cell) auf Branch `feature/v1-ux-aiB`.

Lies zuerst vollständig:
- `handoffs/HANDOFF_20260216_glm47_w8.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w10.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w11.md`
- `roadmap_ctp/DIRECT_MANIPULATION_CONTRACTS_W6_20260216.md`
- `roadmap_ctp/DISCOVERABILITY_WORKFLOW_W5_20260216.md`
- `roadmap_ctp/SELECTION_STATE_ANALYSIS_W5_20260216.md`
- `roadmap_ctp/CH010_REDFLAG_GATE_20260216.md`

Branch-Truth:
- `feature/v1-ux-aiB` ist die operative Wahrheit.

---

## Harte Regeln

1. Keine Core-Edits:
- `modeling/**`
- `config/**`

2. Fokus:
- `gui/**`
- `test/**` (UX/Harness/Gate-nahe Suiten)
- `scripts/gate_ui.ps1`, `scripts/gate_all.ps1`, `scripts/generate_gate_evidence.ps1`
- `roadmap_ctp/**` und `handoffs/**` (Evidenz + Contracts)

3. Kein Placebo:
- Kein reines Doku-Update ohne Code/Test-Repro.

4. Error UX Contract:
- `status_class`/`severity` immer zuerst.
- Legacy `code` nur fallback.

5. Skip-Disziplin:
- Kein neuer Skip ohne technisch präzise Signatur + konkrete Exit-Strategie.

---

## W9 Ultrapack Ziele

W9 soll drei Dinge gleichzeitig liefern:
1. Deutlich robustere Direct-Manipulation-Testbarkeit.
2. Vollständige Selection-State-Konsolidierung (ohne Legacy-Leaks).
3. Produktionsreife UX-Discoverability + Error UX Konsistenz in allen zentralen Oberflächen.

---

## Arbeitspakete (umfangreich, in Reihenfolge)

### Paket A (P0): Direct Manipulation Reliability & De-Flake Program

Ziel:
- Mindestens ein bisher geskipptes Drag-Szenario reproduzierbar stabil machen.

Aufgaben:
1. Erstelle in `test/harness/` robuste Hilfsfunktionen für:
   - viewport/editor readiness waits,
   - koordinatenstabile drag paths,
   - explizite flush/wait nach input events.
2. Refaktoriere `test/harness/test_interaction_consistency.py`:
   - gemeinsame helpers nutzen,
   - flake-sensitive Stellen isolieren.
3. Ent-skippe mindestens einen Drag-Test, wenn stabil.
4. Falls bestimmte Tests weiterhin skippen:
   - Signatur + Root-Cause + konkrete next action im Testreason dokumentieren.

Akzeptanz:
- Kein neuer FAIL im UI-Bundle.
- Mindestens ein objektiver Fortschritt in Flake-Reduktion (entskippt oder stabilere Infrastruktur).

---

### Paket B (P0): Selection-State Final Convergence

Ziel:
- Keine verstreuten Legacy-Pfade mehr für Face-Selection.

Aufgaben:
1. Audit von `gui/viewport_pyvista.py` auf direkte Legacy-Container-Manipulation.
2. Umbau auf Unified API:
   - `toggle_face_selection`
   - `clear_face_selection`
   - `clear_all_selection`
3. Erweitere Tests in `test/test_selection_state_unified.py` um:
   - multi-select lifecycle,
   - body-face marker consistency,
   - abort/escape clearing contract mit Unified API.

Akzeptanz:
- `test/test_selection_state_unified.py` bleibt vollständig grün.
- Kein regressives Verhalten in `test/test_ui_abort_logic.py`.

---

### Paket C (P1): Discoverability v3 Production Rollout

Ziel:
- Wichtige Bedienmodi müssen sichtbar und erlernbar sein (ohne Handbuch).

Aufgaben:
1. Verbesserte Sketch-Hints/HUD im 2D-Kontext:
   - Rotate-Hinweis,
   - Peek (Space halten),
   - kurzer Kontext-Hinweis bei Moduswechsel.
2. Hint-Spam vermeiden:
   - deduplizierte, zeitlich begrenzte Hinweise.
3. Tests:
   - bestehende UI-Abbruchtests anpassen/erweitern,
   - mindestens 1 dedizierter Test für Discoverability-Hinweislogik.

Akzeptanz:
- Hinweise sichtbar, aber nicht störend.
- Tests grün.

---

### Paket D (P1): Error UX v2 Complete Surface Coverage

Ziel:
- Einheitliche Fehlerdarstellung über Browser, Tooltip, Status-Feedback.

Aufgaben:
1. Alle relevanten UI-Renderpfade auf `status_class`/`severity` priorisieren.
2. `next_action` sichtbar machen, wenn vorhanden.
3. Tests in `test/test_browser_tooltip_formatting.py` erweitern:
   - WARNING_RECOVERABLE
   - BLOCKED
   - CRITICAL
   - ERROR
   - Legacy fallback
   - tnp_failure category bridging

Akzeptanz:
- Keine inkonsistente Klassifikation zwischen UI-Flächen.
- Tests vollständig grün.

---

### Paket E (P1): UI Gate Reliability & Evidence v3

Ziel:
- Merge-Entscheidungen auf belastbarem Gate-Output.

Aufgaben:
1. Prüfe `gate_ui.ps1`/`gate_all.ps1` auf konsistente Statusmeldungen.
2. Aktualisiere Evidence-Artefakte für W9:
   - klare PASS/BLOCKED_INFRA/FAIL Einordnung,
   - blocker signatures,
   - skip inventory.
3. Contract-Nachweise mit Repro-Commands liefern.

Akzeptanz:
- W9 Evidence vollständig, reproduzierbar, nicht widersprüchlich.

---

## Pflicht-Validierung

```powershell
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py
powershell -ExecutionPolicy Bypass -File scripts/gate_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/gate_all.ps1
```

Wenn ein Lauf fehlschlägt:
- Fehler-Signatur + betroffene Tests + mögliche Ursache + konkreter Fixpfad dokumentieren.

---

## Rückgabeformat

Datei:
- `handoffs/HANDOFF_20260216_glm47_w9.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Nächste 5 priorisierte Folgeaufgaben

Zusatz:
- ausfülltes W9 Review Template
- explizite Liste “Entskippt vs. weiterhin Skip”

---

## W9 Review Template (auszufüllen)

```markdown
# W9 Review Template (GLM47)

## Scope-Check
- [ ] Nur erlaubte Pfade editiert
- [ ] Kein Core-Kernel geändert

## Contract-Check
- [ ] status_class/severity zuerst
- [ ] Legacy fallback vorhanden
- [ ] Selection Unified API durchgängig
- [ ] Discoverability-Hints konsistent

## Test-Check
- [ ] UI-Bundle gelaufen
- [ ] Gate-Runner-Contract gelaufen
- [ ] gate_ui + gate_all gelaufen
- [ ] Skip-Inventar aktualisiert

## Entskip-Fortschritt
- Entskippt:
  - ...
- Verbleibend Skip:
  - ...

## Merge-Risiken
1. ...
2. ...
3. ...

## Empfehlung
- [ ] Ready for merge train
- [ ] Needs follow-up
Begründung: ...
```
