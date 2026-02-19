# W35 Solver SciPy Reassessment — Plan

> **Erstellt:** 19.02.2026
> **Quelle:** `handoffs/PROMPT_20260219_ai_largeBH_w35_solver_scipy_reassessment.md`
> **Status:** PLAN — noch nicht umgesetzt
> **Branch:** `stabilize/2d-sketch-gap-closure-w34`

---

## 1. Aktueller Solver-Stand

### Architektur

- **Backend:** SciPy `least_squares` mit Levenberg-Marquardt (`method='lm'`)
- **Dateien:** `sketcher/solver.py` (~393 Zeilen), `sketcher/constraints.py` (~754 Zeilen)
- **Constraint-Typen:** 20 (FIXED, COINCIDENT, POINT_ON_LINE, POINT_ON_CIRCLE, HORIZONTAL, VERTICAL, PARALLEL, PERPENDICULAR, COLLINEAR, EQUAL_LENGTH, CONCENTRIC, EQUAL_RADIUS, TANGENT, DISTANCE, LENGTH, ANGLE, RADIUS, DIAMETER, SYMMETRIC, MIDPOINT)
- **Prioritäts-System:** 4 Stufen (CRITICAL=100, HIGH=50, MEDIUM=25, LOW=15)
- **Regularisierung:** `0.01` — zieht Lösung zu Startwerten
- **Konvergenz-Kriterien:** `ftol=1e-8, xtol=1e-8, gtol=1e-8, max_nfev=1000`
- **Erfolgs-Schwellen:** Gesamtfehler < 1e-3, Max-Einzelfehler < 1e-2
- **Rollback:** Bei Nicht-Konvergenz werden Original-Werte wiederhergestellt
- **Batch-Berechnung:** Vectorized Residuen für häufige Constraint-Typen (COINCIDENT, HORIZONTAL, VERTICAL, LENGTH, EQUAL_LENGTH, RADIUS)
- **Tests:** 14/14 bestehen ✅

### Stärken

1. Rollback-Mechanismus verhindert Geometrie-Drift bei Solver-Fehlern
2. Prioritäts-Gewichtung sorgt für korrekte Reihenfolge (topologisch > geometrisch > dimensional)
3. Batch-Berechnung bringt 70-85% Performance-Gewinn bei Residuen
4. Saubere `SolverResult`-Datenklasse mit Status-Enum

---

## 2. Bekannte Schwächen / Failure Modes

| # | Failure Mode | Ursache | Risiko | Betroffene Szenarien |
|---|---|---|---|---|
| F1 | **Spring-back** | Regularisierung (`0.01`) zieht Lösung zu Startwerten zurück | Mittel | Direct-Edit mit großem Drag-Delta |
| F2 | **Overconstrained false positive** | Heuristik `n_effective_constraints > n_vars` ignoriert abhängige/redundante Constraints | Mittel | Polygon + POINT_ON_CIRCLE, Rectangle + COINCIDENT |
| F3 | **Tangent arc_penalty Sprung** | `arc_penalty = 100.0` ist ein harter Sprung statt smooth penalty → kann Solver-Gradient verwirren | Mittel | Arc-Tangent Constraints |
| F4 | **Unnötige Variablen** | FIXED/HORIZONTAL/VERTICAL erzeugen Solver-Variablen, obwohl sie trivial lösbar sind | Niedrig | Große Sketches mit vielen trivialen Constraints |
| F5 | **Keine Jacobian-Matrix** | LM ohne expliziten Jacobian → numerische Differenzierung (langsamer, weniger stabil) | Niedrig | Große Constraint-Systeme (>50 Variablen) |

---

## 3. Work Packages

### WP1: Baseline-Analyse (~2h)

**Ziel:** Failure Modes klassifizieren und aktuelle Performance messen.

**Szenarien:**
1. Einfaches Rechteck (4 Linien, COINCIDENT + HORIZONTAL + VERTICAL)
2. Polygon (6-Eck, POINT_ON_CIRCLE × 6)
3. Tangent-Chain (3 Kreise tangential verbunden)
4. Overconstrained (Rectangle + redundante EQUAL_LENGTH)
5. Direct-Edit Spring-back (Polygon-Vertex Drag mit großem Delta)
6. Komplexer Sketch (>20 Constraints, gemischte Typen)

**Metriken:**
- Konvergenz-Rate (success/total)
- Iterationen bis Konvergenz
- Finaler Fehler
- Laufzeit (ms)
- Geometrie-Drift (Abweichung von erwartetem Ergebnis)

**Deliverable:** Benchmark-Tabelle in `docs/solver/SCIPY_REASSESSMENT_W35.md`

**Validierung:**
```powershell
conda run -n cad_env python -m pytest test/test_sketch_solver_status.py -v
```

### WP2: Solver-Abstraktion (~1.5h)

**Ziel:** Stabiles Interface definieren, SciPy als austauschbares Backend.

**Änderungen in `sketcher/solver.py`:**

```python
class SolverBackend:
    """Abstrakte Basis für Solver-Backends."""
    def solve(self, variables, constraints, options) -> SolverResult:
        raise NotImplementedError

class ScipyLMBackend(SolverBackend):
    """Aktueller SciPy Levenberg-Marquardt Backend."""
    ...

class ConstraintSolver:
    """Facade — delegiert an aktives Backend."""
    def __init__(self, backend: SolverBackend = None):
        self.backend = backend or ScipyLMBackend()
```

**Deliverable:** Refactored `solver.py` mit Backend-Abstraktion, alle 14 Tests grün.

### WP3: Alternative Candidates (~3h)

**Ziel:** Mindestens eine Alternative evaluieren, deterministische Vergleichstabelle.

**Candidate A: Symbolic Pre-Pass**
- FIXED-Constraints: Punkt als `fixed=True` markieren, aus Variablenliste entfernen (bereits teilweise implementiert)
- HORIZONTAL: `line.end.y = line.start.y` direkt setzen, Constraint aus Solver-Liste entfernen
- VERTICAL: `line.end.x = line.start.x` direkt setzen
- **Vorteil:** Weniger Variablen → schnellere Konvergenz, weniger Overconstrained-Risiko
- **Risiko:** Reihenfolge-Abhängigkeit bei kombinierten Constraints

**Candidate B: Staged Solve (2-Phasen)**
- Phase 1: Nur CRITICAL-Constraints (FIXED, COINCIDENT) → topologische Integrität
- Phase 2: Alle restlichen Constraints mit Ergebnis aus Phase 1 als Startwerte
- **Vorteil:** Topologie bleibt immer intakt, bessere Konvergenz
- **Risiko:** Mehr Solver-Aufrufe (2×), potenzielle Inkonsistenz zwischen Phasen

**Candidate C: Smooth Penalties (Quick-Win)**
- Tangent `arc_penalty`: Ersetze `100.0` durch `sigmoid(distance) * weight`
- **Vorteil:** Gradient bleibt stetig → bessere LM-Konvergenz
- **Risiko:** Minimal

**Deliverable:** Vergleichstabelle (Konvergenz, Laufzeit, Genauigkeit) für alle Candidates.

### WP4: Feature-Flagged Rollout (~1h)

**Ziel:** Kontrollierter Rollout ohne Verhaltensänderung für bestehende Projekte.

**Änderungen in `config/feature_flags.py`:**
```python
"solver_symbolic_prepass": False,   # WP3-A: Triviale Constraints vor Solve
"solver_staged_solve": False,       # WP3-B: 2-Phasen-Solve
"solver_smooth_penalties": False,   # WP3-C: Smooth statt harter Penalties
"solver_backend": "scipy_lm",       # WP2: Backend-Auswahl
```

**Deliverable:** Feature Flags + Solver-Integration, alle Tests grün.

### WP5: Dokumentation (~1h)

**Ziel:** `docs/solver/SCIPY_REASSESSMENT_W35.md` mit:
1. Current-state Diagnose
2. Interface- und Implementation-Änderungen
3. Benchmark-Evidenz
4. Empfehlung und Migrationsplan
5. Risiken und Rollback-Strategie

**Deliverable:** Fertige Dokumentation + Handoff.

---

## 4. Vorläufige Empfehlung (vor Benchmarks)

**Hybrid behalten:** SciPy LM als Kern, erweitert um:

1. **Symbolic Pre-Pass** (WP3-A) — größter Impact bei geringstem Risiko
2. **Smooth Penalties** (WP3-C) — Quick-Win für Tangent-Stabilität
3. **Staged Solve** (WP3-B) — optional, nur wenn Baseline-Analyse Spring-back bestätigt

**Kein vollständiger Solver-Ersatz nötig.** SciPy LM ist für 2D-Sketch-Constraints gut geeignet. Die Probleme liegen nicht am Algorithmus, sondern an der Problemformulierung (Penalties, Variablenauswahl, Regularisierung).

---

## 5. Aufwandsschätzung

| WP | Aufwand | Abhängigkeiten |
|---|---|---|
| WP1 Baseline + Benchmarks | ~2h | — |
| WP2 Solver-Abstraktion | ~1.5h | — |
| WP3 Candidates + Vergleich | ~3h | WP1, WP2 |
| WP4 Feature-Flag Rollout | ~1h | WP2, WP3 |
| WP5 Docs | ~1h | WP1–WP4 |
| **Gesamt** | **~8.5h** | |

---

## 6. Scope & Regeln (aus Prompt)

### Erlaubte Dateien
- `sketcher/solver.py`
- `sketcher/constraints.py`
- `sketcher/sketch.py` (nur Adapter-Integration)
- `test/test_sketch_solver_status.py`
- `docs/solver/*` (neu)

### Verboten
- `gui/**` (außer minimale Diagnostik-Hooks)
- `modeling/**`

### Harte Regeln
1. CAD-Kernel-first: Geometrische Korrektheit und Determinismus
2. Kein blinder Solver-Ersatz — kontrollierter Rollout
3. Keine Constraints deaktivieren um Stabilität vorzutäuschen
4. Keine Test-Abschwächung
5. Kein Merge vor User Acceptance

### Validierung
```powershell
conda run -n cad_env python -m py_compile sketcher/solver.py sketcher/constraints.py sketcher/sketch.py
conda run -n cad_env python -m pytest -q test/test_sketch_solver_status.py
```

### Stop-Bedingung
"READY FOR USER ACCEPTANCE — DO NOT MERGE"
