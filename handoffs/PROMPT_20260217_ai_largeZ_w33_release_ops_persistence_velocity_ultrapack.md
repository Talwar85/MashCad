# PROMPT_20260217_ai_largeZ_w33_release_ops_persistence_velocity_ultrapack

Du bist AI-LARGE-Z (Release/Ops/Persistence Cell) auf Branch `feature/v1-ux-aiB`.

## Mission
Ein grosses Beschleunigungspaket fuer V1-Lieferfaehigkeit: persistente Stabilitaet, Gate-Realismus, schnelle Feedback-Zyklen ohne Quality-Tradeoff.

## Nicht-Ueberschneidung
Dieses Paket soll NICHT Core-TNP-Logik und NICHT Sketch-Interaktionslogik bearbeiten.

### No-Go
- `modeling/__init__.py`
- `gui/sketch_editor.py`
- `gui/sketch_handlers.py`

### Fokus
- `scripts/gate_fast_feedback.ps1`
- `scripts/preflight_ui_bootstrap.ps1`
- `test/test_project_roundtrip_persistence.py`
- `test/test_feature_edit_robustness.py`
- `test/test_gate_runner_contract.py`
- `test/test_gate_evidence_contract.py`
- optional weitere release/reliability tests
- Doku unter `roadmap_ctp/**` (nur wenn echte technische Aenderung mitgeliefert wird)

## Harte Regeln
1. Keine Skips/Xfails als Zeitersatz.
2. Keine Gate-Manipulation, die Coverage kaschiert.
3. Jeder neue Profile/Script-Pfad braucht Contract-Test.
4. Keine "nur Doku"-Lieferung.

---

## EPIC Z1 - Persistence Roundtrip Hardening (P0)
Ziel: Projekte laden/speichern auch bei Recovery-/Error-Zustaenden robust und deterministisch.

### Aufgaben
1. Roundtrip-Faelle ausbauen:
- Fehlerstatus-Features
- Recovery-relevante Metadaten
- optionale runtime_dependency/status_details Felder

2. Sicherstellen, dass Wiederladen keine stillen Datenverluste erzeugt.
3. Regression-Tests fuer Cross-Version-kompatible Defaults (wo moeglich).

---

## EPIC Z2 - Gate-Profilisierung fuer Geschwindigkeit + Aussagekraft (P0)
Ziel: Schnellere Loops ohne Informationsverlust.

### Aufgaben
1. Gate-Profile sauber staffeln (z. B. ultraquick/quick/core/recovery).
2. Pro Profil:
- klares Laufzeitziel
- klare Suite-Zuordnung
- evidence output (target vs actual)

3. Contract-Tests erweitern, damit falsche Profile/inkonsistente Evidence sofort failen.

---

## EPIC Z3 - Timeout-proof Execution Strategy (P1)
Ziel: "skip wegen timeout" aus dem Prozess entfernen.

### Aufgaben
1. Lange Suites in reproduzierbare Chunks zerlegen (scripted sequence).
2. Fehlerhafte Teilruns sollen früh und eindeutig abbrechen (klarer exit code).
3. Dokumentierte Recommended-Order fuer lokale und CI-nahe Ausfuehrung.

---

## EPIC Z4 - Workspace Hygiene Gate (P1)
Ziel: versehentliche temp/bak-Artefakte sichtbar machen, ohne legitime handoffs zu blockieren.

### Aufgaben
1. Hygiene-check fuer problematische Muster (z. B. `*.bak`, `temp_*`, debug artefacts).
2. Ausnahme-Policy sauber und minimal halten.
3. Testabdeckung fuer Hygiene-Regeln.

---

## Pflicht-Validierung
```powershell
conda run -n cad_env python -m py_compile scripts/gate_fast_feedback.ps1 scripts/preflight_ui_bootstrap.ps1
conda run -n cad_env python -m pytest -q test/test_project_roundtrip_persistence.py test/test_feature_edit_robustness.py
conda run -n cad_env python -m pytest -q test/test_gate_runner_contract.py test/test_gate_evidence_contract.py
powershell -ExecutionPolicy Bypass -File scripts/gate_fast_feedback.ps1 -Profile ui_quick
powershell -ExecutionPolicy Bypass -File scripts/preflight_ui_bootstrap.ps1
```

## Akzeptanzkriterien
- Mindestens 1 echte Verbesserungsmaßnahme in Persistence/Release-Flow (nicht nur Text).
- Gate-Profile + Evidence kontraktuell abgesichert.
- Kein Timeout-Skip-Pattern in der gelieferten Strategie.

## Rueckgabeformat
Datei: `handoffs/HANDOFF_20260217_ai_largeZ_w33_release_ops_persistence_velocity_ultrapack.md`

Struktur:
1. Problem
2. API/Behavior Contract
3. Impact
4. Validation
5. Breaking Changes / Rest-Risiken
6. Naechste 3 priorisierte Folgeaufgaben
