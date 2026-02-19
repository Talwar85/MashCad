# PROMPT_20260217_ai_largeT_w31_v1_acceleration_gigapack

Du bist AI-LargeT auf Branch `feature/v1-ux-aiB`.

## Mission
Liefer ein grosses Beschleunigungs-Paket fuer V1 mit mehreren EPICs.
Ziel: sichtbare Produktfortschritte + stabile Gates + klare Evidence in einem Durchlauf.

## Delivery-Strategie
- Arbeite EPIC-basiert in dieser Reihenfolge: P0 zuerst, dann P1.
- Jede EPIC-Lieferung braucht Code, Tests, und belegte Resultate.
- Kein "nur Analyse". Fokus auf umgesetzte, messbare Fortschritte.

## Harte Regeln
1. Kein Edit in `modeling/**` ohne explizite Notwendigkeit.
2. Kein globales Skippen/Abschwaechen von Tests als Loesung.
3. Keine Schein-Delivery ohne reproduzierbare Kommandos.
4. Bei unloesbaren Punkten: klar BLOCKED + Repro + Restplan.

## Zielbild (Abnahme auf Portfolio-Ebene)
- P0 EPICs muessen komplett green sein.
- Mindestens 2 P1 EPICs muessen komplett umgesetzt sein.
- Gesamtergebnis muss spuerbar produktiv sein (nicht nur Testpflege).

---

## EPIC A (P0) - Runtime Text Integrity + Mojibake Closure

### Ziel
Alle user-sichtbaren Mojibake-Texte in `gui/**` beseitigen und gegen Rueckfall absichern.

### Scope
- `gui/**`
- `i18n/**/*.json`
- `test/test_text_encoding_mojibake_guard.py`

### Deliverables
1. Runtime-visible text cleanup (Labels, Tooltips, Menues, Status, Hints).
2. i18n JSON UTF-8 Integritaet geprueft und ggf. korrigiert.
3. Guard-Test hardening fuer runtime + i18n.
4. Before/after matrix (counts + file list).

### Pflicht-Validation
```powershell
conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py
rg -n "Ã|Â|â|├|┬|�|Ô|Õ|×" gui i18n -g "*.py" -g "*.json"
```

---

## EPIC B (P0) - Headless UI Stability to CI-Grade

### Ziel
Keine Access-Violation/Native-Crashs in den headless Pflichtsuiten.

### Scope
- `gui/viewport_pyvista.py`
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `scripts/preflight_ui_bootstrap.ps1`

### Deliverables
1. Stabiler headless bootstrap path (reproducible).
2. Abort/Hint suites laufen deterministisch in offscreen.
3. Preflight klassifiziert native bootstrap issues sauber.
4. Guardrail-Doku fuer künftige Änderungen.

### Pflicht-Validation
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
```

---

## EPIC C (P1) - Sketch Direct Manipulation Product Leap

### Ziel
Sketch-Bedienung merklich naeher an Fusion/Onshape bringen (line/rect/arc/ellipse/polygon).

### Scope
- `gui/sketch_editor.py`
- `test/test_line_direct_manipulation_w30.py`
- `test/harness/test_interaction_direct_manipulation_w17.py`
- `test/test_sketch_editor_w26_signals.py`

### Deliverables
1. Linie: endpoint + midpoint drag parity, klare Cursorsemantik.
2. Rechteck: edge-resize stabil, dimensions-konsistent.
3. Arc: radius/start/end handles robust mit shift-lock.
4. Ellipse/Polygon: reduzierte visuelle Komplexitaet, aktive Handles klar.

### Pflicht-Validation
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_line_direct_manipulation_w30.py
conda run -n cad_env python -m pytest -q test/harness/test_interaction_direct_manipulation_w17.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py
```

---

## EPIC D (P1) - Browser Recovery Workflow Leap

### Ziel
Recovery-Flows deutlich beschleunigen (Problemfeature -> Recovery -> Fokus -> Diagnose).

### Scope
- `gui/browser.py`
- `gui/widgets/feature_detail_panel.py`
- `gui/main_window.py` (nur Integrationspfade)
- `test/test_browser_product_leap_w26.py`
- `test/test_feature_detail_recovery_w26.py`
- `test/test_main_window_w26_integration.py`

### Deliverables
1. Priorisierte Recovery-Entscheidungen klar und verstaendlich.
2. Batch-Recovery stabil inkl. mixed/hidden selection guards.
3. "Recover & Focus" end-to-end robust bei edge-cases.
4. Keine stale selection states nach batch actions.

### Pflicht-Validation
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py
```

---

## EPIC E (P1) - Gate Realism, Throughput, and Evidence

### Ziel
Quick-Gates wirklich quick und semantisch ehrlich machen.

### Scope
- `scripts/gate_fast_feedback.ps1`
- `scripts/generate_gate_evidence.ps1`
- `scripts/validate_gate_evidence.ps1`
- ggf. `test/test_gate_runner_contract.py`

### Deliverables
1. Profilziele konsistent mit realen Laufzeiten.
2. Evidence-Felder zeigen klar: target vs actual vs blocker class.
3. Keine stillen Inkonsistenzen in JSON schema/semantics.

### Pflicht-Validation
```powershell
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_ultraquick
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py::TestFastFeedbackTimeoutW29 test/test_gate_evidence_contract.py
```

---

## EPIC F (P2) - Release Readiness Matrix

### Ziel
Klare Release-Checkmatrix fuer V1-Teilabschluss bereitstellen.

### Scope
- `roadmap_ctp/**`
- optional neue Datei `roadmap_ctp/W31_RELEASE_READINESS_MATRIX.md`

### Deliverables
1. Feature/Gate/Test readiness table mit PASS/PARTIAL/BLOCKED.
2. Top 10 Risks + Mitigations.
3. Klare naechste 2 Sprints mit owner/action/outcome.

---

## Global Validation Bundle (am Ende)
```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'
conda run -n cad_env python -m pytest -q test/test_text_encoding_mojibake_guard.py
conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py test/test_discoverability_hints.py
conda run -n cad_env python -m pytest -q test/test_line_direct_manipulation_w30.py test/test_sketch_editor_w26_signals.py
conda run -n cad_env python -m pytest -q test/test_browser_product_leap_w26.py test/test_feature_detail_recovery_w26.py test/test_main_window_w26_integration.py
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
```

## Hard Acceptance Gates
Delivery = FAIL, wenn:
1. EPIC A oder B nicht vollstaendig gruen.
2. Weniger als 2 P1 EPICs komplett geliefert.
3. Keine belastbare before/after evidence vorhanden.
4. Tests gruen nur durch Skip/Abschwaechung.

## Rueckgabeformat
Datei:
- `handoffs/HANDOFF_20260217_ai_largeT_w31_v1_acceleration_gigapack.md`

Pflichtstruktur:
1. Problem
2. EPIC Breakdown (Done/Partial/Blocked)
3. API/Behavior Contract
4. Impact (files + rationale)
5. Validation (exact commands + outputs)
6. Before/After Matrices (counts, runtime, coverage)
7. Breaking Changes / Rest Risks
8. Next 10 prioritized follow-up actions

## Zusatzpflicht
- Mindestens 60 konkrete Aenderungen als Liste (Datei + Kurzbeschreibung).
- Mindestens 3 sichtbare Produktdeltas fuer Endnutzer in klarer Sprache.
- BLOCKED Punkte explizit mit Repro-Command.
