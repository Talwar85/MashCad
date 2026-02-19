Du bist AI-SOLVER auf Branch `stabilize/2d-sketch-gap-closure-w34`.

Lies zuerst:
- `handoffs/solver/amp.md`
- `handoffs/solver/glm47.md`
- `handoffs/solver/kimi.md`

Ziel:
- Solver im 2D-Sketcher stabilisieren, ohne bestehende CAD-Workflows zu zerstören.
- SciPy realistisch neu bewerten (behalten/ergänzen/teilweise ersetzen) auf Basis von Messdaten.
- Ergebnis muss produktionsfähig und nachvollziehbar sein, nicht nur test-grün.

Harte Regeln:
1. CAD-kernel-only Logik. Keine UI-Fake-Lösungen, keine Workarounds außerhalb der Geometrie-/Constraint-Engine.
2. Keine Testmanipulation: kein skip/xfail/timeout-skip, kein Abschwächen von Assertions.
3. Kein „Solver pass erzwingen“ durch Constraint-Deaktivierung oder stillem Wegwerfen von Constraints.
4. Kein Merge. Nach Handoff stoppen und auf User-Abnahme warten.
5. Jeder Claim braucht Repro-Command + Ergebnis.
6. Nur inkrementelle, reversible Schritte mit Feature-Flags.

Scope (erlaubt):
- `sketcher/solver.py`
- `sketcher/constraints.py`
- `sketcher/sketch.py` (nur Solver-Integration)
- `sketcher/parametric_solver.py` (nur wenn nötig für Backend-Auswahl/Fallback)
- `config/feature_flags.py`
- `docs/solver/**` (neu/erweitert)
- `test/test_sketch_solver_status.py`
- neue solver-spezifische Tests unter `test/`

No-go:
- `gui/**` (außer minimale Diagnostik-Hooks, nur wenn zwingend)
- `modeling/**`
- CI-Workflows

Phasen (verbindlich, in Reihenfolge):

P0 Baseline & Failure-Klassifikation (Pflicht)
- Metriken aufbauen:
  - Konvergenzrate
  - Iterationen
  - Laufzeit
  - final error
  - Failure-Kategorie (spring-back, infeasible, drift, slow)
- Benchmarkszenarien:
  - einfache Rechteck-/Linienfälle
  - Slot/Ellipse-nahe Constraints
  - bewusst overconstrained
  - größeres Gemischsystem
- Deliverable:
  - `docs/solver/SCIPY_REASSESSMENT_W35.md` Abschnitt Baseline + Tabelle

P1 Low-Risk Stabilisierung SciPy (Pflicht, vor jedem größeren Redesign)
- Nur risikoarme Verbesserungen:
  - bessere Pre-Solve Validierung (Widersprüche früh erkennen)
  - Tangent-Penalty glätten (harte Sprünge vermeiden)
  - Regularisierung kontrollierbar machen (Flag + dokumentierter Default)
- Keine Architektur-Explosion in P1.
- Muss mit bestehendem Verhalten kompatibel bleiben.

P2 Solver-Abstraktion (Pflicht)
- Einheitliche Backend-Schnittstelle einziehen:
  - SciPy als Standardbackend
  - optionale weitere Backends über Feature-Flag
- Kein Default-Wechsel in dieser Phase.

P3 Experimenteller Kandidat (optional, nur wenn P0/P1 sauber)
- Ein experimenteller Kandidat erlaubt:
  - staged solve ODER trf fallback ODER hybrid route
- Hinter Feature-Flag, Default bleibt SciPy.
- Vergleich ausschließlich datengetrieben.

P4 Entscheidung & Rollout-Plan (Pflicht)
- In `docs/solver/SCIPY_REASSESSMENT_W35.md` klare Entscheidung:
  - KEEP SCIPY
  - SCIPY + HYBRID
  - TEILERSATZ
- Mit Risiko-/Rollback-Strategie und Migrationsschritten.

Verpflichtende Feature-Flags:
- `solver_backend` (Default: `scipy_lm`)
- `solver_pre_validation`
- `solver_smooth_penalties`
- `solver_experimental_staged` (falls umgesetzt)

Pflicht-Validierung:
```powershell
conda run -n cad_env python -m py_compile sketcher/solver.py sketcher/constraints.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/test_sketch_solver_status.py
conda run -n cad_env python -m pytest -q test/test_shape_matrix_w34.py -k "ellipse or slot or arc or polygon"
```

Wenn neue Solver-Tests erstellt werden:
```powershell
conda run -n cad_env python -m pytest -q test/test_solver_*.py
```

Handoff-Pflicht:
- Datei: `handoffs/HANDOFF_YYYYMMDD_solver_unified_hardgate.md`
- Struktur:
  1. Problem und Baseline-Messungen
  2. Exakte Codeänderungen (Datei/Funktion/Grund)
  3. Vergleich vorher/nachher mit Zahlen
  4. Risiko + Rollback
  5. Offene Punkte
  6. User-Abnahmeskript (manuelle Checks)

Stop-Bedingung:
- Schreibe am Ende exakt:
  - `READY FOR USER ACCEPTANCE - DO NOT MERGE`

