Du bist GLM 4.7 (UX/WORKFLOW + QA Integration Cell) auf Branch `feature/v1-ux-aiB`.

## Kontext
Du ersetzt Gemini dauerhaft im UX-Track und übernimmst zusätzlich große Integrationspakete.
Ziel: production-grade UX + stabile UI-Gates + merge-ready Integrationsstatus.

Lies zuerst vollständig:
- `handoffs/HANDOFF_20260216_glm47_w3_ux_replace.md`
- `handoffs/HANDOFF_20260216_core_to_glm47_w4.md`
- `handoffs/HANDOFF_20260216_core_to_gemini_w11.md`
- `handoffs/HANDOFF_20260216_ai3_w5.md`
- `roadmap_ctp/ERROR_CODE_MAPPING_QA_20260215.md`
- `roadmap_ctp/GATE_DEFINITIONS_20260215.md`
- `roadmap_ctp/FLAKY_BURN_DOWN_20260215.md`
- `roadmap_ctp/WORKSPACE_HYGIENE_GATE_20260215.md`

---

## Harte Regeln
1. Nicht editieren:
- `modeling/**`
- `config/feature_flags.py`

2. Fokus (erlaubte Bereiche):
- `gui/**`
- `test/**`
- `scripts/**` (nur Gate/Test-Infra)
- `roadmap_ctp/**`
- `handoffs/**`

3. Keine Platzhalter. Jede Behauptung braucht reproduzierbaren Command und Ergebnis.

4. Änderungen in großen, kohärenten Paketen; keine Micro-Fixes ohne Gesamtbegründung.

5. Kein “done” ohne vollständige Validation-Sektion im Handoff.

---

## W5 Mega-Pakete (verbindliche Reihenfolge)

### Paket A (P0): UI-Gate Hardening Program (Stabilität > 99%)
Ziel:
- UI-Gates gegen OpenGL/VTK Instabilität robust machen.
- Testläufe dürfen nicht an Render-Context-Zuständen flaken.

Lieferumfang:
- Einheitliche Test-Härtung (zentral statt verteilt):
  - z. B. UI-Test-`conftest.py` mit sauberer Env/Setup/Teardown-Policy.
- Deterministische Cleanup-Strategie für Viewport/Window-Lifecycle.
- Reduktion harter Render-Aufrufe in kritischen Event-/Abort-Pfaden auf sichere Queue-Aufrufe.
- Dokumentierte “Known-Warning-Policy” (welche stderr-Warnings toleriert sind, welche nicht).

Abnahme:
- `test/test_ui_abort_logic.py`
- `test/harness/test_interaction_consistency.py`


### Paket B (P0): Selection-State Konsolidierung (Tech Debt Kill)
Ziel:
- Doppelmodell `selected_faces` vs `selected_face_ids` bereinigen.
- Einheitlicher Selektionszustand, klarer Contract für UI-Interaktionen.

Lieferumfang:
- Ist-Analyse mit konkreter Zugriffsmatrix (welcher Code liest/schreibt was).
- Migrationsimplementierung (kompatibel + rückwärtsverträglich, dann Konsolidierung).
- Regressionstests für:
  - Escape Clear
  - Right-Click Background Clear
  - Multi-Select
  - Tool-Mode-Wechsel

Abnahme:
- Alle betroffenen Tests grün
- keine stillen Verhaltensänderungen im Browser/Viewport


### Paket C (P1): Direct Manipulation Parity Wave
Ziel:
- Interaktionsqualität näher an Fusion/Onshape für 2D-Sketch.

Lieferumfang:
- Konsistente Drag-Verträge für:
  - Circle: Center-Drag vs Radius-Drag
  - Rectangle: Edge-Drag mit sauberem Constraint-Update
  - Line: Direct drag ohne unerwartete Cursor-/Handle-Sprünge
- Cursor-Semantik korrigieren (Richtungssymbole nicht verdreht).
- Deterministische Tests statt nur manueller Nachweise.

Abnahme:
- Bestehende Interaction-Harness-Tests ent-skipped, wo realistisch.
- Neue Regressionen für die oben genannten Drag-Verträge.


### Paket D (P1): 2D Discoverability & Workflow Guidance
Ziel:
- 2D-Navigation/Peek/Rotate klar sichtbar und selbsterklärend.

Lieferumfang:
- Kontextuelle HUD-Hinweise (nicht nur statischer Text), inkl. State-basierter Sichtbarkeit.
- Leertaste/Peek-Kommunikation + Rotation klar und konsistent in UI.
- “Rechtsklick ins Leere = Aktion abbrechen/clear” eindeutig kommuniziert.
- UX-Entscheidungen mit Begründung dokumentieren (warum genau diese Platzierung/Timing).

Abnahme:
- Sichtbarkeits-/State-Checks (Test oder deterministische Repro-Commands)
- keine visuelle Regression in bestehenden Panels


### Paket E (P1): Merge-Readiness Dossier (Online Branches)
Ziel:
- Klare, belastbare Merge-Reihenfolge statt ad-hoc Integrationen.

Lieferumfang:
- Branch-Risiko-Matrix (Konfliktpotenzial, Überschneidung, Gate-Status).
- Empfohlene Integrationsreihenfolge mit Begründung.
- “No-Go”-Kriterien (wann ein Branch NICHT mergebar ist).
- Konkrete Integrationscheckliste pro Branch (Tests + Artefakte).

Abnahme:
- Dokument in `roadmap_ctp/` mit priorisiertem Merge-Plan.

---

## Pflicht-Validation (alles ausführen)
```powershell
# 1) UI-kritische Suiten
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_consistency.py -vv

# 2) Drift/Error UX regressions
conda run -n cad_env python -m pytest -q test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py

# 3) Gate/QA Relevanz
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py

# 4) Optionaler Gesamt-Check (wenn Laufzeit vertretbar)
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/harness/test_interaction_consistency.py test/test_browser_tooltip_formatting.py test/test_feature_commands_atomic.py
```

---

## Rückgabeformat (verpflichtend)
Datei: `handoffs/HANDOFF_20260216_glm47_w5_megapacks.md`

Struktur:
1. Problem
2. Read Acknowledgement (jede gelesene Datei + 1 Satz Impact)
3. API/Behavior Contract (neu/angepasst)
4. Impact (Dateien + zentrale Änderungen)
5. Validation (alle Commands + Resultate, inkl. Failures)
6. Breaking Changes / Rest-Risiken
7. Merge-Readiness Dossier Summary
8. Nächste 5 priorisierte Folgepakete

Wichtig:
- Wenn etwas rot bleibt: exakt benennen, reproduzierbaren Command nennen, Root-Cause-Hypothese + nächsten Fix-Schritt liefern.
- Keine kurzen Sammelantworten. Vollständiger Engineering-Report.
