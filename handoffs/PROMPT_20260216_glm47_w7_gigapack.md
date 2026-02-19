Du bist GLM 4.7 (UX/WORKFLOW + QA Integration Cell) auf Branch `feature/v1-ux-aiB`.

## Mission W7 (GIGAPACK)
W7 ist ein grosses zusammenhaengendes Produktionspaket. Ziel ist nicht nur Bugfixing,
sondern eine belastbare UX- und Testbasis fuer V1 ohne halbfertige Reststellen.

Lies zuerst komplett:
- `handoffs/HANDOFF_20260216_glm47_w6.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w7.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w6.md`
- `handoffs/HANDOFF_20260216_ai3_w5.md`
- `roadmap_ctp/DIRECT_MANIPULATION_CONTRACTS_W6_20260216.md`
- `roadmap_ctp/DISCOVERABILITY_WORKFLOW_W5_20260216.md`
- `roadmap_ctp/SELECTION_STATE_ANALYSIS_W5_20260216.md`
- `roadmap_ctp/UI_GATE_KNOWN_WARNINGS_W5_20260216.md`
- `roadmap_ctp/GATE_DEFINITIONS_20260215.md`

---

## Harte Regeln
1. Nicht editieren:
- `modeling/**`
- `config/feature_flags.py`

2. Erlaubte Bereiche:
- `gui/**`
- `test/**`
- `scripts/**` (nur UI/Gate/Test-Infra)
- `roadmap_ctp/**`
- `handoffs/**`

3. Keine Micro-Commits und keine lose Einzelkorrekturen.
Nur zusammenhaengende W7-Lieferpakete mit klarer Wirkung.

4. Keine "done"-Aussage ohne reproduzierbare Validation-Commands.

5. Core-Envelope ist ab W7 erweitert:
- `status_details.status_class`
- `status_details.severity`
Diese Felder muessen in UX bewusst konsumiert werden.

---

## W7 GIGAPACK (verbindliche Reihenfolge)

### Paket A (P0): Direct Manipulation Determinism Program
Ziel:
- Drag-Vertraege Circle/Rectangle/Line nicht nur visuell, sondern testbar-deterministisch machen.

Lieferumfang:
- Event-/Coordinate-Layer so haerten, dass Kern-Drag-Pfade reproduzierbar sind.
- Interaction-Harness modernisieren:
  - reduzierte Skip-Rate bei Drag-Tests,
  - klare Marker fuer echte Infra-Blocker vs Logikfehler.
- Cursor-Semantik finalisieren:
  - keine widerspruechlichen Cursorwechsel bei Hover->Drag->Drop.

Abnahme:
- `test/harness/test_interaction_consistency.py`
- neue/erweiterte Drag-Regressionen fuer Circle/Rectangle/Line


### Paket B (P0): Selection State Full Migration
Ziel:
- Legacy-Selektion technisch abschliessen (Bridge nur noch fuer Kompatibilitaet, nicht als aktive Schreibquelle).

Lieferumfang:
- Alle aktiven GUI-Zugriffe auf Unified API konsolidieren.
- Legacy-Zugriffe (`selected_faces`, `selected_edges`) nur noch als Wrapper lesen/schreiben,
  keine neue Kernlogik mehr darueber.
- Regressionen fuer:
  - Escape clear
  - right-click background clear
  - multi-select
  - mode/tool switch

Abnahme:
- `test/test_selection_state_unified.py`
- keine Verhaltensregression in Browser/Viewport


### Paket C (P0): Error UX Contract v2 (status_class + severity)
Ziel:
- UI soll nicht mehr implizit raten, sondern Core-Klassifikation direkt nutzen.

Lieferumfang:
- Browser Tooltip, Status-Panels und relevante UI-Hinweise auf `status_class`/`severity` umstellen.
- Mapping-Regeln:
  - `WARNING_RECOVERABLE` -> recoverable warning visual
  - `BLOCKED` -> blocked visual (keine generische "Error"-Darbietung)
  - `CRITICAL` -> klare kritische Eskalation
  - `ERROR` -> standard error
- Fallback nur, wenn neue Felder fehlen (Backward-Compat).

Abnahme:
- `test/test_browser_tooltip_formatting.py`
- ggf. Panel-spezifische Regressionen
- Drift (`tnp_ref_drift`) weiterhin recoverable


### Paket D (P1): Discoverability System v2 (state-driven UX)
Ziel:
- 2D-Guidance als konsistentes, state-basiertes System statt einzelner Hinweise.

Lieferumfang:
- Einheitliche Anzeige-Policy fuer:
  - Peek (Space halten)
  - Rotation
  - Rechtsklick-Abbruch
- Zeitliche/kontextuelle Regeln dokumentieren (wann zeigen, wann nicht).
- Reduktion von Hint-Noise bei power-user Flows.

Abnahme:
- deterministische Repro-Checks oder Tests fuer Sichtbarkeitszustand
- keine visuelle Regression in bestehenden Panels


### Paket E (P1): UI Gate Reliability v2 + Evidence
Ziel:
- UI-Gate als belastbarer Release-Indikator weiterhaerten.

Lieferumfang:
- Test-Infra weiter robust machen, ohne echte Fehler zu maskieren.
- BLOCKED_INFRA vs FAIL im Report eindeutig.
- Known-Warnings policy aktualisieren (was toleriert wird, was nicht).
- W7 Evidence aktualisieren (MD + JSON, falls im Prozess vorgesehen).

Abnahme:
- `test/test_ui_abort_logic.py`
- `test/harness/test_interaction_consistency.py`
- `test/test_gate_runner_contract.py`


### Paket F (P1): Merge-Ready UX Dossier W7
Ziel:
- Nach W7 muss klar sein, was mergebar ist und was Rest-Risiko bleibt.

Lieferumfang:
- W7 Delta gegen W6 fuer UX/Tests/Risiken.
- Klare No-Go-Kriterien fuer UI-Merge.
- Priorisierte Folgepakete mit Owner+ETA.

Abnahme:
- dokumentierte W7-Zusammenfassung in `roadmap_ctp/` + Handoff

---

## Pflicht-Validation (vollstaendig)
```powershell
# 1) UI Kernsuiten
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -vv

# 2) Selection + Error UX
conda run -n cad_env python -m pytest -q test/test_selection_state_unified.py
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py

# 3) Gate Contract
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py

# 4) Optional gebuendelter Lauf
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_selection_state_unified.py test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py test/test_gate_runner_contract.py
```

---

## Rueckgabeformat (verpflichtend)
Datei: `handoffs/HANDOFF_20260216_glm47_w7_gigapack.md`

Struktur:
1. Problem
2. Read acknowledgement (jede gelesene Datei + Impact)
3. API/Behavior Contract (neu/geaendert/entfaellt)
4. Impact (Dateien + Kernveraenderungen)
5. Validation (alle Commands + exakte Resultate)
6. Breaking changes / Rest-Risiken
7. W6 -> W7 Delta (UX + Gates)
8. Naechste 5 priorisierte Folgepakete (Owner + ETA)

Wichtig:
- Keine Kurzantworten.
- Bei Rot/Skip: Repro + Root-Cause-Hypothese + naechster Fixschritt.
- Status immer evidenzbasiert, keine Annahmen.
