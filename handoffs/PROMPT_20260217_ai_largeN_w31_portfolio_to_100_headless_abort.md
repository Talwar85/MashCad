# PROMPT_20260217_ai_largeN_w31_portfolio_to_100_headless_abort

Du bist AI-LargeN auf Branch `feature/v1-ux-aiB`.

## Mission
Schliesse den gesamten Teilbereich "Headless/UI-Abort/Discoverability Stability" auf 100 Prozent ab.

Dies ist kein Minifix. Das ist ein End-to-End Portfolio-Delivery mit harter Abnahme.

## Ausgangslage
Der vorherige N-Lauf wurde abgelehnt.
Hauptgrund:
- Reproduzierbare Access Violations in Headless bleiben bestehen.
- Claims und echte Laufresultate stimmen nicht ueberein.

Ab jetzt gilt: Nur messbare, reproduzierbare Stabilisierung zaehlt.

---

## Portfolio-Zielbild (100 Prozent fuer diesen Part)
Nach Lieferung muessen alle folgenden Punkte gleichzeitig erfuellt sein:

1. Keine Access Violations in den Pflichtsuiten.
2. ESC/Right-Click Abort-Parity bleibt funktional korrekt.
3. Discoverability-Hints bleiben semantisch korrekt und deterministisch.
4. MainWindow/Viewport-Testbootstrap ist reproduzierbar headless-safe.
5. Gate-/Preflight-Klassifikation unterscheidet sauber Produktdefekt vs Infra-Blocker.
6. Dokumentation + Evidence sind so klar, dass jede weitere KI den Part ohne Kontextverlust weiterfuehren kann.

---

## Harte Grenzen

### No-Go (nicht editieren)
- `modeling/**`
- `gui/sketch_editor.py`
- `gui/browser.py`

### Erlaubter Bereich
- `test/test_ui_abort_logic.py`
- `test/test_discoverability_hints.py`
- `test/test_main_window_w26_integration.py`
- `test/test_projection_trace_workflow_w26.py`
- `test/test_sketch_editor_w26_signals.py`
- `test/ui/**`
- `test/conftest.py`
- `gui/main_window.py` (nur falls fuer stabilen Bootstrap zwingend)
- `gui/viewport_pyvista.py` (nur falls fuer stabilen Bootstrap zwingend)
- `scripts/preflight_ui_bootstrap.ps1`
- `scripts/gate_fast_feedback.ps1`
- `scripts/generate_gate_evidence.ps1`
- `scripts/validate_gate_evidence.ps1`
- `roadmap_ctp/**` (Status/Evidence)

### Verboten
- Globales blindes Skippen.
- "No repro" behaupten, wenn die Suite crashen kann.
- Nur kosmetische Test-Aenderungen ohne Crash-Fix.
- Green durch Entfernen zentraler Assertions.

---

## Arbeitspakete (Riesenportfolio)

## EPIC A - Headless Crash Eradication (P0)

### A1: Repro-Matrix + Crash-Signatur
- Erstelle eine stabile Repro-Matrix fuer:
  - `test/test_ui_abort_logic.py`
  - `test/test_discoverability_hints.py`
- Dokumentiere Crash-Signatur (Stack-Hotspots, Triggerbedingungen).
- Zeige min. 2 reproduzierbare Vorher-Faelle.

### A2: Bootstrap Architecture (Fixture-Level)
- Fuehre einen einheitlichen headless-safe Bootstrap-Pfad fuer MainWindow-Tests ein.
- Verhindere reale VTK/Interactor-Initialisierung in den betroffenen Testpfaden, ohne Produktlogik zu amputieren.
- Scope minimal halten: nur fuer betroffene Suiten/Fixtures.

### A3: Safety Guards gegen Native Crash-Klasse
- In Test-Setup/teardown sichere Reihenfolge fuer Qt/Viewport-Ressourcen.
- Keine doppelte Initialisierung von kritischen nativen Komponenten.
- Keine zombie-state Leaks zwischen Tests.

### A4: Verification Harness
- Neue gezielte Tests fuer Bootstrap-Lebenszyklus:
  - setup -> action -> teardown
  - mehrfach hintereinander in gleicher Pytest-Session


## EPIC B - Abort/Hint Semantics Hardening (P0)

### B1: Abort-Parity Contract
- Verifiziere und haerte:
  - ESC und Right-Click fuehren in gleichen Endzustand
  - kein ghost drag state
  - kein stale modal/stack state

### B2: Discoverability Determinism
- Hints robust gegen Timing/Event-Order.
- Keine semantische Aufweichung der Assertions.
- Encoding robust ohne Bedeutungsverlust.

### B3: Priority/Cooldown Integrity
- Priority Stack und Cooldown nicht regressieren.
- Fuege Regressionstests fuer bekannte Wackelstellen hinzu.


## EPIC C - Gate & Evidence Reliability (P1)

### C1: Preflight Blocker Taxonomy
- `preflight_ui_bootstrap.ps1` so erweitern, dass Access-Violation-Klasse sauber als Infra/Native-Bootstrap-Risiko klassifiziert werden kann.
- Klassifikation darf echte Produktfehler nicht verschleiern.

### C2: Fast-Feedback Profile Mapping
- `gate_fast_feedback.ps1` Profile so pflegen, dass dieser Part schnell und reproduzierbar pruefbar ist.
- Kein Timeout-Skip als Loesung.

### C3: Evidence Schema Completeness
- `generate_gate_evidence.ps1` und `validate_gate_evidence.ps1` um Felder erweitern (falls noetig), damit Headless-Stabilitaet explizit nachweisbar ist:
  - `native_bootstrap_status`
  - `access_violation_detected`
  - `headless_bootstrap_mode`


## EPIC D - Completion Package / Handover to 100 (P1)

### D1: Closure Matrix
- Erstelle eine Abschlussmatrix "Headless-Abort Part" mit klaren Checks (PASS/FAIL) fuer alle Teilziele.

### D2: Runbook
- Kurzes Runbook: wie man lokal und in CI exakt denselben Green-Zustand reproduziert.

### D3: Guardrail Doc
- Dokumentiere, welche Aenderungen in Zukunft diese Stabilitaet wieder brechen koennen, inkl. Fruehwarn-Tests.

---

## Pflicht-Validierung (muss im Handoff 1:1 enthalten sein)

```powershell
$env:QT_OPENGL='software'; $env:QT_QPA_PLATFORM='offscreen'

conda run -n cad_env python -m pytest -q test/test_ui_abort_logic.py
conda run -n cad_env python -m pytest -q test/test_discoverability_hints.py
conda run -n cad_env python -m pytest -q test/test_main_window_w26_integration.py
conda run -n cad_env python -m pytest -q test/test_projection_trace_workflow_w26.py
conda run -n cad_env python -m pytest -q test/test_sketch_editor_w26_signals.py
conda run -n cad_env python -m pytest -q test/test_workflow_product_leaps_w25.py
```

Optional zusaetzlich (wenn geaendert):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_ultraquick
```

---

## Harte Abnahmebedingungen (Fail-Fast)

Delivery ist automatisch FAIL, wenn einer dieser Punkte zutrifft:

1. Eine Pflichtsuite crasht mit Access Violation.
2. `test/test_ui_abort_logic.py` oder `test/test_discoverability_hints.py` wurde nur durch Skip/Abschwaechung "gruen".
3. Kein klarer technischer Root Cause und keine belegte Fix-Kette.
4. Handoff behauptet Pass, aber Kommandos/Ergebnisse fehlen oder sind widerspruechlich.

---

## Rueckgabeformat
Erzeuge:
- `handoffs/HANDOFF_20260217_ai_largeN_w31_portfolio_to_100_headless_abort.md`

Pflichtstruktur:
1. Problem
2. Root Cause (konkret, technisch)
3. API/Behavior Contract
4. Impact (Datei + Aenderung + Grund)
5. Validation (exakte Kommandos + Resultate)
6. Closure Matrix (alle Ziele PASS/FAIL)
7. Breaking Changes / Rest-Risiken
8. Naechste 5 priorisierte Folgeaufgaben

Zusatzpflicht:
- Vollstaendige Liste aller geaenderten Dateien.
- Fuer jede geaenderte Datei: "Warum noetig" in 1-2 saetzen.
- Falls ein Punkt nicht geloest: klar als BLOCKED mit Repro.

---

## Erwartungshaltung
Dies ist ein Portfolio-Delivery zur Vollendung eines gesamten Projekt-Parts.
Keine Teilfertigkeit, keine kosmetischen Ergebnisse, keine Unschaerfe.

Nur reproduzierbare Stabilitaet + klare Evidence = akzeptiert.
